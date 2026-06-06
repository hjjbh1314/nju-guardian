#!/usr/bin/env python3
"""
案例库格式校验器 · NJU Guardian
=================================

把 CONTRIBUTING.md 里的字段规范变成"可执行的格式检查"。这是评委建议爬取扩库后
保证质量的第一道闸门：任何新案例（人工录入或自动采集）入库前都必须过这关。

特性
----
- 纯标准库，无需 torch / sentence-transformers，可直接进 CI。
- 规则来自 case_schema.json（单一真相源）+ 本文件的语义规则（正则可编译、来源可核验、
  建议字数、关键词非单字、紧急号码、跨案例去重）。
- 友好分级报错：ERROR 阻断入库，WARN 提示但放行。
- 既能校验整库，也能校验"候选"文件（自动采集产出的待审案例）。

用法
----
    python demo/validate_kb.py                          # 校验 knowledge_base.json 全库
    python demo/validate_kb.py path/to/candidates.json  # 校验候选文件（list 或单条 dict）
    python demo/validate_kb.py --against demo/knowledge_base.json candidates.json
                                                        # 候选 + 与现有库交叉查重
    python demo/validate_kb.py --quiet                  # 只输出结果与错误，CI 友好

退出码：0 = 全部通过（可有 WARN）；1 = 存在 ERROR。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = DEMO_DIR / "case_schema.json"
DEFAULT_KB = DEMO_DIR / "knowledge_base.json"

# 不可核验来源黑名单（命中即 ERROR）
SOURCE_BLACKLIST = ("tbd", "todo", "待补", "内部材料", "微信群", "聊天记录", "截图", "知乎", "贴吧", "未公开", "—", "无")
PLACEHOLDER_TEXT = {"", "—", "tbd", "todo", "xxx", "待补充", "示例"}
PHONE_RE = re.compile(r"\d{3,}")
URL_RE = re.compile(r"https?://|[a-z0-9-]+\.(com|cn|org|gov|net|edu)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 报告容器
# ---------------------------------------------------------------------------
class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []

    def err(self, cid: str, msg: str) -> None:
        self.errors.append(f"[{cid}] {msg}")

    def warn(self, cid: str, msg: str) -> None:
        self.warns.append(f"[{cid}] {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# 规则加载
# ---------------------------------------------------------------------------
def load_schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _len_rules(schema: dict, field: str) -> tuple[int | None, int | None]:
    """从 schema 取数组字段的 minItems / maxItems。"""
    p = schema["properties"].get(field, {})
    return p.get("minItems"), p.get("maxItems")


# ---------------------------------------------------------------------------
# 单条案例校验
# ---------------------------------------------------------------------------
def validate_case(case: dict, schema: dict, rep: Report) -> None:
    cid = case.get("id", "?")
    props = schema["properties"]
    required = schema["required"]

    # 1) 必填字段存在且非空
    for f in required:
        v = case.get(f)
        if v is None or (isinstance(v, (str, list)) and len(v) == 0):
            rep.err(cid, f"缺少或为空的必填字段：{f}")

    # 2) 不允许的多余字段
    for f in case:
        if f not in props:
            rep.warn(cid, f"未知字段 '{f}'（schema 未定义，建议移除或先扩展 schema）")

    # 3) id 格式
    if not re.match(r"^KB-\d{3}$", str(case.get("id", ""))):
        rep.err(cid, f"id 格式应为 KB-NNN，实际：{case.get('id')!r}")

    # 4) risk_level 枚举
    rl_enum = props["risk_level"]["enum"]
    if case.get("risk_level") not in rl_enum:
        rep.err(cid, f"risk_level 须属于 {rl_enum}，实际：{case.get('risk_level')!r}")

    # 5) keywords：数量 + 单字检测
    kws = case.get("keywords", []) or []
    lo, hi = _len_rules(schema, "keywords")
    if lo and len(kws) < lo:
        rep.warn(cid, f"keywords 仅 {len(kws)} 个，建议 ≥ {lo}（召回不足）")
    if hi and len(kws) > hi:
        rep.warn(cid, f"keywords 多达 {len(kws)} 个，建议 ≤ {hi}（易误命中）")
    for k in kws:
        if len(k) < 2:
            rep.err(cid, f"单字关键词 '{k}' 会大量误命中，禁止")

    # 6) patterns：数量 + 正则可编译
    pts = case.get("patterns", []) or []
    lo, hi = _len_rules(schema, "patterns")
    if lo and len(pts) < lo:
        rep.err(cid, f"patterns 至少 {lo} 条，实际 {len(pts)}")
    if hi and len(pts) > hi:
        rep.warn(cid, f"patterns 多达 {len(pts)} 条，建议 ≤ {hi}")
    for pt in pts:
        try:
            re.compile(pt)
        except re.error as e:
            rep.err(cid, f"非法正则 {pt!r}：{e}")

    # 7) 数组类字段数量区间（script_examples / steps / why_scam / advice）
    for field in ("script_examples", "steps", "why_scam", "advice"):
        arr = case.get(field, []) or []
        lo, hi = _len_rules(schema, field)
        if lo and len(arr) < lo:
            rep.err(cid, f"{field} 至少 {lo} 条，实际 {len(arr)}")
        if hi and len(arr) > hi:
            rep.warn(cid, f"{field} 多达 {len(arr)} 条，建议 ≤ {hi}")

    # 8) advice 字数（含电话/网址的条目豁免——号码和域名天然占字数，强压会丢信息）
    for a in case.get("advice", []) or []:
        carries_contact = bool(PHONE_RE.search(a)) or bool(URL_RE.search(a))
        if len(a) > 25 and not carries_contact:
            rep.warn(cid, f"advice 超 25 字（{len(a)} 字）：{a[:18]}…")

    # 9) emergency 至少一条含号码
    emg = case.get("emergency", []) or []
    if not any(PHONE_RE.search(str(e)) for e in emg):
        rep.err(cid, "emergency 必须至少包含一个可识别号码（如 96110 / 110 / 12381）")

    # 10) source 可核验
    src = str(case.get("source", "")).strip()
    if src.lower() in PLACEHOLDER_TEXT:
        rep.err(cid, "source 为空或占位符，必须给出可核验的公开来源")
    else:
        for bad in SOURCE_BLACKLIST:
            if bad in src.lower():
                rep.err(cid, f"source 含不可核验来源关键词 '{bad}'：{src}")
                break


# ---------------------------------------------------------------------------
# 跨案例：重复 id / 近似重复
# ---------------------------------------------------------------------------
def _kw_set(case: dict) -> set[str]:
    return set(case.get("keywords", []) or []) | {case.get("type", "")}


def check_collisions(cases: list[dict], existing: list[dict], rep: Report) -> None:
    seen_ids: dict[str, int] = {}
    for i, c in enumerate(existing + cases):
        cid = c.get("id", "?")
        if cid in seen_ids:
            rep.err(cid, "id 与库中其它案例重复")
        seen_ids[cid] = i

    # 近似重复：新案例与（现有库 + 其它新案例）关键词重合度过高
    pool = existing + cases
    for c in cases:
        cset = _kw_set(c)
        if not cset:
            continue
        for other in pool:
            if other is c or other.get("id") == c.get("id"):
                continue
            oset = _kw_set(other)
            if not oset:
                continue
            overlap = len(cset & oset) / len(cset | oset)
            if overlap >= 0.7:
                rep.warn(
                    c.get("id", "?"),
                    f"与 {other.get('id')} 关键词重合 {overlap:.0%}，疑似重复，请人工确认",
                )
                break


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _extract_cases(raw) -> list[dict]:
    """支持三种输入：完整 KB(dict 带 cases) / 案例数组 / 单条案例 dict。"""
    if isinstance(raw, dict) and "cases" in raw:
        return raw["cases"]
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    raise ValueError("无法识别的文件结构：应为 KB 对象、案例数组或单条案例")


def main() -> int:
    ap = argparse.ArgumentParser(description="NJU Guardian 案例库格式校验器")
    ap.add_argument("target", nargs="?", default=str(DEFAULT_KB),
                    help="待校验文件（默认 knowledge_base.json）")
    ap.add_argument("--against", default=None,
                    help="现有库路径，用于与候选交叉查重（校验候选文件时建议带上）")
    ap.add_argument("--quiet", action="store_true", help="只输出结果与错误")
    args = ap.parse_args()

    schema = load_schema()
    target = Path(args.target)
    if not target.exists():
        print(f"找不到文件：{target}", file=sys.stderr)
        return 2

    with target.open(encoding="utf-8") as f:
        cases = _extract_cases(json.load(f))

    existing: list[dict] = []
    if args.against:
        with Path(args.against).open(encoding="utf-8") as f:
            existing = _extract_cases(json.load(f))

    rep = Report()
    for c in cases:
        validate_case(c, schema, rep)
    check_collisions(cases, existing, rep)

    if not args.quiet:
        print(f"校验目标：{target}")
        print(f"案例数：{len(cases)}" + (f"（交叉库 {len(existing)} 条）" if existing else ""))
        print("-" * 56)

    if rep.warns:
        print(f"⚠️  {len(rep.warns)} 条警告（不阻断）：")
        for w in rep.warns:
            print(f"   · {w}")
    if rep.errors:
        print(f"\n❌ {len(rep.errors)} 条错误（阻断入库）：")
        for e in rep.errors:
            print(f"   · {e}")
        print(f"\n校验未通过：{len(rep.errors)} error / {len(rep.warns)} warn")
        return 1

    print(f"\n✅ 校验通过：{len(cases)} 条全部合规" +
          (f"（{len(rep.warns)} 条警告）" if rep.warns else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
