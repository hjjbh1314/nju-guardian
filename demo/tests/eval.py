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


# ---------------------------------------------------------------------------
# 泛化评测：第三路『行为红旗』对未知骗局的预警增益
# ---------------------------------------------------------------------------
_RANK = {"low-medium": 1, "medium": 2, "high": 3}


def _top_rule_score(text: str, cases: list[dict]) -> float:
    t = text.lower()
    best = 0.0
    for c in cases:
        kw = sum(1 for k in c.get("keywords", []) if k.lower() in t)
        pt = 0
        for p in c.get("patterns", []):
            try:
                if re.search(p, text, re.IGNORECASE):
                    pt += 1
            except re.error:
                pass
        best = max(best, kw * 1.0 + pt * 1.5)
    return best


def _rule_level(rs: float):
    if rs >= 3.0:
        return "high"
    if rs >= 1.5:
        return "medium"
    if rs >= 1.0:
        return "low-medium"
    return None


def combined_level(text: str, cases: list[dict], use_signals: bool):
    """规则路(+可选行为红旗)给出的风险等级。无向量(CI 友好)。"""
    lvl = _rule_level(_top_rule_score(text, cases))
    if use_signals:
        from fraud_signals import behavior_assessment, extract_signals
        _, bl = behavior_assessment(extract_signals(text))
        if bl and (lvl is None or _RANK[bl] > _RANK[lvl]):
            lvl = bl
    return lvl


def run_generalization(cases: list[dict]) -> None:
    samples = load("tests/eval_generalization.json")["samples"]
    n = len(samples)
    rule_only = sum(1 for s in samples if combined_level(s["text"], cases, False))
    three_way = sum(1 for s in samples if combined_level(s["text"], cases, True))
    print("\n" + "=" * 52)
    print(f"泛化评测 · 未知骗局预警覆盖（{n} 条案例库未直接覆盖样本）")
    print("-" * 52)
    print(f"  双路（规则+语义）：{rule_only}/{n} = {rule_only/n:.0%} 给出预警")
    print(f"  三路（+行为红旗）：{three_way}/{n} = {three_way/n:.0%} 给出预警")
    print(f"  → 第三路净增覆盖：+{(three_way-rule_only)/n:.0%}")
    misses = [s for s in samples if not combined_level(s["text"], cases, True)]
    if misses:
        print("  仍未预警：")
        for s in misses:
            print(f"    · {s['text'][:24]}…")


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

    run_generalization(cases)

    if args.min_top3 is not None and top3 / n < args.min_top3:
        print(f"\n❌ Top-3 召回率 {top3/n:.0%} 低于阈值 {args.min_top3:.0%}（疑似回归）")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
