#!/usr/bin/env python3
"""
对话式反诈 Agent · 南大数智安全官（DeepSeek / OpenAI 兼容）
============================================================

把"粘进去出卡片"的分类器，升级成一个会【多轮追问 + 调用案例库工具 + 给出处置方案】
的真正 Agent。这是项目里"Agent"二字的落点。

默认走 DeepSeek（OpenAI 兼容接口）。因为用的是 OpenAI 兼容协议，**换任何兼容端点
都只改两个环境变量**——包括 OpenClaw / 其它平台，印证"OpenClaw 本质也是调 API"。

架构（function calling 的 agentic loop）：
- 工具 search_cases：在 demo/knowledge_base.json 里检索最相关的诈骗案例（纯本地，无需联网）。
- 模型自己决定何时追问、何时查库、何时下研判。

运行：
    pip install openai
    export DEEPSEEK_API_KEY=sk-...
    python agent/guardian_agent.py

可选环境变量：
    NJU_AGENT_MODEL     默认 deepseek-chat
    NJU_AGENT_BASE_URL  默认 https://api.deepseek.com
    NJU_AGENT_API_KEY   覆盖 DEEPSEEK_API_KEY（接其它兼容端点时用）
没有 key / 没装 openai 时，会打印配置指引，并指向离线演示稿 agent/demo_transcript.md。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB_PATH = ROOT / "demo" / "knowledge_base.json"
MODEL = os.environ.get("NJU_AGENT_MODEL", "deepseek-chat")
BASE_URL = os.environ.get("NJU_AGENT_BASE_URL", "https://api.deepseek.com")
API_KEY = os.environ.get("NJU_AGENT_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")

KB = json.load(KB_PATH.open(encoding="utf-8"))
CASES = KB["cases"]


# ---------------------------------------------------------------------------
# 工具实现：案例库检索（纯本地，模型通过它"查证"）
# ---------------------------------------------------------------------------
def _tokenize(s: str) -> set[str]:
    return set(re.findall(r"[一-龥A-Za-z0-9]{2,}", s.lower()))


def search_cases(query: str, top_k: int = 4) -> list[dict]:
    """按 query 与案例关键词/名称/话术的重合度打分，返回最相关的若干案例。"""
    q = query.lower()
    qtok = _tokenize(query)
    scored = []
    for c in CASES:
        kw_hit = sum(1 for k in c.get("keywords", []) if k.lower() in q)
        blob = " ".join([c.get("name", ""), c.get("type", "")] + c.get("script_examples", []))
        tok_hit = len(qtok & _tokenize(blob))
        score = kw_hit * 2 + tok_hit
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, c in scored[:top_k]:
        out.append({
            "id": c["id"], "type": c["type"], "name": c["name"],
            "risk_level": c["risk_level"],
            "why_scam": c.get("why_scam", []),
            "advice": c.get("advice", []),
            "emergency": c.get("emergency", []),
            "source": c.get("source", ""),
        })
    return out


TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_cases",
        "description": (
            "在校园反诈案例库（50 类）中检索与用户描述最相关的诈骗案例。"
            "当你需要确认某种话术属于哪类诈骗、或查证作案手法与处置建议时调用。"
            "query 用自然语言描述用户遇到的可疑情形即可。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用户描述的可疑情形或关键话术"}
            },
            "required": ["query"],
        },
    },
}]

CASE_TYPES = "、".join(sorted({c["type"] for c in CASES}))
SYSTEM = f"""你是「南大数智安全官」，一个面向南京大学学生的反诈 AI Agent。你的任务不是简单分类，而是像一位耐心的反诈辅导员，通过对话帮同学判断是否遇到诈骗，并给出能立刻执行的处置。

工作方式：
1. 信息不足时，先追问关键细节——对方自称什么身份、通过什么渠道联系、有没有要求转账/下载App/共享屏幕/提供验证码、你是否已经操作。一次只问 1–2 个问题，口吻关心、不要审讯式连环追问。
2. 掌握足够信息后，调用 search_cases 工具到案例库里查证，再下判断——不要凭空臆断。
3. 给出结论时包含：① 风险等级（高/中/低）② 属于哪类诈骗、为什么（可引用国家反诈"八个凡是"）③ 立即怎么做（动词开头、含 96110 反诈专线、南大保卫处 81686110）。

红线：
- 不恐吓、不武断；证据不足就说"疑似"并继续核实。
- 如果同学已经转账或泄露了验证码/密码，第一句话就强调立即止损：拨 96110、向银行挂失、保留记录、就近报警。
- 只依据案例库与公开反诈知识，不编造具体数字或机构。
- 回答简洁口语，给学生看，不堆术语。

案例库已覆盖的诈骗类型：{CASE_TYPES}。"""


# ---------------------------------------------------------------------------
# Agentic loop（OpenAI 兼容 function calling）
# ---------------------------------------------------------------------------
def run_turn(client, messages: list[dict]) -> list[dict]:
    """处理一个用户回合：模型可多次调用工具，直到给出最终回复。返回更新后的 messages。"""
    while True:
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS, temperature=0.3,
        )
        msg = resp.choices[0].message
        # 记录助手消息（含可能的 tool_calls）
        am: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            am["tool_calls"] = [{
                "id": tc.id, "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            } for tc in msg.tool_calls]
        messages.append(am)

        if not msg.tool_calls:
            print(msg.content or "")
            return messages

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            hits = search_cases(**args) if tc.function.name == "search_cases" else []
            print(f"  〔查案例库：{str(args.get('query',''))[:20]}… → 命中 "
                  f"{', '.join(h['id'] for h in hits) or '无'}〕")
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(hits, ensure_ascii=False),
            })


def main() -> int:
    try:
        from openai import OpenAI
        has_sdk = True
    except ImportError:
        has_sdk = False

    if not (has_sdk and API_KEY):
        why = "未设 DEEPSEEK_API_KEY" if has_sdk else "未安装 openai（pip install openai）"
        print("对话式反诈 Agent 需要一个大模型 API（默认 DeepSeek；OpenClaw 等平台本质同为调用 API）。")
        print(f"当前无法实时运行：{why}。\n")
        print("配置后即可对话运行：")
        print("    pip install openai")
        print("    export DEEPSEEK_API_KEY=sk-...")
        print("    python agent/guardian_agent.py\n")
        print("（接其它 OpenAI 兼容端点：设 NJU_AGENT_BASE_URL / NJU_AGENT_API_KEY / NJU_AGENT_MODEL）")
        print("离线想看效果：阅读 agent/demo_transcript.md（一段真实多轮处置对话）。")
        return 0

    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    print(f"🛡 南大数智安全官 · 对话式反诈 Agent（{MODEL} · 输入 q 退出）")
    print("把遇到的可疑情况讲给我，我会帮你判断并告诉你怎么办。\n")
    messages: list[dict] = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            user = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user.lower() in {"q", "quit", "exit"}:
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        print("安全官> ", end="")
        messages = run_turn(client, messages)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
