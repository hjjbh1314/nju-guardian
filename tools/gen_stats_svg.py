#!/usr/bin/env python3
"""
案例库统计图生成器 · NJU Guardian
===================================

从 demo/knowledge_base.json 自动生成一张 SVG 概览图（总数 / 风险分布 / 反诈要点覆盖 /
类型数），写到 assets/kb_stats.svg，供 README 嵌入。

妙处：案例库长大后重跑一次，图就自动更新——直观体现"会自己长大"。纯标准库，无需 matplotlib。

用法：
    python tools/gen_stats_svg.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB_PATH = ROOT / "demo" / "knowledge_base.json"
OUT = ROOT / "assets" / "kb_stats.svg"

RISK_ORDER = ["high", "medium-high", "medium", "low-medium", "low"]
RISK_LABEL = {
    "high": "高危 high",
    "medium-high": "中高 medium-high",
    "medium": "中危 medium",
    "low-medium": "中低 low-medium",
    "low": "低危 low",
}
RISK_COLOR = {
    "high": "#C0392B",
    "medium-high": "#C0892E",
    "medium": "#D4A24E",
    "low-medium": "#6E8B5E",
    "low": "#6E8B5E",
}


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def load_stats() -> dict:
    kb = json.load(KB_PATH.open(encoding="utf-8"))
    cases = kb["cases"]
    risk = Counter(c.get("risk_level", "?") for c in cases)
    eight = set()
    for c in cases:
        for w in c.get("why_scam", []):
            m = re.search(r"反诈预警要点.*?第([一二三四五六七八12345678])条", w)
            if m:
                eight.add(m.group(1))
    return {
        "total": len(cases),
        "risk": risk,
        "types": len({c.get("type") for c in cases}),
        "eight": len(eight),
        "version": kb.get("version", "0.x"),
        "updated": kb.get("updated", "—"),
    }


def build_svg(s: dict) -> str:
    W, H = 760, 328
    pad = 32
    bar_x = 210          # 条形起点
    bar_w_max = 470      # 条形最大宽
    total = max(s["total"], 1)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
    )
    parts.append(f'<rect width="{W}" height="{H}" rx="14" fill="#F5F0E6" stroke="#E3DCCB"/>')
    # 标题
    parts.append(f'<text x="{pad}" y="42" font-size="22" font-weight="700" fill="#1A1714">'
                 f'🛡 南大数智安全官 · 案例库概览</text>')
    parts.append(f'<text x="{pad}" y="64" font-size="12" fill="#8a8a9a">'
                 f'v{esc(s["version"])} · 更新 {esc(s["updated"])} · 自动生成自 knowledge_base.json</text>')

    # 顶部三个大数字
    cards = [("案例类型", s["types"]), ("案例总数", s["total"]), ("反诈要点覆盖", f'{s["eight"]}/8')]
    cw = (W - 2 * pad - 2 * 14) / 3
    for i, (label, val) in enumerate(cards):
        cx = pad + i * (cw + 14)
        parts.append(f'<rect x="{cx:.0f}" y="80" width="{cw:.0f}" height="66" rx="10" '
                     f'fill="#EFE8DA" stroke="#E3DCCB"/>')
        parts.append(f'<text x="{cx + cw/2:.0f}" y="118" font-size="30" font-weight="800" '
                     f'fill="#C0392B" text-anchor="middle">{esc(str(val))}</text>')
        parts.append(f'<text x="{cx + cw/2:.0f}" y="137" font-size="12" fill="#6a6a7a" '
                     f'text-anchor="middle">{esc(label)}</text>')

    # 风险分布横条
    parts.append(f'<text x="{pad}" y="182" font-size="14" font-weight="700" fill="#1A1714">'
                 f'风险等级分布</text>')
    y = 198
    row_h = 30
    for rl in RISK_ORDER:
        n = s["risk"].get(rl, 0)
        if n == 0 and rl == "low":
            continue
        w = bar_w_max * n / total
        parts.append(f'<text x="{pad}" y="{y+15}" font-size="12" fill="#4a4a5a">'
                     f'{esc(RISK_LABEL[rl])}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{bar_w_max}" height="20" rx="5" fill="#E3DCCB"/>')
        if w > 0:
            parts.append(f'<rect x="{bar_x}" y="{y}" width="{w:.1f}" height="20" rx="5" '
                         f'fill="{RISK_COLOR[rl]}"/>')
        parts.append(f'<text x="{bar_x + max(w,0) + 8:.0f}" y="{y+15}" font-size="12" '
                     f'font-weight="700" fill="#1A1714">{n}</text>')
        y += row_h

    parts.append('</svg>')
    return "\n".join(parts)


def main() -> int:
    s = load_stats()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_svg(s), encoding="utf-8")
    print(f"✅ 生成 {OUT}")
    print(f"   总数 {s['total']} · 类型 {s['types']} · 反诈预警要点 {s['eight']}/8 · "
          f"风险 {dict(s['risk'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
