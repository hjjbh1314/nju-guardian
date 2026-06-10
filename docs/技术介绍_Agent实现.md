# 南大数智安全官 · 技术介绍（Agent / LLM 实现）

> 给"用了什么 agent、怎么实现的"这类追问准备的底稿。每一条都对应仓库里的真实代码，能经得起细问。

---

## 一句话
整体是**分层研判架构**：端侧"三路引擎"做毫秒级、可解释的秒判；**难例升级到一个 LLM Agent**——基于 **DeepSeek + OpenAI 兼容的 function calling**，我们**手写了一个 agentic loop**，让模型自己决定"先追问、再调工具查案例库、最后下判断"。

---

## 一、我们的 Agent 是什么、怎么实现的（核心）

**代码**：`agent/guardian_agent.py`（约 190 行，纯 Python）

**范式**：function-calling 的 **agentic loop**（ReAct 思路）——**没有套 LangChain/AutoGPT 之类的重框架，是自己实现的循环**。理由：反诈场景要**可控、可解释、可审计**，重框架黑箱多、不好把控。

**三个要件**：

1. **模型接入（可替换是关键卖点）**
   用 `from openai import OpenAI` 这个**OpenAI 兼容 SDK**，默认指向 DeepSeek：
   ```python
   client = OpenAI(api_key=API_KEY, base_url=BASE_URL)   # base_url=https://api.deepseek.com
   ```
   因为走的是 OpenAI 兼容协议，**换任何兼容端点都只改环境变量**（`NJU_AGENT_BASE_URL / API_KEY / MODEL`）——可平替到本地/私有化模型，**数据不出校**。

2. **工具（Tool）：`search_cases`**
   给模型注册了一个工具，作用是**在本地 `knowledge_base.json` 里检索最相关的诈骗案例**（纯本地、无需联网）：
   ```python
   TOOLS = [{
     "type": "function",
     "function": {
       "name": "search_cases",
       "description": "在反诈案例库里检索最相关的诈骗案例",
       "parameters": { "query": "string", "top_k": "int" }
     }
   }]
   ```

3. **Agentic loop：模型自己决定调几次工具**
   核心是 `run_turn` 里的 `while True`：
   ```python
   while True:
     resp = client.chat.completions.create(
         model=MODEL, messages=messages, tools=TOOLS, temperature=0.3)
     msg = resp.choices[0].message
     messages.append(msg)                    # 记下助手消息(可能含 tool_calls)
     if not msg.tool_calls:                   # 模型不再调工具 → 给出最终研判，结束
         return messages
     for tc in msg.tool_calls:                # 模型要调工具
         hits = search_cases(**json.loads(tc.function.arguments))
         messages.append({"role": "tool",
                          "tool_call_id": tc.id,
                          "content": json.dumps(hits)})   # 把案例查回去喂给模型
   ```
   **流程**：用户说一句 → 模型判断信息够不够 → 不够就**追问关键细节**（是否要转账/要验证码/对方身份）→ 够了就**调 `search_cases` 查案例库**→ 拿着检索结果**给出带依据的研判和处置建议**。模型可以多轮、多次调工具，直到收敛。

**System prompt 的行为约束**：明确要求它"**先掌握足够信息、再调 search_cases 查证、不要凭空臆断**"——所以它不是张口就判，而是**先问后查再答**，这正是"Agent"区别于"单次问答"的地方。

**外层多轮对话**：主循环 `while True` 持续接收用户输入，保留上下文，支持连续追问。

---

## 二、其他几处 LLM 应用（一并讲，显得体系完整）

| 用途 | 在哪 | 怎么做 |
|---|---|---|
| **H5「AI 深度研判」** | Cloudflare Worker → DeepSeek | 把**端侧三路引擎的研判结果作为 context** 喂给大模型，做一次深度解释+处置（单轮）。密钥存服务端 Secret，不进前端 |
| **采集自动结构化** | `ingest/structure.py` | LLM 把公开来源**原文 → 12 字段案例**，进校验流水线 |
| **上报自动草拟** | Worker `/report` | 用户上报一句话，DeepSeek **自动草拟成 12 字段案例**写进 GitHub Issue，维护者只核验+补来源（来源 AI 不编造） |

> 区别要讲清：**只有 `guardian_agent.py` 是带工具调用循环的"Agent"**；其余三处是"LLM 增强"（单轮、无工具循环）。别把它们都叫 Agent。

---

## 三、为什么这么设计（设计取舍，加分项）

- **分层**：简单的端侧规则/语义/行为红旗秒判，**只有难例才上 LLM Agent**——成本可控、响应快、可离线、隐私可端侧。不是无脑全上大模型。
- **手写 loop 不套框架**：反诈要可控可审计，自己实现的 function-calling 循环每一步都看得见。
- **工具是本地检索**：Agent 的"查证"在本地案例库完成，不把用户内容外发去检索。
- **模型可替换**：OpenAI 兼容协议，换端点只改环境变量，能上私有化/本地模型，数据不出校。

---

## 四、可能被追问 & 怎么答

**Q：用了什么 Agent 框架？**
没用重框架（LangChain/AutoGPT 等）。基于 OpenAI 兼容的 **function calling 自己写的 agentic loop**——反诈场景要可控、可解释、可审计，自己实现每一步都可控。

**Q：Agent 和普通问答的区别？**
它会**自主决定**：信息不够先追问、需要查证就调 `search_cases` 工具、多轮迭代直到能给出有依据的判断——是"会用工具、会追问"的智能体，不是一问一答。

**Q：工具就一个，算 Agent 吗？**
算。Agent 的本质是"模型自主规划 + 调用工具 + 观察结果再决策"的循环，工具数量不是标准；我们的循环里模型可多次调用、按需追问。要扩展也容易（再注册工具即可）。

**Q：为什么用 DeepSeek？能换吗？**
DeepSeek 中文反诈语境好、便宜、国内可直连；而且我们走 OpenAI 兼容协议，**换任何兼容模型（含校内私有化部署）只改一个环境变量**。

**Q：大模型会乱判 / 幻觉吗？怎么控制？**
三重控制：①system prompt 强制"先查证再判断、不臆断"；②工具检索的是**人工审核过的本地案例库**，给它真实依据；③大模型只在**难例**触发，简单情形端侧规则已定级。

**Q：数据安全？**（详见《答辩问答清单》Q10）
端侧默认不上传；只有主动用 AI 研判才传那一条，经加密代理、密钥服务端、不留存；可平替私有化模型数据不出校。

---

### 30 秒口述版
"我们是分层架构：端侧三路引擎做秒判，难例升级到一个 LLM Agent。这个 Agent 基于 DeepSeek 和 OpenAI 兼容的 function calling，我们手写了 agentic loop——它会先追问关键细节，再调用 `search_cases` 工具去本地案例库查证，最后给出带依据的研判，可以多轮迭代。因为走兼容协议，模型能随时换成校内私有化部署，数据不出校。"
