#!/usr/bin/env python3
"""
检测命中率评测 · NJU Guardian
===============================

在固定评测集（eval_set.json）上算检测指标，给答辩提供【可量化】证据：
- Top-1 准确率：最高分案例正好是期望案例的比例
- Top-3 召回率：期望案例出现在前 3 名的比例
- 未召回：完全没进前 3 的样本（这些正是规则路短板、向量召回的价值所在）

默认只评【规则路】（关键词+正则，与 H5 一致、CI 无需模型）。
加 --vector 评双路融合（需已下载 BGE/TF-IDF，本地可跑）。

用法：
    python demo/tests/eval.py            # 规则路
    python demo/tests/eval.py --vector   # 双路融合
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO_DIR))


def load(name: str):
    with (DEMO_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


def rule_detect(text: str, cases: list[dict], top_k: int = 3) -> list[str]:
    scored = []
    t = text.lower()
    for c in cases:
        kw = [k for k in c.get("keywords", []) if k.lower() in t]
        pt = 0
        for p in c.get("patterns", []):
            try:
                if re.search(p, text, re.IGNORECASE):
                    pt += 1
            except re.error:
                pass
        score = len(kw) * 1.0 + pt * 1.5
        if score >= 1.0:
            scored.append((c["id"], score))
    scored.sort(key=lambda x: -x[1])
    return [cid for cid, _ in scored[:top_k]]


def vector_detect(text: str, top_k: int = 3) -> list[str]:
    from nju_guardian import detect  # 双路融合入口
    return [m.case["id"] for m in detect(text, top_k=top_k)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", action="store_true", help="评双路融合（需模型）")
    ap.add_argument("--min-top3", type=float, default=None,
                    help="Top-3 召回率低于此值则退出码 1（CI 回归闸门，如 0.75）")
    args = ap.parse_args()

    cases = load("knowledge_base.json")["cases"]
    samples = load("tests/eval_set.json")["samples"]
    n = len(samples)

    top1 = top3 = 0
    misses = []
    for s in samples:
        ids = (vector_detect(s["text"]) if args.vector
               else rule_detect(s["text"], cases))
        exp = s["expect"]
        if ids and ids[0] == exp:
            top1 += 1
        if exp in ids:
            top3 += 1
        else:
            misses.append((exp, s["text"]))

    mode = "双路融合（规则+向量）" if args.vector else "规则路（关键词+正则）"
    print(f"评测集：{n} 条 · 模式：{mode}")
    print("-" * 52)
    print(f"  Top-1 准确率：{top1}/{n} = {top1/n:.0%}")
    print(f"  Top-3 召回率：{top3}/{n} = {top3/n:.0%}")
    if misses:
        print(f"\n  未进前3（{len(misses)} 条，规则路短板→向量召回的价值）：")
        for exp, text in misses:
            print(f"    · 期望 {exp}：{text[:28]}…")

    if args.min_top3 is not None and top3 / n < args.min_top3:
        print(f"\n❌ Top-3 召回率 {top3/n:.0%} 低于阈值 {args.min_top3:.0%}（疑似回归）")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
