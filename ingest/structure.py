#!/usr/bin/env python3
"""
结构化层 · NJU Guardian 采集管线 Step 2（示范用）
===================================================

把 fetch.py 抓到的 raw 正文，用 LLM 自动结构化成符合 12 字段 schema 的候选案例，
随后交给 validate_kb.py 校验。重点：学生/校园类。

三种运行模式（自动选择）：
1. 有 ANTHROPIC_API_KEY + 装了 anthropic → 调 Claude 自动结构化（prompt 缓存 schema 块）
2. 无 key/SDK → 降级：把 raw 预填进一个 CSV，接回 from_csv.py 的人工通道
3. --demo → 直接展示 ingest/raw/sample_campus_scam.json 经本步产出的范例候选，
   现场离线也能演示"原文→结构化候选"的效果

用法
----
    export ANTHROPIC_API_KEY=sk-...           # 有 key 走全自动
    python ingest/structure.py raw_xxx.json    # 结构化 + 校验
    python ingest/structure.py --demo          # 离线演示效果
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo"
RAW_DIR = ROOT / "ingest" / "raw"
CAND_DIR = ROOT / "ingest" / "candidates"
SCHEMA = DEMO_DIR / "case_schema.json"
KB_PATH = DEMO_DIR / "knowledge_base.json"
sys.path.insert(0, str(DEMO_DIR))

MODEL = os.environ.get("NJU_STRUCTURE_MODEL", "claude-sonnet-4-6")

SYSTEM_INSTRUCTION = """你是反诈案例结构化助手。把给定的【公开反诈材料正文】改写、提炼成一条结构化诈骗案例 JSON。

铁律：
- 必须【改写】，不得逐字复制原文。
- 不得虚构原文中没有的事实、数字、机构名。
- 只输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块。
- 字段严格遵循下方 schema；数组字段条数落在 schema 的 min/max 内。
- keywords 8-12 个、每个 2-8 字、禁止单字。
- patterns 1-2 条合法 Python 正则。
- advice 每条动词开头、尽量 ≤25 字。
- emergency 至少含一个号码（96110/110/12381 等）。
- source 用调用方提供的来源短标，保持可核验。
- id 留空字符串，由后续流程分配。

schema：
"""


def build_prompt(raw: dict, schema: dict) -> tuple[str, str]:
    system = SYSTEM_INSTRUCTION + json.dumps(schema, ensure_ascii=False, indent=2)
    user = (
        f"来源短标：{raw.get('tag','')}\n"
        f"来源URL：{raw.get('url','')}\n"
        f"标题：{raw.get('title','')}\n\n"
        f"正文：\n{raw.get('text','')}\n\n"
        "请据此产出一条结构化诈骗案例 JSON。若正文不是诈骗案例（如纯通知），返回 {\"skip\": true}。"
    )
    return system, user


def structure_with_llm(records: list[dict], schema: dict) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic()
    out = []
    for raw in records:
        system, user = build_prompt(raw, schema)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],  # schema 块缓存，多条复用
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            print(f"  ⚠️ LLM 输出非 JSON，跳过：{raw.get('url')}", file=sys.stderr)
            continue
        if obj.get("skip"):
            print(f"  ↷ 非案例，跳过：{raw.get('title','')[:30]}")
            continue
        obj["source"] = obj.get("source") or raw.get("tag", "")
        out.append(obj)
    return out


def fallback_to_csv(records: list[dict]) -> Path:
    """无 key 时：把 raw 预填进 CSV，接回 from_csv.py 人工通道。"""
    import csv

    out = ROOT / "ingest" / f"to_fill_{datetime.now():%Y%m%d_%H%M%S}.csv"
    cols = ["id", "type", "name", "risk_level", "keywords", "patterns",
            "script_examples", "steps", "why_scam", "advice", "emergency", "source"]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in records:
            # 已知的先填：name←标题，source←tag+url，script_examples←正文前两段
            segs = [s for s in r.get("text", "").split("\n") if len(s) > 8][:2]
            w.writerow(["", "", r.get("title", "")[:30], "", "", "",
                        ";;".join(segs), "", "", "", "96110",
                        f"{r.get('tag','')}（{r.get('url','')}）"])
    return out


def assign_ids_and_save(cands: list[dict]) -> Path:
    existing = json.load(KB_PATH.open(encoding="utf-8")).get("cases", []) if KB_PATH.exists() else []
    nums = [int(c["id"].split("-")[1]) for c in existing if str(c.get("id", "")).startswith("KB-")]
    nxt = (max(nums) + 1) if nums else 1
    for c in cands:
        if not c.get("id"):
            c["id"] = f"KB-{nxt:03d}"
            nxt += 1
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    out = CAND_DIR / f"candidates_{datetime.now():%Y%m%d_%H%M%S}.json"
    json.dump(cands, out.open("w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


def validate(cands: list[dict]) -> bool:
    from validate_kb import Report, check_collisions, load_schema, validate_case
    existing = json.load(KB_PATH.open(encoding="utf-8")).get("cases", []) if KB_PATH.exists() else []
    rep = Report()
    for c in cands:
        validate_case(c, load_schema(), rep)
    check_collisions(cands, existing, rep)
    for w in rep.warns:
        print(f"  ⚠️ {w}")
    for e in rep.errors:
        print(f"  ❌ {e}")
    return rep.ok


def main() -> int:
    ap = argparse.ArgumentParser(description="raw 正文 → LLM 结构化候选案例")
    ap.add_argument("raw_file", nargs="?", help="ingest/raw 下的文件名或路径")
    ap.add_argument("--demo", action="store_true", help="离线演示：用 sample_campus_scam.json")
    args = ap.parse_args()

    schema = json.load(SCHEMA.open(encoding="utf-8"))

    if args.demo:
        sample = RAW_DIR / "sample_campus_scam.json"
        if not sample.exists():
            print(f"缺少演示样本 {sample}", file=sys.stderr)
            return 2
        records = json.load(sample.open(encoding="utf-8"))
    elif args.raw_file:
        p = Path(args.raw_file)
        if not p.exists():
            p = RAW_DIR / args.raw_file
        records = json.load(p.open(encoding="utf-8"))
    else:
        ap.error("给一个 raw 文件，或用 --demo")

    students = [r for r in records if r.get("student_related")]
    print(f"输入 {len(records)} 条 raw（学生相关 {len(students)} 条，优先结构化）")
    records = students or records

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    try:
        import anthropic  # noqa
        has_sdk = True
    except ImportError:
        has_sdk = False

    # 离线演示且无 key：直接展示该原文经 LLM 结构化的范例产物，让效果可见。
    # 配置 ANTHROPIC_API_KEY 后，--demo 会走下方真实 LLM 路径现场重生成。
    if args.demo and not (has_key and has_sdk):
        expected = CAND_DIR / "demo_expected.json"
        cands = json.load(expected.open(encoding="utf-8"))
        print(f"→ 离线演示：展示原文经 LLM 结构化后的范例候选（配 API key 可现场实时重生成）")
        out = assign_ids_and_save(cands)
        print(f"\n✅ {len(cands)} 条候选 → {out}")
        print(f"   分配 id：{[c['id'] for c in cands]}")
        c0 = cands[0]
        print(f"\n   原文「{records[0]['title'][:24]}…」→ 结构化为：")
        print(f"     类型：{c0['type']}  风险：{c0['risk_level']}")
        print(f"     关键词：{'、'.join(c0['keywords'][:6])}…（{len(c0['keywords'])}个）")
        print(f"     来源：{c0['source']}")
        print("\n--- 格式校验 ---")
        ok = validate(cands)
        print(("\n✅ 候选合规，进入人工审核 → 合并（库 50 → 51）" if ok else "\n❌ 校验未过"))
        return 0 if ok else 1

    if has_key and has_sdk:
        print(f"→ LLM 自动结构化（{MODEL}）…")
        cands = structure_with_llm(records, schema)
    else:
        why = "未设 ANTHROPIC_API_KEY" if not has_key else "未装 anthropic"
        print(f"→ 降级人工通道（{why}）")
        csv_path = fallback_to_csv(records)
        print(f"  已预填 → {csv_path}")
        print(f"  补全后跑：python ingest/from_csv.py {csv_path.name}")
        return 0

    if not cands:
        print("没有产出候选。")
        return 1
    out = assign_ids_and_save(cands)
    print(f"\n✅ {len(cands)} 条候选 → {out}")
    print(f"   分配 id：{[c['id'] for c in cands]}")
    print("\n--- 格式校验 ---")
    ok = validate(cands)
    print(("\n✅ 候选合规，进入人工审核 → 合并" if ok else "\n❌ 校验未过，需修正"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
