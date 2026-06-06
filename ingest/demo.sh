#!/usr/bin/env bash
# 答辩现场演示：一条命令跑完「自增长案例库」全链路
# 用法：bash ingest/demo.sh
set -e
cd "$(dirname "$0")/.."

line() { printf '\n\033[1;36m── %s ──\033[0m\n' "$1"; }

line "1) 当前案例库规模"
python3 -c "import json;print('  现有', len(json.load(open('demo/knowledge_base.json'))['cases']), '类案例')"

line "2) 格式治理：校验全库（任何漂移会被拦下）"
python3 demo/validate_kb.py --quiet | tail -1

line "3) 采集：抓取一个公开来源的正文（真实联网）"
echo "  （演示可跑：python3 ingest/fetch.py <公开文章URL> --tag 来源短标）"
echo "  本机示范用已抓样本，跳过实时联网以保证现场稳定。"

line "4) 结构化 + 校验：公开原文 → LLM 自动成 12 字段 → 校验 → 入库候选"
python3 ingest/structure.py --demo

line "5) 统计图 + H5 数据自动刷新（案例库长大，图和小程序数据都跟着更新）"
python3 tools/gen_stats_svg.py
python3 tools/build_web.py

line "6) 人工审核闭环"
cat <<'EOF'
  候选落在 ingest/candidates/，由人工过目改写后合并进 knowledge_base.json。
  这一步【故意保留人工】——可审计、不污染，是我们方案的护城河。

  一句话：初赛是 50 条静态案例；决赛是一套「采集→结构化→校验→去重→人工审核」
  会自己长大的反诈知识系统。冷启动不再是问题，因为它每天都能变强。
EOF
