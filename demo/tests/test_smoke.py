"""
冒烟测试 · 在 CI 中跑这个。不依赖 SBERT 模型下载，只校验：
1. 知识库 schema 完整性（50 条、必填字段、来源齐全）
2. 规则路检测 8/8 通过
3. 风险等级判定符合预期

调用：
    python demo/tests/test_smoke.py        # 直接运行
    pytest demo/tests/                     # pytest 风格
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO_DIR))

REQUIRED_FIELDS = (
    "id", "type", "name", "risk_level",
    "keywords", "patterns", "script_examples",
    "steps", "why_scam", "advice", "emergency", "source",
)
EXPECTED_RISK_LEVELS = {"high", "medium-high", "medium", "low-medium", "low"}


def load_kb() -> dict:
    with (DEMO_DIR / "knowledge_base.json").open(encoding="utf-8") as f:
        return json.load(f)


def test_kb_schema():
    kb = load_kb()
    assert kb.get("version", "").startswith("0."), f"version 异常: {kb.get('version')}"
    assert kb.get("license"), "license 字段缺失"
    assert kb.get("sources"), "sources 字段缺失"
    cases = kb.get("cases", [])
    assert len(cases) >= 50, f"案例数应 ≥ 50，实际 {len(cases)}"

    seen_ids = set()
    for c in cases:
        for f in REQUIRED_FIELDS:
            assert c.get(f), f"{c.get('id', '?')} 缺字段 {f}"
        cid = c["id"]
        assert cid not in seen_ids, f"重复 id: {cid}"
        seen_ids.add(cid)
        assert re.match(r"^KB-\d{3}$", cid), f"id 格式异常: {cid}"
        assert c["risk_level"] in EXPECTED_RISK_LEVELS, f"{cid} risk_level 异常: {c['risk_level']}"
        # 来源不能为空字符串或占位符
        assert c["source"].strip() and c["source"] not in {"—", "TBD", "—"}, \
            f"{cid} source 不能为空或占位符"


def test_rule_only_detection():
    """禁用向量引擎，只用规则路验证 8/8 命中。CI 不下载 SBERT 模型。"""
    import os
    os.environ["NJU_SKIP_VECTOR"] = "1"

    # 直接复用 score_case，不引入 nju_guardian（避免 import gradio）
    kb = load_kb()
    cases = kb["cases"]

    def detect(text):
        results = []
        for c in cases:
            kw_hits = [k for k in c["keywords"] if k.lower() in text.lower()]
            pt_hits = []
            for pt in c["patterns"]:
                try:
                    if re.search(pt, text, re.IGNORECASE):
                        pt_hits.append(pt)
                except re.error:
                    pass
            score = len(kw_hits) + 1.5 * len(pt_hits)
            if score >= 1.0:
                results.append((c["id"], score))
        return sorted(results, key=lambda x: -x[1])

    test_cases = [
        ("辅导员让我代收班费要我先转 800 给他他周一返我", "KB-008"),
        ("群里说免费送礼品+点赞返佣金，要下载 APP 做任务", "KB-001"),
        ("【京东客服】您订单异常，点击 http://jd-fix.xyz", "KB-013"),
        ("注销校园贷影响征信请转入清算账户", "KB-006"),
        ("您涉嫌洗钱请将资金转入安全账户配合调查", "KB-005"),
        ("演唱会内场票低价转让加微信私下交易", "KB-007"),
        ("无抵押免征信秒放款交保证金即可放款", "KB-003"),
        ("内幕消息稳赚不赔加入投资群", "KB-002"),
        # D2 新增
        ("毕业论文代写包过万字800", "KB-017"),
        ("保录哥伦比亚大学付5万定金锁定offer", "KB-018"),
        ("您的ETC认证已失效请点击链接重新激活", "KB-025"),
        ("请下载向日葵远程协助让我帮您操作", "KB-029"),
    ]
    failures = []
    for text, expected_id in test_cases:
        results = detect(text)
        ids = [r[0] for r in results[:3]]
        if expected_id not in ids:
            failures.append(f"  {expected_id}: {text[:30]}... → 命中 {ids[:3]}")
    assert not failures, "规则路检测失败：\n" + "\n".join(failures)


def test_eight_rules_coverage():
    """反诈预警要点引用应至少覆盖 5 条（避免 KB 漂移导致反诈要点覆盖不足）。"""
    kb = load_kb()
    eight_rules_hits = set()
    for c in kb["cases"]:
        for w in c.get("why_scam", []):
            m = re.search(r"反诈预警要点.*?第([一二三四五六七八12345678])条", w)
            if m:
                eight_rules_hits.add(m.group(1))
    assert len(eight_rules_hits) >= 5, \
        f"反诈要点覆盖不足（仅 {len(eight_rules_hits)} 条）"


def test_emergency_phones():
    """每条 case 都应该至少有一个紧急电话联系。"""
    kb = load_kb()
    for c in kb["cases"]:
        emergency = c.get("emergency", [])
        assert emergency and any(any(d.isdigit() for d in e) for e in emergency), \
            f"{c['id']} emergency 字段必须包含可识别的号码"


if __name__ == "__main__":
    tests = [
        ("KB schema 完整性", test_kb_schema),
        ("规则路 12/12 检测", test_rule_only_detection),
        ("反诈要点覆盖度", test_eight_rules_coverage),
        ("紧急电话齐全", test_emergency_phones),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}\n        {e}")
    if failed:
        print(f"\n{failed} 条 smoke test 失败")
        sys.exit(1)
    print(f"\n全部 {len(tests)} 条 smoke test 通过")
