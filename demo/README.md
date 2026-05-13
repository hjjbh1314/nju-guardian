# 南大数智安全官 NJU Guardian · Demo v0.2.1

> OpenClaw 应用创新大赛参赛项目的本地原型 Demo。在没有 OpenClaw 平台访问权限前，本机即可跑通"文本检测 / 截图识别 / 链接核验"三模态。

## 🆕 v0.2.1 升级（2026-05-07）

| 更新点 | 说明 |
|---|---|
| **案例库扩到 50 类** | 国家反诈十大类 + 校园特化 + 新型 AI 诈骗，每条带公开来源 |
| **双路召回检测引擎** | 新增 `embedding_engine.py`：BGE-zh 向量召回 + 关键词/正则规则匹配，融合打分 |
| **📤 可转发卡片** | 检测后一键生成可发到班群/朋友圈的简洁文字（含案例 + 行动建议 + 八个凡是 + 紧急联系）|
| **💾 报告下载** | 点击下载 HTML 检测报告，浏览器中 ⌘+P 即可保存为 PDF |
| **AI 换脸/共享屏幕等新型诈骗** | 覆盖 2024-2025 高发场景：AI 换脸、共享屏幕、币圈、二次诈骗清退群 |
| **校园场景细分** | 论文代写、留学保录、付费内推、教务系统钓鱼、火车票退改签等 12 类校园特化 |
| **公开来源标注** | 每条 case 强制 `source` 字段引用国家反诈中心、央视、新华社等公开材料 |
| **CC BY 4.0 授权** | 知识库可被引用，仅需保留来源标注 |
| **📹 30s 路演脚本** | `录屏脚本_30s.md` 提供精确分镜 + 推荐输入样例，路演不翻车 |

### 🔍 双路召回原理

```
用户输入
   ├─→ 规则路：keywords / regex 命中 → rule_score
   └─→ 向量路：BGE-zh embedding 余弦相似度 → vector_sim
              ↓
     综合分 = rule_score + 2.5 × vector_sim
              ↓
     风险等级（综合规则强度与语义相似度双信号）
```

**关键参数**：

- 向量模型：`BAAI/bge-small-zh-v1.5`（95MB，中文优化）
- 召回门槛：`rule_score ≥ 1.0` 或 `vector_sim ≥ 0.55` 才进候选
- 高风险条件：`rule_score ≥ 3.0`，或 `rule_score ≥ 1.5 且 vector_sim ≥ 0.55`（双路确认）
- 中等风险：单路较强信号
- 模型加载失败 → 自动降级 TF-IDF；TF-IDF 也失败 → 跳过向量路只用规则

**冒烟测试**：8/8 输入（含规则弱命中、纯语义命中）TOP-1 全部命中正确 case。

## 🕘 v0.2 历史更新（2026-05-06）

| 更新点 | 说明 |
|---|---|
| **对话卡片输出** | 报告改成结构化卡片：彩色风险横条 + 命中关键词高亮 + 八个凡是引用块 + 三步建议 |
| **八个凡是匹配** | 自动从命中案例里抽出"国家反诈八个凡是"对应条目并独立展示 |
| **关键词高亮** | 用户原文里命中的关键词自动加粗，看得见"为什么被打标" |
| **知识库浏览** | 新增 Tab，可视化全部案例（类型分布、关键词、话术、首选建议）|
| **示例对话** | 新增 Tab，路演时直接放映 3 条标杆问答（不用现场敲键盘）|
| **关于** | 新增 Tab，说明本 Demo 与决赛 OpenClaw 版的差异 |
| **Hero 区** | 南大紫渐变 banner + 数据来源 + 紧急联系条 |
| **链接检测增强** | 增加 HTTP 警告、扩展短链识别、IP 地址检测优化 |

## 🚀 快速运行

### 1. 装依赖

```bash
cd "/Users/haiwenbao/Documents/OpenClaw应用创新大赛/demo"
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2.（可选）装 OCR 依赖

只用「文本检测」和「链接核验」**不需要装 OCR**。要用「截图识别」才需要：

```bash
# macOS
brew install tesseract tesseract-lang

# Ubuntu / Debian
sudo apt install tesseract-ocr tesseract-ocr-chi-sim
```

### 3. 启动

```bash
python nju_guardian.py
```

浏览器开 [http://127.0.0.1:7860](http://127.0.0.1:7860)。

---

## 🧪 8 条可粘贴测试样例（路演用）

| # | 输入 | 应触发 KB | 应匹配「八个凡是」第几条 |
|---|---|---|---|
| 1 | `辅导员让我代收班费要我先转 800 给他他周一返我` | KB-008 | 6 |
| 2 | `群里说免费送礼品+点赞返佣金，要下载 APP 做任务` | KB-001 | 1, 7 |
| 3 | `【京东客服】您订单异常，点击 http://jd-fix.xyz` | KB-013 | 7 |
| 4 | `注销校园贷影响征信请转入清算账户` | KB-006 | — |
| 5 | `您涉嫌洗钱请将资金转入安全账户配合调查` | KB-005 | 5 |
| 6 | `演唱会内场票低价转让加微信私下交易` | KB-007 | — |
| 7 | `无抵押免征信秒放款交保证金即可放款` | KB-003 | 3 |
| 8 | `内幕消息稳赚不赔加入投资群` | KB-002 | 2 |

8/8 全部通过 smoke test。

---

## ⚙️ LLM 增强（可选）

本 Demo 默认使用本地规则匹配，**完全离线、无需 API**。

如果想要更"智能"的解读（行为视角、定制化建议），可在 UI 右侧勾选"启用 LLM 增强"，填入兼容 OpenAI 协议的 API：

| 服务商 | Base URL | 模型示例 | 备注 |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | 国内便宜 |
| 通义百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | 阿里云 |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | Kimi |

也可用环境变量预填：

```bash
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"
python nju_guardian.py
```

---

## 📂 文件结构

```
demo/
├── README.md             ← 本文件
├── requirements.txt      ← Python 依赖
├── knowledge_base.json   ← 50 类结构化诈骗案例知识库
├── embedding_engine.py   ← BGE-zh / TF-IDF 双路召回中的向量路
├── nju_guardian.py       ← Gradio Web 应用主程序
└── tests/test_smoke.py   ← CI 冒烟测试
```

---

## 🎬 路演录制建议（30 秒视频）

按这个顺序操作可以拍出最有冲击力的演示：

1. **0–3 秒**：界面截图，南大紫 banner + 标题 + 知识库 50 类标签
2. **3–10 秒**：「文本检测」Tab，点示例"辅导员代收班费" → 红色高风险 + 八个凡是·第六条匹配
3. **10–18 秒**：滚动展示「为什么是诈骗」「三步行动建议」「相似案例」
4. **18–24 秒**：切到「示例对话」Tab，向评委展示 3 条标杆问答（无需现场敲键盘）
5. **24–30 秒**：切到「知识库浏览」Tab，展示 50 类案例覆盖度

录屏：macOS QuickTime（⌘+⇧+5）或 OBS。

---

## 🔭 与决赛 OpenClaw 版的差异

| 维度 | 本地 Demo（v0.2） | 决赛 OpenClaw 版 |
|---|---|---|
| 检测引擎 | 关键词 + 正则匹配 | OpenClaw RAG 向量检索 + 多 Agent 协作 |
| OCR | 本地 tesseract | OpenClaw 多模态能力 |
| 案例库规模 | 50 类 | 200+ 条（含真实校园回流） |
| 部署形态 | 本地 Gradio | 微信小程序 + OpenClaw 平台 |
| 数据脱敏 | 原型阶段不持久化 | 专门 Workflow 自动 PII 脱敏 |

---

## 📌 注意事项

- 知识库版本 `0.2.0`，覆盖国家反诈中心十大类案 + 校园特化场景共 50 类（含 AI 换脸、共享屏幕、二次诈骗清退群等新型场景）
- 本地启发式检测**不能替代国家反诈中心 App** 与 96110 劝阻
- 如真实遭遇诈骗，请立即拨打 **96110 / 110 / 南大保卫处 81686110**

---

## 📞 紧急联系

南京大学保卫处 **81686110** ｜ 96110 反诈劝阻 ｜ 12381 涉诈短信 ｜ 110 报警
