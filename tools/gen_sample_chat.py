#!/usr/bin/env python3
"""
生成演示用"诈骗聊天截图"样图 · NJU Guardian
=============================================

为 H5 的"截图识诈"功能造一张干净、清晰的合成诈骗聊天图，供现场演示 OCR。
干净渲染 + 大字号 → tesseract.js 识别成功率高；即便识别失败，H5 也内置了已知文本兜底。

输出：web/sample_chat.png
用法：python tools/gen_sample_chat.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "sample_chat.png"

# 演示样图里的"诈骗话术"。H5 用它做 OCR 失败时的兜底文本，需与图中文字一致。
LINES = [
    ("来电", "您的账户涉嫌异常交易，需立即配合审查"),
    ("来电", "请下载会议软件并共享屏幕"),
    ("来电", "按我的指示操作并报出短信验证码"),
    ("来电", "否则一切后果自行承担"),
]
SAMPLE_TEXT = "您的账户涉嫌异常交易，需立即配合审查 请下载会议软件并共享屏幕 按我的指示操作并报出短信验证码，否则一切后果自行承担"


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in ("/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/Songti.ttc",
              "/System/Library/Fonts/STHeiti Medium.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main() -> int:
    W = 720
    pad = 28
    bubble_font = load_font(30)
    name_font = load_font(20)

    # 预估高度
    line_h = 86
    H = 150 + len(LINES) * line_h + 40
    img = Image.new("RGB", (W, H), "#ebebf0")
    d = ImageDraw.Draw(img)

    # 顶部聊天栏
    d.rectangle([0, 0, W, 92], fill="#f6f6f8")
    d.text((pad, 32), "< 银行客服（仿冒）", font=load_font(26), fill="#1a1a2e")
    d.line([0, 92, W, 92], fill="#dcdce4", width=2)

    y = 120
    for _name, text in LINES:
        # 头像
        d.ellipse([pad, y, pad + 52, y + 52], fill="#c0392b")
        d.text((pad + 14, y + 12), "客", font=name_font, fill="#fff")
        # 气泡
        tx0 = pad + 70
        tw = W - tx0 - pad
        d.rounded_rectangle([tx0, y, tx0 + tw, y + 62], radius=14, fill="#ffffff")
        d.text((tx0 + 16, y + 16), text, font=bubble_font, fill="#1a1a2e")
        y += line_h

    img.save(OUT)
    print(f"✅ 生成 {OUT}（{W}x{H}）")
    print(f"   样图文本（H5 兜底用）：{SAMPLE_TEXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
