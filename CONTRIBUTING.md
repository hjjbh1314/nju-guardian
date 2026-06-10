# 贡献指南 · NJU Guardian

感谢你想为校园反诈做点事。本指南覆盖：

- [新增诈骗案例](#新增诈骗案例)（最常见的贡献）
- [改进检测引擎](#改进检测引擎)
- [改进 UI / 文档](#改进-ui--文档)
- [报 bug](#报-bug)

## 🚨 一条不可让步的规则

**所有进入仓库的诈骗案例，必须能给出公开来源 URL、正式出版物名称或可核验的公开来源标注。**

允许的来源：

- ✅ 国家反诈中心、公安部刑侦局、12381 等政府发布
- ✅ 央视、新华、人民日报、澎湃等主流媒体公开报道
- ✅ 学术机构（如中国信通院）公开发布的研究报告
- ✅ 高校保卫处**已公开**的反诈推文 / 官网（必须改写，不得逐字复制）

**不允许**的来源：

- ❌ 论坛、贴吧、知乎匿名自述（隐私+真实性都没保障）
- ❌ 微信群截图、私下聊天记录（即使打码也是隐私材料）
- ❌ 高校保卫处内部材料、未公开的预警邮件
- ❌ 受害者实名自述（除非本人已公开授权）

如果你不能给一条 case 找到稳定的公开来源，**就不要把它加进知识库**。已有来源短标说明见 [docs/sources.md](docs/sources.md)。

> 一旦本仓库被发到 GitHub，就等于"公开发表"。"反正都是高校"的逻辑在开源前提下不成立。

---

## 新增诈骗案例

### 字段规范

每条 case 是 `demo/knowledge_base.json` 的 `cases` 数组里的一个对象，必填字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `KB-NNN` 格式，三位数字递增，不重复 |
| `type` | string | 类型短标签（5-10 字），如 "AI换脸拟声" |
| `name` | string | 完整案例名（10-20 字）|
| `risk_level` | enum | `high` / `medium-high` / `medium` / `low-medium` / `low` |
| `keywords` | string[] | 8-12 个关键词，长度 2-8 字。**避免单字关键词**（误命中率高）|
| `patterns` | string[] | 1-3 条正则。**先在 [regex101](https://regex101.com)（中文 flavor 选 PCRE）测试**，避免无效正则 |
| `script_examples` | string[] | 2-3 条典型话术原文（可改写）|
| `steps` | string[] | 3 个作案步骤，每条以场景动词开头 |
| `why_scam` | string[] | 2-3 条解释为什么是诈骗。**如对应国家反诈预警要点，请用固定格式**：`"国家反诈预警要点·第N条：..."` |
| `advice` | string[] | 3 步行动建议，**每条动词开头，不超过 25 字** |
| `emergency` | string[] | 至少含一个可识别的号码（96110 / 110 / 12381 / 12348 等）|
| `source` | string | 公开来源标注，格式 `[出版物/机构]·[条目]` 例 `国家反诈手册2023·KB1` |

### 提交流程

1. Fork 本仓库
2. 在 `demo/knowledge_base.json` 的 `cases` 数组**末尾**追加你的 case
3. 检查 `id` 不与现有冲突（最大值 + 1）
4. 跑 `python demo/tests/test_smoke.py`，必须全部 PASS
5. 自测：用 `script_examples[0]` 作为输入跑 `demo/nju_guardian.py`，确认能命中你刚加的 case
6. 提交 PR，PR 描述附**每条 case 的来源 URL 或完整来源信息**

### Case 起草模板

```jsonc
{
  "id": "KB-051",
  "type": "新型类型短标",
  "name": "完整案例名",
  "risk_level": "high",
  "keywords": ["关键词1", "关键词2"],
  "patterns": ["(锚词).*(伴词)"],
  "script_examples": ["典型话术1", "典型话术2"],
  "steps": [
    "步骤1：引流方式",
    "步骤2：建立信任 / 制造焦虑",
    "步骤3：实施诈骗"
  ],
  "why_scam": [
    "国家反诈预警要点·第N条：...（如适用）",
    "其他识别原理"
  ],
  "advice": [
    "动词开头的行动建议1",
    "动词开头的行动建议2",
    "已被骗立即拨打 96110 或 ..."
  ],
  "emergency": ["96110", "..."],
  "source": "公开来源·章节"
}
```

---

## 改进检测引擎

### 调试单条输入

```bash
cd demo && .venv/bin/python -c "
from nju_guardian import detect
matches = detect('你的可疑文本')
for m in matches:
    print(m.case['id'], m.score, 'rule=', m.rule_score, 'vec=', m.vector_sim)
"
```

### 性能要点

- **向量缓存**：KB 改了之后，第一次启动会重建嵌入（耗时 5-15s）；缓存放在 `demo/.embeddings_cache/`
- **检测延迟**：单次 detect ~180ms（命中模型缓存后）
- **CPU only**：默认 PyTorch CPU；上 GPU 不会更快（句子很短）

### 改阈值前先想清楚

现有阈值（在 `nju_guardian.py:detect()`）：
- `RULE_MIN_SOFT = 1.0` — 规则分进候选门槛
- `VEC_MIN_SOFT = 0.55` — 向量分进候选门槛
- `VEC_WEIGHT = 2.5` — 向量贡献到综合分的权重

调阈值前请：

1. 在 `demo/tests/test_smoke.py` 加你的边角 case
2. 跑测试，量化"调高/调低对召回率/误报率的影响"
3. PR 里附测试结果对比

---

## 改进 UI / 文档

UI 改动请先在本地启动 demo（`python demo/nju_guardian.py`）确认效果再提 PR。截图最好附在 PR 里。

文档错别字、链接失效、过时说明等小修小补直接 PR 即可。

---

## 报 bug

请提交 [Issue](../../issues)，并带上：

- 你的输入文本（可脱敏）
- 期望的检测结果
- 实际拿到的结果（含截图）
- Python 版本 + OS

---

## 行为准则

- 校园反诈是严肃议题。请勿提交基于虚构、调侃或试图绕过检测的 case
- 不在 issue / PR 中泄露任何真实受害者的个人信息
- 涉及法律边界的内容（如帮信罪界定）以官方文件为准

---

## 联系方式

- **作者**：作者 · 南京大学
- **联系**：通过 GitHub Issue 提交
- 需要了解项目背景请看顶层 [README.md](./README.md) 和 [docs/application_summary.md](./docs/application_summary.md)
