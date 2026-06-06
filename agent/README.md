# agent · 对话式反诈 Agent

把"粘进去出卡片"的分类器，升级成一个真正的 **Agent**：会多轮追问、调用案例库工具查证、给出按优先级排序的可执行处置。这是项目里"Agent"二字的落点。

## 它和 H5/规则引擎的关系

| 层 | 形态 | 角色 |
|---|---|---|
| H5（`web/`） | 纯前端、零服务器 | 现场扫码即用，单次"粘进去出卡片" |
| 规则+向量引擎（`demo/`） | 本地检测 | 召回与打分 |
| **对话式 Agent（本目录）** | Claude API + 工具调用 | **多轮研判**：追问 → 查库 → 处置 |

## 运行

```bash
pip install openai
export DEEPSEEK_API_KEY=sk-...
python agent/guardian_agent.py
```

没有 key 时程序会打印配置指引；想离线看效果见 [`demo_transcript.md`](demo_transcript.md)。

## 架构

- **模型**：默认 `deepseek-chat`（DeepSeek，OpenAI 兼容接口）。
- **工具 `search_cases`**：在 `demo/knowledge_base.json`（50 类）里按关键词/话术重合度检索最相关案例，纯本地、无需联网。模型自己决定何时追问、何时查库、何时下结论（标准 function-calling agentic loop）。
- **红线写进系统提示**：不恐吓、不武断；已转账/泄露则第一句强调止损（96110 / 挂失 / 报警）；只依据案例库与公开反诈知识，不编造。
- **可换任意 OpenAI 兼容端点**：设 `NJU_AGENT_BASE_URL` / `NJU_AGENT_API_KEY` / `NJU_AGENT_MODEL` 即可——这正说明 OpenClaw 等平台"本质也是调 API"，迁移成本极低。

## 关于 OpenClaw / 是否要 Docker

大赛要求"基于 OpenClaw"，但 OpenClaw 本质也是**调用大模型 API + 工具编排**。本 Agent 就是这套能力的可移植实现：

- **不需要你自己封 Docker 镜像**。这是一个普通 Python 脚本，依赖只有 `openai`（用其 OpenAI 兼容客户端调 DeepSeek）。
- 因为走的是 OpenAI 兼容协议，**换平台只改 `NJU_AGENT_BASE_URL` / `NJU_AGENT_API_KEY` / `NJU_AGENT_MODEL` 三个环境变量**。OpenClaw 若提供兼容端点即可直接接；否则在其控制台里把 `search_cases` 工具和系统提示配成一个智能体流程——交付的是配置/流程，不是容器镜像。
- 因此现阶段：本地这套 = 真东西；OpenClaw 那层是"换一个托管/编排壳"。具体提交要求以大赛文档为准。
