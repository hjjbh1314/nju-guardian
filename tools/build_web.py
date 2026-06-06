#!/usr/bin/env python3
"""
H5 数据打包器 · NJU Guardian
=============================

把 demo/knowledge_base.json 编译成 web/kb.js（window.NJU_KB = {...}）。

为什么不用 fetch 直接读 json：
- 浏览器 file:// 下 fetch 本地 json 会被 CORS 拦（双击打不开）。
- 编译成 <script src="kb.js"> 后，双击 index.html 和 GitHub Pages 都能用。

保证 H5 与案例库【单一真相源】：改了库就重跑本脚本，H5 自动同步。

用法：python tools/build_web.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "demo" / "knowledge_base.json"
OUT = ROOT / "web" / "kb.js"

# H5 只用规则路需要的字段，瘦身（去掉 steps 之外按需保留；这里全量保留便于卡片展示）
KEEP = ("id", "type", "name", "risk_level", "keywords", "patterns",
        "script_examples", "why_scam", "advice", "emergency", "source")


def main() -> int:
    kb = json.load(KB.open(encoding="utf-8"))
    slim = [{k: c.get(k) for k in KEEP} for c in kb["cases"]]
    payload = {
        "version": kb.get("version", "0.x"),
        "updated": kb.get("updated", "—"),
        "cases": slim,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = (
        "/* 自动生成，请勿手改。改 demo/knowledge_base.json 后重跑 tools/build_web.py */\n"
        "window.NJU_KB = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    )
    OUT.write_text(js, encoding="utf-8")
    print(f"✅ 生成 {OUT}（{len(slim)} 条案例，{len(js)//1024} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
