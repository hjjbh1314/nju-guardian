#!/usr/bin/env python3
"""
抓取层 · NJU Guardian 采集管线 Step 1（示范用）
=================================================

把一个【公开可访问】的反诈文章 URL 抓下来、抽出正文，产出一条 raw 记录给后续
LLM 结构化（structure.py）使用。重点关注学生/校园类内容。

设计取向：这是【功能示范】，不是抗造的日更爬虫。现场演示"抓取"这一步真实可跑即可。

用法
----
    python ingest/fetch.py <文章URL> --tag "国家反诈中心·公开提示"
    python ingest/fetch.py --all          # 遍历 sources.json 里 enabled 的源

产出：ingest/raw/raw_<时间戳>.json（title / text / url / tag / fetched_at / student_related）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "ingest" / "raw"
SOURCES = ROOT / "ingest" / "sources.json"

# 学生/校园相关性过滤词（命中即标 student_related=True，优先入库）
STUDENT_HINTS = (
    "学生", "大学", "高校", "校园", "同学", "新生", "迎新", "学费", "助学金",
    "奖学金", "导师", "辅导员", "教务", "兼职", "实习", "论文", "考试", "四六级",
    "考研", "校园贷", "宿舍", "选课", "学籍", "毕业", "留学",
)

# header 只能用 latin-1，UA 保持纯 ASCII
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) NJUGuardian-ingest/0.1 (+public anti-fraud case collection)"


def extract_main_text(html: str) -> tuple[str, str]:
    """返回 (title, 正文文本)。去脚本/样式，优先取 <article>/<p>。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        bad.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    container = soup.find("article") or soup.body or soup
    paras = [p.get_text(" ", strip=True) for p in container.find_all(["p", "li", "h2", "h3"])]
    paras = [p for p in paras if len(p) >= 8]
    text = "\n".join(paras)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


def fetch_one(url: str, tag: str) -> dict | None:
    import requests

    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
    except Exception as e:
        print(f"  ❌ 抓取失败 {url}：{e}", file=sys.stderr)
        return None

    title, text = extract_main_text(resp.text)
    if len(text) < 40:
        print(f"  ⚠️ 正文过短（{len(text)} 字），可能是 JS 渲染页或非文章页：{url}", file=sys.stderr)
    blob = title + text
    student = any(h in blob for h in STUDENT_HINTS)
    return {
        "title": title,
        "text": text[:6000],
        "url": url,
        "tag": tag,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "student_related": student,
    }


def load_sources() -> list[dict]:
    with SOURCES.open(encoding="utf-8") as f:
        return [s for s in json.load(f).get("sources", []) if s.get("enabled")]


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取公开反诈文章正文")
    ap.add_argument("url", nargs="?", help="文章 URL")
    ap.add_argument("--tag", default="公开来源·待标注", help="来源短标")
    ap.add_argument("--all", action="store_true", help="遍历 sources.json 中 enabled 的源")
    args = ap.parse_args()

    jobs: list[tuple[str, str]] = []
    if args.all:
        srcs = load_sources()
        if not srcs:
            print("sources.json 里没有 enabled=true 的源。请先把真实文章 URL 填进去并设 enabled。")
            return 1
        jobs = [(s["url"], s["tag"]) for s in srcs]
    elif args.url:
        jobs = [(args.url, args.tag)]
    else:
        ap.error("给一个 URL，或用 --all 遍历 sources.json")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for url, tag in jobs:
        print(f"抓取：{url}")
        rec = fetch_one(url, tag)
        if rec:
            flag = "🎓学生相关" if rec["student_related"] else "（非学生类）"
            print(f"  ✅ {rec['title'][:40]}… 正文 {len(rec['text'])} 字 {flag}")
            records.append(rec)

    if not records:
        print("没有抓到任何可用正文。")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RAW_DIR / f"raw_{stamp}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(records)} 条 raw 记录 → {out}")
    print("   下一步：python ingest/structure.py", out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
