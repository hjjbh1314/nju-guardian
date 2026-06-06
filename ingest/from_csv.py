#!/usr/bin/env python3
"""
表格录入 → 候选案例 JSON · NJU Guardian
========================================

让非技术同学也能贡献案例：填 `template.csv`（一行一条），跑本脚本，自动转成
符合 12 字段 schema 的候选 JSON，并立刻调用 validate_kb.py 做格式校验 + 与现有库去重。

数组类字段（keywords / patterns / script_examples / steps / why_scam / advice /
emergency）在单元格内用双分号 `;;` 分隔多个值。
（注意：不能用 `|`，因为正则 patterns 本身大量使用 `|` 做"或"，会被劈碎。）

用法
----
    python ingest/from_csv.py ingest/template.csv
    python ingest/from_csv.py my_cases.csv --out ingest/candidates --validate

产出：ingest/candidates/candidates_<时间戳>.json
随后人工审核 → 合并进 demo/knowledge_base.json（这步故意保留人工，见 CONTRIBUTING）。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo"
KB_PATH = DEMO_DIR / "knowledge_base.json"
sys.path.insert(0, str(DEMO_DIR))  # 复用 demo/validate_kb.py

ARRAY_FIELDS = (
    "keywords", "patterns", "script_examples",
    "steps", "why_scam", "advice", "emergency",
)
SCALAR_FIELDS = ("type", "name", "risk_level", "source")
SKIP_MARKERS = ("示例", "example", "#", "")


CELL_SEP = ";;"  # 不能用 | —— 正则 patterns 大量用 | 做"或"，会冲突


def _split_cell(val: str) -> list[str]:
    """单元格内用 ;; 分隔，去空白与空项。"""
    return [p.strip() for p in (val or "").split(CELL_SEP) if p.strip()]


def _next_id(existing: list[dict]) -> int:
    nums = [int(c["id"].split("-")[1]) for c in existing
            if isinstance(c.get("id"), str) and c["id"].startswith("KB-")]
    return (max(nums) + 1) if nums else 1


def load_existing_cases() -> list[dict]:
    if not KB_PATH.exists():
        return []
    with KB_PATH.open(encoding="utf-8") as f:
        return json.load(f).get("cases", [])


def rows_to_cases(csv_path: Path, existing: list[dict]) -> list[dict]:
    cases: list[dict] = []
    next_num = _next_id(existing)
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for lineno, row in enumerate(reader, start=2):
            id_cell = (row.get("id") or "").strip()
            # 跳过示例行 / 空行
            if any(id_cell.startswith(m) for m in SKIP_MARKERS if m) or not (row.get("type") or "").strip():
                continue

            case: dict = {}
            # id：留空则自动递增，填了就沿用（但必须 KB-NNN）
            if id_cell and id_cell.startswith("KB-"):
                case["id"] = id_cell
            else:
                case["id"] = f"KB-{next_num:03d}"
                next_num += 1

            for fld in SCALAR_FIELDS:
                case[fld] = (row.get(fld) or "").strip()
            for fld in ARRAY_FIELDS:
                case[fld] = _split_cell(row.get(fld, ""))

            # 字段顺序对齐 schema，方便人工 diff
            ordered = {k: case[k] for k in
                       ("id", "type", "name", "risk_level", "keywords", "patterns",
                        "script_examples", "steps", "why_scam", "advice",
                        "emergency", "source") if k in case}
            cases.append(ordered)
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="表格 → 候选案例 JSON")
    ap.add_argument("csv_path", help="输入 CSV（参照 ingest/template.csv 格式）")
    ap.add_argument("--out", default=str(ROOT / "ingest" / "candidates"),
                    help="候选 JSON 输出目录")
    ap.add_argument("--no-validate", action="store_true", help="跳过格式校验")
    ap.add_argument("--stamp", default=None,
                    help="输出文件名时间戳（默认取当前时间；CI/可复现场景可显式传入）")
    args = ap.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"找不到 CSV：{csv_path}", file=sys.stderr)
        return 2

    existing = load_existing_cases()
    cases = rows_to_cases(csv_path, existing)
    if not cases:
        print("没有解析到任何案例（示例行/空行已跳过）。请检查 CSV 是否填了内容。")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = args.stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"candidates_{stamp}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)

    print(f"✅ 解析 {len(cases)} 条候选 → {out_path}")
    print(f"   新分配 id：{[c['id'] for c in cases]}")

    if args.no_validate:
        return 0

    # 立刻校验（复用 demo/validate_kb.py），并与现有库交叉去重
    print("\n--- 格式校验 ---")
    from validate_kb import Report, check_collisions, load_schema, validate_case

    schema = load_schema()
    rep = Report()
    for c in cases:
        validate_case(c, schema, rep)
    check_collisions(cases, existing, rep)

    for w in rep.warns:
        print(f"⚠️  {w}")
    for e in rep.errors:
        print(f"❌ {e}")
    if rep.errors:
        print(f"\n校验未通过：{len(rep.errors)} error / {len(rep.warns)} warn —— 修正 CSV 后重跑")
        return 1
    print(f"\n✅ 候选全部合规（{len(rep.warns)} warn），可进入人工审核 → 合并")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
