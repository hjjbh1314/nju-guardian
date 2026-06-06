#!/usr/bin/env python3
"""
现场扫码二维码生成器 · NJU Guardian
=====================================

为 H5（web/index.html 的 GitHub Pages 地址）生成二维码，供答辩 PPT / 海报展示，
现场观众扫码即用，不依赖现场网络连演示者电脑。

依赖：segno（纯 Python，pip install segno）。可选 PNG 输出需 pillow（本机已有）。

用法：
    python tools/gen_qr.py                       # 用默认 GitHub Pages 地址
    python tools/gen_qr.py --url https://你的实际地址/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import segno

ROOT = Path(__file__).resolve().parent.parent

# 默认地址：pages.yml 把 web/ 作为站点根发布，所以 H5 在仓库 Pages 根。
# Pages 设置好后，若实际地址不同，用 --url 传入并重新生成。
DEFAULT_URL = "https://hjjbh1314.github.io/nju-guardian/"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 H5 现场扫码二维码")
    ap.add_argument("--url", default=DEFAULT_URL, help="H5 公网地址")
    ap.add_argument("--out", default=str(ROOT / "assets"), help="输出目录")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    qr = segno.make(args.url, error="h")  # 高纠错，便于打印/中心嵌 logo

    svg = out / "qr_app.svg"
    qr.save(str(svg), kind="svg", scale=8, border=2, dark="#1A1714")
    png = out / "qr_app.png"
    try:
        qr.save(str(png), kind="png", scale=10, border=2, dark="#1A1714")
        png_msg = f" + {png.name}"
    except Exception as e:  # pillow 缺失等
        png_msg = f"（PNG 跳过：{e}）"

    print(f"✅ 生成 {svg.name}{png_msg}")
    print(f"   指向：{args.url}")
    print("   ⚠️ GitHub Pages 设置好后，用 --url 传入实际地址重新生成，确保二维码可扫通。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
