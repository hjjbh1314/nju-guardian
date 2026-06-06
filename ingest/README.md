# ingest · 案例录入与采集管线

把新案例安全地送进知识库。两条通道，最后都汇到同一道**格式校验闸门**，再经**人工审核**合并。

```
                              ┌─ 人工通道：填 template.csv ──┐
                              │                              │
公开来源 ── 自动采集(Day3-5) ─┤                              ├─→ validate_kb.py 校验 + 去重
                              │                              │        │
                              └─ from_csv.py 转候选 JSON ────┘        ▼
                                                              candidates/ 暂存
                                                                     │ 人工审核
                                                                     ▼
                                                        demo/knowledge_base.json 合并
```

## 人工通道（Day 2，已可用）

给非技术同学的最快贡献方式，**不用碰 JSON**：

1. 复制 `template.csv`，按表头一行填一条案例
2. 数组字段（keywords / patterns / script_examples / steps / why_scam / advice / emergency）
   在单元格内用 **`;;`（双分号）** 分隔多个值
   - ⚠️ 不能用 `|`：正则 patterns 本身用 `|` 做"或"，会冲突
3. `id` 留空 → 自动按 `KB-NNN` 递增分配
4. 跑转换 + 校验：

   ```bash
   python ingest/from_csv.py 你的表格.csv
   ```

   - 产出 `candidates/candidates_<时间戳>.json`
   - 立刻校验格式 + 与现有库去重；有 ERROR 会打回，改完重跑
5. 人工过一遍候选 → 合并进 `demo/knowledge_base.json` → 跑 `python demo/validate_kb.py` 复核

## 不可让步的铁律（沿用 CONTRIBUTING.md）

- 来源必须**公开可核验**（政府/央媒/高校保卫处公开推文），`source` 字段不得为 TBD/内部材料/群截图
- 案例话术必须**改写**，不得逐字复制
- 合并这一步**故意保留人工**——这是"可审计、不污染"的护城河，不是偷懒

## 自动采集通道（Day 3-5，示范版已可跑）

> 定位：**功能示范**，现场展示"会自己长大"的效果即可，不追求真日更。

- `fetch.py <URL>`：抓公开文章正文（requests+bs4，真实联网，自动标"学生相关"）
- `structure.py raw_xxx.json`：LLM 自动结构化成 12 字段候选
  - 有 `ANTHROPIC_API_KEY`（且 `pip install anthropic`）→ 调 Claude 全自动
  - 没 key → 降级：预填 CSV 接回上面的人工通道
  - `--demo` → 离线展示"公开原文 → LLM 结构化 → 校验 → 库+1"完整效果
- `sources.json`：公开来源注册表，团队往里加真实文章 URL（重点学生类）

### 现场一键演示

```bash
bash ingest/demo.sh
```

跑完展示：当前库规模 → 全库校验 → 采集 → 原文结构化为新案例 → 校验通过 → 人工审核闭环。

### 配 key 后全自动（可选）

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python ingest/fetch.py <公开文章URL> --tag "来源短标"
python ingest/structure.py raw_<时间戳>.json   # → candidates/ → 人工审核合并
```
