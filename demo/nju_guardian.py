"""
南大数智安全官 NJU Guardian — 校园场景化反诈 AI Agent · Demo v0.2

单文件 Demo：Gradio Web UI + 关键词/正则匹配检测引擎 + 可选 LLM 增强。
设计目标：在没有 OpenClaw 平台访问权限前，本地可跑、可路演。

v0.2.1 更新（2026-05-07）：
- 案例库扩到 50 类（国家反诈十大类 + 校园特化 + AI 换脸/共享屏幕等新型）
- 每条 case 强制 source 字段，引用国家反诈中心、央视、新华社等公开材料

v0.2 更新（2026-05-06）：
- 输出格式重做为"对话卡片"形态（风险标签 + 命中分析 + 反诈预警要点匹配 + 三步建议）
- 命中关键词在原文中高亮显示
- 新增「知识库浏览」Tab，可视化全部 50 类案例
- 新增「示例对话」Tab，路演时直接放映三条标杆问答
- Hero 区加入知识库统计与紧急联系条
- 反诈预警要点匹配独立模块（基于 case 来源中提到的"反诈预警要点·第N条"）

运行：
    pip install -r requirements.txt
    python nju_guardian.py
然后浏览器访问 http://127.0.0.1:7860
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import gradio as gr

ROOT = Path(__file__).parent
KB_PATH = ROOT / "knowledge_base.json"

# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

with KB_PATH.open(encoding="utf-8") as f:
    KB = json.load(f)
CASES: list[dict] = KB["cases"]
KB_VERSION = KB.get("version", "0.x")
KB_UPDATED = KB.get("updated", "—")

# 向量召回引擎（D2 新增）。模型未下载 / 网络不通时降级 TF-IDF；都不行时彻底跳过。
try:
    from embedding_engine import VectorEngine

    VECTOR_ENGINE: VectorEngine | None = VectorEngine(KB)
except Exception as _e:  # pragma: no cover
    VECTOR_ENGINE = None
    print(f"[warn] VectorEngine 加载失败（仅规则匹配）：{_e}")

EMERGENCY_TIPS = (
    "**紧急联系** · 南京大学保卫处 **81686110** · "
    "96110 反诈劝阻 · 12381 涉诈短信预警 · 110 报警"
)

# 国家反诈预警要点（与 KB 案例 "反诈预警要点·第 N 条" 引用对齐）
EIGHT_RULES = [
    "要求垫付资金做任务的兼职刷单，都是诈骗",
    "宣称内幕消息、专家指导、稳赚不赔的投资理财，都是诈骗",
    "宣称无抵押低利率、放款前要先交各类费用的贷款，都是诈骗",
    "自称电商物流客服以退款理赔为由要求提供银行卡和验证码的，都是诈骗",
    "自称公检法以涉嫌违法为由要求转账到安全账户的，都是诈骗",
    '自称"领导"主动加 QQ/微信，先嘘寒问暖再要求转账的，都是诈骗',
    "发送不明链接让你输入银行卡 / 手机验证码 / 各种密码的，都是诈骗",
    "通过社交平台拉群加好友、让你点击链接下载 APP 进行投资 / 退费的，都是诈骗",
]


# ---------------------------------------------------------------------------
# 检测引擎
# ---------------------------------------------------------------------------


@dataclass
class Match:
    case: dict
    score: float                              # 综合排序分（rule_score + alpha * vector_sim）
    hit_keywords: list[str]
    hit_patterns: list[str]
    vector_sim: float = 0.0                   # 向量召回相似度（[0,1]，无引擎时为 0）

    @property
    def rule_score(self) -> float:
        return len(self.hit_keywords) * 1.0 + len(self.hit_patterns) * 1.5


def score_case(text: str, case: dict) -> Match:
    text_norm = text.lower()
    hits_kw = [kw for kw in case.get("keywords", []) if kw.lower() in text_norm]
    hits_pt: list[str] = []
    for pt in case.get("patterns", []):
        try:
            if re.search(pt, text, flags=re.IGNORECASE):
                hits_pt.append(pt)
        except re.error:
            continue
    score = len(hits_kw) * 1.0 + len(hits_pt) * 1.5
    return Match(case=case, score=score, hit_keywords=hits_kw, hit_patterns=hits_pt)


# 双路融合的关键参数：vector_sim 0.6 ≈ 1.5 规则分（中等风险阈值）
VEC_WEIGHT = 2.5
VEC_MIN_SOFT = 0.55       # 向量单独命中（无规则）的最低相似度
RULE_MIN_SOFT = 1.0       # 规则单独命中（无向量）的最低分


def detect(text: str, top_k: int = 3, vector_top_n: int = 10) -> list[Match]:
    """规则匹配 + 向量召回的双路融合。

    - 规则路：按现有 keyword/pattern 打分（rule_score）。
    - 向量路：用 BGE / TF-IDF 召回 top_n 个语义相近的 case，得到 vector_sim。
    - 综合分 = rule_score + VEC_WEIGHT * vector_sim。
    - 召回阈值：rule_score ≥ RULE_MIN_SOFT 或 vector_sim ≥ VEC_MIN_SOFT。
    """
    if not text or not text.strip():
        return []

    rule_matches: dict[str, Match] = {c["id"]: score_case(text, c) for c in CASES}

    vector_hits: dict[str, float] = {}
    if VECTOR_ENGINE is not None:
        try:
            VECTOR_ENGINE.ensure_index()
            if VECTOR_ENGINE.is_available:
                for h in VECTOR_ENGINE.search(text, top_k=vector_top_n):
                    vector_hits[h.case_id] = h.similarity
        except Exception:
            pass  # 向量路失败不阻塞规则路

    fused: list[Match] = []
    for case_id, m in rule_matches.items():
        vec_sim = vector_hits.get(case_id, 0.0)
        combined = m.score + VEC_WEIGHT * vec_sim
        # 召回门槛：规则强命中 OR 向量强命中
        if m.score >= RULE_MIN_SOFT or vec_sim >= VEC_MIN_SOFT:
            fused.append(
                Match(
                    case=m.case,
                    score=combined,
                    hit_keywords=m.hit_keywords,
                    hit_patterns=m.hit_patterns,
                    vector_sim=vec_sim,
                )
            )

    fused.sort(key=lambda x: x.score, reverse=True)
    return fused[:top_k]


def overall_risk(matches: list[Match]) -> tuple[str, str, float, str]:
    """综合规则 + 向量信号返回 (label, level, confidence, color_emoji)"""
    if not matches:
        return "暂未匹配到诈骗模式", "low", 0.0, "🟢"
    top = matches[0]
    rs = top.rule_score
    vs = top.vector_sim

    # 高风险：规则强命中
    if rs >= 3.0:
        conf = min(0.99, 0.6 + 0.08 * rs + 0.15 * vs)
        return "高风险 · 强烈疑似诈骗", "high", conf, "🔴"
    # 高风险：规则中等 + 向量同时命中（双路确认）
    if rs >= 1.5 and vs >= 0.55:
        conf = min(0.95, 0.55 + 0.08 * rs + 0.25 * vs)
        return "高风险 · 规则+语义双路确认", "high", conf, "🔴"
    # 中等风险：规则中等
    if rs >= 1.5:
        conf = min(0.85, 0.4 + 0.1 * rs)
        return "中等风险 · 多项可疑特征", "medium", conf, "🟡"
    # 中等风险：向量强命中（语义疑似），或弱规则 + 中等向量
    if vs >= 0.62 or (rs >= 1.0 and vs >= 0.55):
        conf = min(0.75, 0.35 + 0.1 * rs + 0.4 * vs)
        return "中等风险 · 语义疑似（建议进一步核实）", "medium", conf, "🟡"
    # 低风险
    conf = min(0.5, 0.2 + 0.1 * rs + 0.3 * vs)
    return "低风险 · 少量可疑信号", "low", conf, "🟢"


def extract_eight_rules_refs(matches: list[Match]) -> list[tuple[int, str]]:
    """从 case.why_scam 字段里抽出引用的"反诈预警要点·第N条"，去重后返回 (index, text)"""
    refs: list[tuple[int, str]] = []
    seen: set[int] = set()
    for m in matches:
        for line in m.case.get("why_scam", []):
            mat = re.search(r"反诈预警要点.*?第([一二三四五六七八12345678])条", line)
            if not mat:
                continue
            cn_to_int = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
                         "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8}
            idx = cn_to_int.get(mat.group(1))
            if idx and idx not in seen and 1 <= idx <= len(EIGHT_RULES):
                seen.add(idx)
                refs.append((idx, EIGHT_RULES[idx - 1]))
    return refs


def highlight_text(text: str, hit_keywords: list[str]) -> str:
    """在原文中把命中的关键词加粗（按长度降序避免子串覆盖）"""
    if not text or not hit_keywords:
        return f"> {text}" if text else ""
    out = text
    for kw in sorted(set(hit_keywords), key=len, reverse=True):
        if not kw:
            continue
        # 避免重复加粗
        out = re.sub(re.escape(kw), f"**{kw}**", out, flags=re.IGNORECASE)
    return f"> {out}"


# ---------------------------------------------------------------------------
# 输出渲染（对话卡片风格）
# ---------------------------------------------------------------------------


RISK_BANNERS = {
    "high": "<div style='background:#FEF2F2;border:1px solid #FECACA;border-left:4px solid #DC2626;"
            "padding:11px 16px;border-radius:6px;margin:6px 0 12px;'>"
            "<span style='color:#DC2626;font-weight:600;font-size:15px;letter-spacing:0.3px;'>● {label}</span>"
            "<span style='color:#7F1D1D;margin-left:14px;font-size:12px;'>置信度 {conf}%</span></div>",
    "medium": "<div style='background:#FFFBEB;border:1px solid #FDE68A;border-left:4px solid #D97706;"
              "padding:11px 16px;border-radius:6px;margin:6px 0 12px;'>"
              "<span style='color:#D97706;font-weight:600;font-size:15px;letter-spacing:0.3px;'>● {label}</span>"
              "<span style='color:#78350F;margin-left:14px;font-size:12px;'>置信度 {conf}%</span></div>",
    "low": "<div style='background:#F0FDF4;border:1px solid #BBF7D0;border-left:4px solid #16A34A;"
           "padding:11px 16px;border-radius:6px;margin:6px 0 12px;'>"
           "<span style='color:#16A34A;font-weight:600;font-size:15px;letter-spacing:0.3px;'>● {label}</span>"
           "<span style='color:#14532D;margin-left:14px;font-size:12px;'>置信度 {conf}%</span></div>",
}


def render_case_card(match: Match, rank: int) -> str:
    c = match.case
    hits = "、".join(f"`{k}`" for k in match.hit_keywords[:8]) or "（仅命中模式特征）"
    why = "\n".join(f"- {w}" for w in c.get("why_scam", []))
    advice = "\n".join(
        f"- **{i+1}.** {a}" for i, a in enumerate(c.get("advice", []))
    )
    steps = "\n".join(f"- {s}" for s in c.get("steps", []))

    # 双路命中标签
    badges: list[str] = []
    if match.rule_score >= 1.0:
        badges.append(f"📐 规则 {match.rule_score:.1f}")
    if match.vector_sim >= 0.4:
        badges.append(f"🧠 语义 {match.vector_sim:.2f}")
    if not badges:
        badges.append(f"📐 规则 {match.rule_score:.1f}")
    badge_line = "　".join(badges)

    # 每段之间加空行，避免 markdown 折叠
    return (
        f"#### 命中案例 {rank} · {c['id']} · {c['name']}\n\n"
        f"**类型** · {c['type']}　|　**综合分** · {match.score:.1f}　|　{badge_line}\n\n"
        f"**命中关键词** · {hits}\n\n"
        f"**作案手法**\n\n{steps}\n\n"
        f"**为什么是诈骗**\n\n{why}\n\n"
        f"**三步行动建议**\n\n{advice}\n\n"
        f"<sub>来源 · {c.get('source', '—')}</sub>"
    )


def render_report(text: str, matches: list[Match]) -> str:
    label, level, conf, _ = overall_risk(matches)
    banner = RISK_BANNERS[level].format(label=label, conf=int(conf * 100))

    # 关键：HTML block 与 markdown 内容之间必须用空行分隔，否则 markdown-it
    # 会把后续 markdown 当成 HTML block 的延续，** 不会被渲染为加粗。
    parts: list[str] = [banner, ""]

    # 用户输入回显（命中关键词高亮）
    all_kws = [k for m in matches for k in m.hit_keywords]
    parts.append("**用户输入**（命中关键词已加粗）")
    parts.append("")
    parts.append(highlight_text(text, all_kws))
    parts.append("")

    if not matches:
        parts.append("---")
        parts.append("")
        parts.append("**未在本地知识库中命中诈骗模式**。可能原因：")
        parts.append("")
        parts.append("- 文本本身风险较低；")
        parts.append("- 表述较隐晦，建议结合右侧 LLM 增强进一步分析；")
        parts.append("- 知识库 50 类未覆盖此场景，建议描述更具体的细节再试。")
        parts.append("")
        parts.append(EMERGENCY_TIPS)
        return "\n".join(parts)

    # 反诈预警要点引用（独立模块）
    refs = extract_eight_rules_refs(matches)
    if refs:
        parts.append("---")
        parts.append("")
        parts.append("**国家反诈预警要点 · 命中条目**")
        parts.append("")
        for idx, txt in refs:
            parts.append(f"> **第 {idx} 条** · {txt}")
        parts.append("")

    parts.append("---")
    parts.append("")
    parts.append(f"**已匹配 {len(matches)} 条相似案例**")
    parts.append("")
    for i, m in enumerate(matches, 1):
        parts.append(render_case_card(m, i))
        parts.append("")

    parts.append("---")
    parts.append("")
    parts.append(EMERGENCY_TIPS)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 转发卡片 / 报告下载（D3 新增）
# ---------------------------------------------------------------------------


def make_share_card(text: str, matches: list[Match]) -> str:
    """生成可复制粘贴到班级群/朋友圈的简洁文字卡片。控制在 ~300 字内。"""
    if not text or not text.strip():
        return "（请先输入待检测的文本，再生成卡片。）"

    label, _level, conf, emoji = overall_risk(matches)
    lines: list[str] = []
    lines.append(f"{emoji} 反诈检测预警 · 南大数智安全官")
    lines.append("─────────────────")
    excerpt = text.strip().replace("\n", " ")
    if len(excerpt) > 80:
        excerpt = excerpt[:80] + "…"
    lines.append(f"原文：{excerpt}")
    lines.append("")
    lines.append(f"风险等级：{label}（置信度 {int(conf*100)}%）")

    if matches:
        top = matches[0]
        c = top.case
        lines.append(f"匹配类型：{c['name']}（{c['id']}）")
        # 双路命中标记
        signal_bits = []
        if top.rule_score > 0:
            signal_bits.append(f"规则 {top.rule_score:.1f}")
        if top.vector_sim >= 0.4:
            signal_bits.append(f"语义 {top.vector_sim:.2f}")
        if signal_bits:
            lines.append(f"检测信号：{' / '.join(signal_bits)}")
        lines.append("")
        lines.append("📌 三步行动建议：")
        for i, a in enumerate(c.get("advice", [])[:3], 1):
            lines.append(f"  {i}. {a}")
        # 反诈预警要点引用
        refs = extract_eight_rules_refs(matches)
        if refs:
            lines.append("")
            lines.append("🛡 触发反诈预警要点：")
            for idx, txt in refs[:2]:
                lines.append(f"  · 第 {idx} 条：{txt}")
    else:
        lines.append("匹配类型：未在本地知识库命中诈骗模式")
        lines.append("")
        lines.append("⚠️ 没命中不等于安全，遇到资金敏感的请求请务必电话核实。")

    lines.append("")
    lines.append("📞 紧急联系：")
    lines.append("  · 南大保卫处 81686110")
    lines.append("  · 96110 反诈劝阻 / 12381 涉诈短信")
    lines.append("  · 110 报警")
    lines.append("─────────────────")
    lines.append("via NJU Guardian · OpenClaw 应用创新大赛参赛 Demo")
    return "\n".join(lines)


def make_html_report(text: str, matches: list[Match], llm_text: str = "") -> str:
    """生成可下载的独立 HTML 报告（用户可在浏览器中 ⌘+P 打印为 PDF）。"""
    import html
    from datetime import datetime

    label, level, conf, _ = overall_risk(matches)
    color_map = {
        "high":   ("#DC2626", "#FEF2F2", "#FECACA"),
        "medium": ("#D97706", "#FFFBEB", "#FDE68A"),
        "low":    ("#16A34A", "#F0FDF4", "#BBF7D0"),
    }
    fg, bg, border = color_map.get(level, color_map["low"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def esc(s):
        return html.escape(s or "")

    def case_html(m: Match, rank: int) -> str:
        c = m.case
        kw = "、".join(esc(k) for k in m.hit_keywords[:8]) or "—"
        steps = "".join(f"<li>{esc(s)}</li>" for s in c.get("steps", []))
        why = "".join(f"<li>{esc(w)}</li>" for w in c.get("why_scam", []))
        adv = "".join(f"<li>{esc(a)}</li>" for a in c.get("advice", []))
        return f"""
        <div class="case">
          <h3>命中案例 {rank} · {esc(c['id'])} · {esc(c['name'])}</h3>
          <div class="meta">
            <span><b>类型</b> {esc(c['type'])}</span>
            <span><b>综合分</b> {m.score:.1f}</span>
            <span><b>规则</b> {m.rule_score:.1f}</span>
            <span><b>语义</b> {m.vector_sim:.2f}</span>
          </div>
          <p><b>命中关键词</b>：{kw}</p>
          <p><b>作案手法</b></p><ul>{steps}</ul>
          <p><b>为什么是诈骗</b></p><ul>{why}</ul>
          <p><b>三步行动建议</b></p><ol>{adv}</ol>
          <p class="src">来源 · {esc(c.get('source', '—'))}</p>
        </div>"""

    cases_html = "".join(case_html(m, i) for i, m in enumerate(matches, 1)) or \
                 "<p>未命中本地知识库案例。请结合常识判断或拨打 96110。</p>"

    refs = extract_eight_rules_refs(matches)
    refs_html = ""
    if refs:
        items = "".join(f"<li><b>第 {idx} 条</b> · {esc(txt)}</li>" for idx, txt in refs)
        refs_html = f"<section><h2>国家反诈预警要点 · 命中条目</h2><ul>{items}</ul></section>"

    llm_html = ""
    if llm_text and not llm_text.startswith("_未启用"):
        llm_html = f"<section><h2>LLM 增强解读</h2><div class='llm'>{esc(llm_text)}</div></section>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>NJU Guardian 反诈检测报告 · {timestamp}</title>
<style>
  @media print {{ .no-print {{ display:none; }} body {{ padding:0; }} }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:-apple-system,'PingFang SC',sans-serif; max-width:780px;
         margin:0 auto; padding:32px; color:#1F2937; line-height:1.6; }}
  header {{ border-bottom:1px solid #E5E7EB; padding-bottom:16px; margin-bottom:24px; }}
  h1 {{ margin:0 0 4px; font-size:22px; color:#6D28D9; }}
  .subtitle {{ font-size:12px; color:#6B7280; }}
  .banner {{ background:{bg}; border:1px solid {border}; border-left:4px solid {fg};
             padding:14px 18px; border-radius:6px; margin:18px 0; }}
  .banner b {{ color:{fg}; font-size:16px; }}
  .input-block {{ background:#F9FAFB; border:1px solid #E5E7EB;
                  padding:14px 18px; border-radius:6px; font-size:13.5px;
                  white-space:pre-wrap; word-break:break-all; }}
  .case {{ background:#FFFFFF; border:1px solid #E5E7EB; padding:18px;
          border-radius:8px; margin:14px 0; page-break-inside:avoid; }}
  .case h3 {{ margin:0 0 10px; font-size:15px; color:#7B287D; }}
  .meta {{ display:flex; gap:14px; flex-wrap:wrap; font-size:12px;
          color:#6B7280; margin-bottom:10px; }}
  .src {{ color:#9CA3AF; font-size:11px; margin-top:8px; }}
  ul, ol {{ padding-left:22px; margin:6px 0 12px; }}
  section {{ margin:24px 0; }}
  section h2 {{ font-size:15px; color:#374151; border-bottom:1px solid #E5E7EB; padding-bottom:6px; }}
  .llm {{ background:#FAF5FF; border-left:3px solid #A78BFA; padding:12px 16px;
          border-radius:6px; white-space:pre-wrap; font-size:13.5px; }}
  footer {{ margin-top:36px; padding-top:14px; border-top:1px solid #E5E7EB;
            font-size:11px; color:#9CA3AF; text-align:center; }}
  .no-print {{ background:#EEF2FF; border:1px dashed #818CF8; padding:10px 14px;
               border-radius:6px; font-size:12px; color:#3730A3; margin-bottom:18px; }}
</style></head><body>
  <div class="no-print">💡 浏览器中按 <b>⌘+P / Ctrl+P</b> 即可保存为 PDF。</div>
  <header>
    <h1>南大数智安全官 · 反诈检测报告</h1>
    <div class="subtitle">生成时间：{timestamp} · 知识库 v{KB_VERSION} · 双路召回引擎</div>
  </header>
  <div class="banner"><b>● {esc(label)}</b>　·　置信度 {int(conf*100)}%</div>
  <section><h2>用户输入</h2>
    <div class="input-block">{esc(text)}</div>
  </section>
  {refs_html}
  <section><h2>命中案例（共 {len(matches)} 条）</h2>{cases_html}</section>
  {llm_html}
  <footer>
    本报告由 NJU Guardian 自动生成，仅供风险参考，不替代国家反诈中心 App 与 96110 劝阻。<br>
    紧急联系 · 南大保卫处 81686110 · 96110 · 12381 · 110<br>
    OpenClaw 应用创新大赛参赛 Demo · 知识库 CC BY 4.0
  </footer>
</body></html>"""


# ---------------------------------------------------------------------------
# 可选 LLM 增强
# ---------------------------------------------------------------------------

LLM_SYSTEM_PROMPT = """你是"南大数智安全官 NJU Guardian"，一款面向南京大学学生的校园场景化反诈 AI Agent。
请基于以下用户输入和本地知识库已匹配到的案例，给出一段简洁、专业、贴合校园语境的风险解读。

输出格式（用 markdown）：
1. **一句话结论** —— 红/黄/绿三级风险 + 一句话原因
2. **行为视角** —— 这条诈骗在利用受害人的什么决策偏误（如损失厌恶 / 权威服从 / 稀缺性诱饵 / 互惠原则等），限两条
3. **三步可执行建议** —— 动词开头，每条不超过 25 字
4. **校园关联** —— 如涉及辅导员 / 教务 / 奖助 / 二手 / 老乡群等校园语境，明确指出

注意：保持中文；不要编造案例细节；不确定时建议拨打 96110 或南大保卫处 81686110。"""


def llm_explain(text: str, matches: list[Match], api_key: str, base_url: str, model: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return "_（未安装 openai 库，跳过 LLM 增强。`pip install openai` 后可启用）_"

    client = OpenAI(api_key=api_key, base_url=base_url)
    case_brief = (
        "（无匹配案例，请基于通用反诈知识回答）"
        if not matches
        else "\n".join(f"- {m.case['id']} {m.case['name']}（命中：{','.join(m.hit_keywords)}）" for m in matches)
    )
    user_msg = f"【用户输入】\n{text}\n\n【本地知识库匹配】\n{case_brief}\n\n请按系统提示词的格式输出风险解读。"
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return resp.choices[0].message.content or "_（LLM 返回为空）_"
    except Exception as e:
        return f"_（LLM 调用失败：{e}）_"


# ---------------------------------------------------------------------------
# Gradio 接口函数
# ---------------------------------------------------------------------------


def analyze_text(text, enable_llm, api_key, base_url, model):
    matches = detect(text, top_k=3)
    report = render_report(text, matches)
    if enable_llm and api_key.strip():
        llm_view = llm_explain(text, matches, api_key.strip(), base_url.strip(), model.strip())
    else:
        llm_view = "_未启用 LLM 增强（在右侧勾选并填入 API Key 后可启用）_"
    return report, llm_view


def make_share_handler(text):
    """UI 回调：基于当前文本生成转发卡片。"""
    matches = detect(text or "", top_k=3) if text else []
    return make_share_card(text or "", matches)


def download_report_handler(text, llm_text):
    """UI 回调：把检测结果生成 HTML 文件，返回路径供 Gradio 下载组件使用。"""
    import tempfile
    from datetime import datetime

    matches = detect(text or "", top_k=3) if text else []
    html_str = make_html_report(text or "", matches, llm_text or "")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(tempfile.gettempdir()) / "nju_guardian_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"NJUGuardian_报告_{ts}.html"
    out_path.write_text(html_str, encoding="utf-8")
    return str(out_path)


def analyze_image(image, enable_llm, api_key, base_url, model):
    if image is None:
        return "请先上传截图。", ""
    try:
        import pytesseract
    except ImportError:
        return (
            "📌 OCR 功能需要安装 `pytesseract` 和 `pillow`，并在系统层安装 tesseract：\n\n"
            "```bash\nbrew install tesseract tesseract-lang  # macOS\n"
            "pip install pytesseract pillow\n```\n\n"
            "未装也没关系——可改用「文本检测」Tab，把聊天文字粘进去。",
            "",
        )
    try:
        text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    except Exception as e:
        return f"OCR 失败：{e}\n\n请尝试上传更清晰的截图，或改用文本输入。", ""
    if not text.strip():
        return "未识别到文字，请尝试更清晰的截图。", ""
    text_view = f"**📷 OCR 识别结果**\n\n```\n{text.strip()[:500]}\n```\n\n---\n\n"
    rep, llm = analyze_text(text, enable_llm, api_key, base_url, model)
    return text_view + rep, llm


def analyze_link(link, enable_llm, api_key, base_url, model):
    if not link.strip():
        return "请输入链接或电话号码。", ""
    risk_notes = []
    suspicious_tlds = (".xyz", ".top", ".click", ".info", ".cn.com", ".tk", ".ml", ".ga")
    short_link_hosts = ("t.cn", "url.cn", "dwz.cn", "suo.im", "bit.ly", "tinyurl.com", "goo.gl")
    low = link.lower()
    if any(t in low for t in suspicious_tlds):
        hits = ", ".join(t for t in suspicious_tlds if t in low)
        risk_notes.append(f"❗ 域名后缀属于钓鱼高发后缀（{hits}）")
    if any(s in low for s in short_link_hosts):
        host = next(s for s in short_link_hosts if s in low)
        risk_notes.append(f"❗ 包含短链服务（{host}），需展开后再核验")
    if re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", link):
        risk_notes.append("❗ 使用裸 IP 地址，几乎确定是异常链接")
    if re.match(r"^1[3-9]\d{9}$", link.strip()):
        risk_notes.append("ℹ️ 这看起来是手机号——请通过手机自带骚扰拦截 / 96110 一键查询。")
    if low.startswith("http://"):
        risk_notes.append("⚠️ 使用 HTTP 而非 HTTPS，存在窃听与中间人风险")

    matches = detect(link, top_k=3)
    head = "## 🔗 链接 / 电话风险查询\n\n"
    head += "\n".join(risk_notes) if risk_notes else "✅ 未命中常见风险特征。"
    head += "\n\n_本地启发式检查只能识别明显问题。生产版本会接入 URL 风险接口与电话黑名单查询。_\n\n---\n\n"

    if matches:
        head += render_report(link, matches)
    else:
        head += EMERGENCY_TIPS

    if enable_llm and api_key.strip():
        llm = llm_explain(f"用户提交了链接 / 电话：{link}", matches, api_key.strip(), base_url.strip(), model.strip())
    else:
        llm = "_未启用 LLM 增强_"
    return head, llm


# ---------------------------------------------------------------------------
# 知识库浏览（v0.2 新增）
# ---------------------------------------------------------------------------


def render_kb_overview() -> str:
    """生成全部 case 的可视化总览"""
    type_count = Counter(c["type"] for c in CASES)
    parts = [
        f"### 校园诈骗知识库 v{KB_VERSION} · 更新于 {KB_UPDATED}\n",
        f"共 **{len(CASES)}** 类结构化案例，覆盖 **{len(type_count)}** 种诈骗类型。\n",
        "**类型分布**",
    ]
    for typ, n in type_count.most_common():
        parts.append(f"- {typ}（{n} 条）")
    parts.append("\n**数据来源**")
    for s in KB.get("sources", []):
        parts.append(f"- {s}")
    parts.append("\n---\n")

    risk_label = {"high": "高风险", "medium-high": "中高风险", "medium": "中风险", "low": "低风险"}
    risk_color = {"high": "#DC2626", "medium-high": "#EA580C", "medium": "#D97706", "low": "#16A34A"}
    for c in CASES:
        lvl = c.get("risk_level", "high")
        rl = risk_label.get(lvl, "高风险")
        rc = risk_color.get(lvl, "#DC2626")
        parts.append(
            f"#### <span style='color:{rc};'>●</span> {c['id']} · {c['name']} "
            f"<sub style='color:{rc};font-weight:500;'>{rl}</sub>"
        )
        parts.append(f"**类型** · {c['type']}")
        kw_preview = "、".join(f"`{k}`" for k in c.get("keywords", [])[:6])
        parts.append(f"**关键词** · {kw_preview}")
        if c.get("script_examples"):
            parts.append(f"**话术示例** · 「{c['script_examples'][0]}」")
        if c.get("advice"):
            parts.append(f"**首选建议** · {c['advice'][0]}")
        parts.append(f"<sub>来源 · {c.get('source', '—')}</sub>")
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 示例对话（v0.2 新增 · 路演用）
# ---------------------------------------------------------------------------


SHOWCASE_DIALOGS = [
    {
        "title": "样例 1 · 冒充辅导员收班费",
        "user": "辅导员让我代收班费，要我先转 800 给他他周一返我，靠谱吗？",
        "expected_kb": "KB-008",
    },
    {
        "title": "样例 2 · 兼职刷单返利",
        "user": "看到一个微信群说免费送礼品+点赞返佣金，要我下载一个 APP 做任务，要不要试试？",
        "expected_kb": "KB-001",
    },
    {
        "title": "样例 3 · 钓鱼链接 + 假客服",
        "user": "【京东客服】您订单异常，请点击 http://jd-fix.xyz 处理售后",
        "expected_kb": "KB-013",
    },
]


def render_showcase() -> str:
    parts = ["### 示例对话（路演用）\n",
             "下方三条对话已经过本地引擎检测。点击「文本检测」Tab 的示例可亲手验证。\n\n---\n"]
    for d in SHOWCASE_DIALOGS:
        matches = detect(d["user"])
        parts.append(f"#### {d['title']}")
        parts.append(f"\n**用户输入**\n\n> {d['user']}\n")
        parts.append("**NJU Guardian 回复**\n")
        parts.append(render_report(d["user"], matches))
        parts.append("\n---\n")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


SAMPLE_TEXTS = [
    "辅导员让我代收班费，要我先转 800 给他，他周一返我，靠谱吗？",
    "看到一个微信群说免费送礼品+点赞返佣金，要我下载一个 APP 做任务，要不要试试？",
    "【京东客服】您订单异常，请点击 http://jd-fix.xyz 处理售后",
    "我学生时代注册的校园贷没注销，影响征信，让我在借呗、金条借出额度转入清算账户",
    "您涉嫌洗钱，请将资金转入安全账户接受调查，否则立即逮捕",
    "演唱会内场票低价转让，加微信私下交易",
    "教育部门通知您可以领取 2000 元助学金，请到 ATM 按指示激活",
    "群里老师免费分享内幕消息，跟单稳赚不赔",
]


HERO_HTML = f"""
<div style="
    background:linear-gradient(120deg,#6D28D9 0%,#7B287D 50%,#4338CA 100%);
    border-radius:12px;margin-bottom:16px;padding:22px 28px;
    box-shadow:0 4px 20px -8px rgba(123,40,125,0.45);
    color:#FFFFFF !important;">
  <div style="display:flex;align-items:center;gap:16px;color:#FFFFFF;">
    <div style="width:42px;height:42px;background:rgba(255,255,255,0.18);border-radius:10px;
                display:flex;align-items:center;justify-content:center;
                font-size:20px;color:#FFFFFF;flex-shrink:0;">⛨</div>
    <div style="color:#FFFFFF;">
      <div style="margin:0;font-size:22px;font-weight:600;color:#FFFFFF;letter-spacing:0.3px;">
        南大数智安全官 <span style="opacity:0.7;font-weight:400;">· NJU Guardian</span>
      </div>
      <div style="margin:3px 0 0;font-size:12px;color:#FFFFFF;opacity:0.85;">
        校园场景化电信诈骗智能识别 · 基于 OpenClaw 的 Demo 原型
      </div>
    </div>
    <div style="margin-left:auto;color:#FFFFFF;background:rgba(255,255,255,0.16);
                padding:5px 11px;border-radius:6px;font-size:11px;
                font-family:'SF Mono',Menlo,monospace;letter-spacing:0.5px;">
      v0.2.1 · KB {len(CASES)} · 双路召回
    </div>
  </div>
  <div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.18);
              display:flex;gap:24px;flex-wrap:wrap;font-size:11.5px;color:#FFFFFF;opacity:0.92;">
    <span style="color:#FFFFFF;">检测引擎 · 关键词/正则 + BGE-zh 向量召回</span>
    <span style="color:#FFFFFF;">紧急联系 · 南大保卫处 81686110 · 96110 · 12381</span>
  </div>
</div>
"""


def build_ui() -> gr.Blocks:
    css = """
    .gradio-container {max-width:1240px !important; background:#FAFAF9 !important;}
    #report-md {min-height:240px;}
    .tab-nav button {font-weight:500 !important;}
    h3 {font-weight:600 !important; color:#1F2937 !important;}
    h4 {font-weight:600 !important;}
    .prose strong {font-weight:600 !important;}
    .form {border:1px solid #E5E7EB !important; background:#FFFFFF !important;}
    """
    theme = gr.themes.Soft(
        primary_hue="purple",
        neutral_hue="slate",
        font=[gr.themes.GoogleFont("Inter"), "PingFang SC", "system-ui", "sans-serif"],
    )
    # Gradio 6 起 theme / css 推荐通过 launch() 传入；仍允许构造器传，但会发 deprecation。
    # 我们把它们存到 attribute 上，在 __main__ 里 launch 时再传。
    with gr.Blocks(title="NJU Guardian · 南大数智安全官") as app:
        app._nju_theme = theme  # type: ignore[attr-defined]
        app._nju_css = css  # type: ignore[attr-defined]
        gr.HTML(HERO_HTML)

        with gr.Tabs():
            # ============== Tab 1: 文本检测 ==============
            with gr.TabItem("文本检测"):
                with gr.Row():
                    with gr.Column(scale=2):
                        txt_in = gr.Textbox(
                            label="粘贴可疑短信 / 聊天记录 / 链接说明",
                            lines=5,
                            placeholder="例如：辅导员让我代收班费，要我先转 800 给他...",
                        )
                        gr.Examples(SAMPLE_TEXTS, inputs=txt_in, label="示例输入（点击填入）", examples_per_page=8)
                        txt_btn = gr.Button("开始检测", variant="primary", size="lg")
                    with gr.Column(scale=1):
                        gr.Markdown("### LLM 增强（可选）")
                        gr.Markdown(
                            "本地规则即可输出完整报告。如要更智能的解读，可填入兼容 OpenAI 协议的 API："
                            "DeepSeek / 通义百炼 / Moonshot 等。"
                        )
                        enable_llm = gr.Checkbox(label="启用 LLM 增强解读", value=False)
                        api_key = gr.Textbox(label="API Key", type="password", placeholder="sk-...")
                        base_url = gr.Textbox(
                            label="API Base URL",
                            value=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
                        )
                        model = gr.Textbox(label="Model", value=os.getenv("LLM_MODEL", "deepseek-chat"))

            # ============== Tab 2: 截图识别 ==============
            with gr.TabItem("截图识别"):
                with gr.Row():
                    with gr.Column(scale=2):
                        img_in = gr.Image(type="pil", label="上传聊天 / 转账 / 二维码截图")
                        img_btn = gr.Button("识别并检测", variant="primary", size="lg")
                    with gr.Column(scale=1):
                        gr.Markdown(
                            "### OCR 依赖\n"
                            "需要在系统层安装 tesseract（macOS：`brew install tesseract tesseract-lang`），"
                            "并 `pip install pytesseract pillow`。\n\n"
                            "未安装也可以用「文本检测」Tab——把聊天复制粘贴。"
                        )

            # ============== Tab 3: 链接核验 ==============
            with gr.TabItem("链接核验"):
                with gr.Row():
                    with gr.Column(scale=2):
                        link_in = gr.Textbox(
                            label="输入完整链接或 11 位手机号",
                            placeholder="https://jd-fix.xyz/abc 或 13800000000",
                        )
                        link_examples = [
                            "http://jd-fix.xyz/order/93f2a",
                            "http://192.168.1.1/login",
                            "https://t.cn/AbCdEfG",
                            "13812345678",
                        ]
                        gr.Examples(link_examples, inputs=link_in, label="示例输入")
                        link_btn = gr.Button("查询风险", variant="primary", size="lg")
                    with gr.Column(scale=1):
                        gr.Markdown(
                            "### 检测维度\n"
                            "- 钓鱼高发域名（.xyz / .top / .click 等）\n"
                            "- 短链服务展开\n"
                            "- 裸 IP 地址\n"
                            "- HTTP（非 HTTPS）警告\n"
                            "- 手机号引导用户使用 96110 查询"
                        )

            # ============== Tab 4: 知识库浏览（v0.2 新增）==============
            with gr.TabItem("知识库"):
                gr.Markdown(render_kb_overview())

            # ============== Tab 5: 示例对话（v0.2 新增）==============
            with gr.TabItem("示例对话"):
                gr.Markdown(render_showcase())

            # ============== Tab 6: 关于 ==============
            with gr.TabItem("关于"):
                gr.Markdown(f"""
### 关于本 Demo

**南大数智安全官 NJU Guardian** 是 2026 年南京大学 OpenClaw 应用创新大赛参赛项目的本地原型。

- **当前版本**：Demo v0.2.1（{KB_UPDATED}）
- **技术栈**：Python 3 + Gradio + 双路召回引擎（关键词/正则 + BGE-zh 向量）+ 可选 LLM 增强
- **知识库**：v{KB_VERSION}，{len(CASES)} 类结构化案例，每条带公开来源标注（CC BY 4.0）
- **代码仓库**：决赛前公开 GitHub 链接
- **联系方式**：***REMOVED***

### 双路召回原理

```
用户输入 ─┬─→ 规则路：keyword + regex 命中 → rule_score
         └─→ 向量路：BGE-zh 语义相似度 → vector_sim
                          ↓
              综合分 = rule_score + 2.5 × vector_sim
                          ↓
       风险等级（双路确认 → HIGH，单路强信号 → MEDIUM）
```

**关键参数**：
- 向量模型：BAAI/bge-small-zh-v1.5（95MB，中文优化）
- 召回门槛：rule_score ≥ 1.0 或 vector_sim ≥ 0.55
- 高风险条件：rule_score ≥ 3.0，或 rule_score ≥ 1.5 且 vector_sim ≥ 0.55
- 模型加载失败 → 降级 TF-IDF；TF-IDF 也失败 → 跳过向量路只用规则

### v0.2.1 新功能

- **📤 转发卡片**：点击「生成可转发卡片」一键生成可发到班群的简洁文字
- **💾 报告下载**：点击「下载报告」生成独立 HTML 文件，浏览器中 ⌘+P 即可打印 PDF

### 与正式版的差异
| 维度 | 本地 Demo（v0.2.1） | 决赛 OpenClaw 版 |
|---|---|---|
| 检测引擎 | 关键词/正则 + BGE-zh 向量 | OpenClaw RAG 向量检索 + 多 Agent 协作 |
| OCR | 本地 tesseract | OpenClaw 多模态能力 |
| 案例库规模 | 50 类（公开来源） | 200+ 条（含真实校园回流） |
| 部署形态 | 本地 Gradio | 微信小程序 + OpenClaw 平台 |

### 紧急联系
南京大学保卫处 **81686110** ｜ 96110 反诈劝阻 ｜ 12381 涉诈短信预警 ｜ 110 报警
""")

        # Output panes (shared by Tab 1/2/3)
        gr.Markdown("---")
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### 检测报告")
                report_out = gr.Markdown(value="_点击上方任一 Tab 的检测按钮开始_", elem_id="report-md")

                # D3：转发卡片 + HTML 报告下载
                with gr.Row():
                    share_btn = gr.Button("📤 生成可转发卡片", size="sm")
                    download_btn = gr.Button("💾 下载报告 (HTML → PDF)", size="sm")

                share_card_box = gr.Textbox(
                    label="🔗 可转发卡片（全选复制后发到班群 / 朋友圈）",
                    lines=14, visible=False, interactive=True,
                )
                download_file = gr.File(
                    label="📄 检测报告（浏览器打开后 ⌘+P 保存为 PDF）",
                    visible=False, interactive=False,
                )
            with gr.Column(scale=1):
                gr.Markdown("### LLM 解读（可选）")
                llm_out = gr.Markdown(value="_未启用 LLM 时此处显示提示_")

        # Footer (compact)
        gr.HTML(f"""
        <div style="margin-top:12px;padding:12px 16px;border-top:1px solid #E5E7EB;
                    color:#6B7280;font-size:11px;line-height:1.6;">
          <div><strong style="color:#374151;">知识库</strong> · v{KB_VERSION} · {len(CASES)} 类结构化案例 · 更新于 {KB_UPDATED}</div>
          <div><strong style="color:#374151;">数据来源</strong> · {' · '.join(KB.get('sources', []))}</div>
          <div><strong style="color:#374151;">紧急联系</strong> · 南大保卫处 81686110 · 96110 反诈劝阻 · 12381 涉诈短信 · 110 报警</div>
        </div>
        """)

        # Bindings
        txt_btn.click(analyze_text, [txt_in, enable_llm, api_key, base_url, model], [report_out, llm_out])
        img_btn.click(analyze_image, [img_in, enable_llm, api_key, base_url, model], [report_out, llm_out])
        link_btn.click(analyze_link, [link_in, enable_llm, api_key, base_url, model], [report_out, llm_out])

        # D3 bindings
        share_btn.click(
            lambda t: gr.update(value=make_share_handler(t), visible=True),
            inputs=[txt_in], outputs=[share_card_box],
        )
        download_btn.click(
            lambda t, llm: gr.update(value=download_report_handler(t, llm), visible=True),
            inputs=[txt_in, llm_out], outputs=[download_file],
        )

    return app


if __name__ == "__main__":
    print(f"\n🛡️  NJU Guardian Demo v0.2.1 · 知识库 {len(CASES)} 类 · 双路召回")
    print(f"📚 数据来源：{' | '.join(KB.get('sources', []))}")
    print("📞 紧急：南大保卫处 81686110 | 96110 | 12381 | 110")
    print("🌐 启动后访问：http://127.0.0.1:7860\n")
    app = build_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=False,
        theme=getattr(app, "_nju_theme", None),
        css=getattr(app, "_nju_css", None),
    )
