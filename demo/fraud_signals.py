#!/usr/bin/env python3
"""
行为红旗信号层 · 反诈"八个凡是"要素抽取（检测引擎第三路）
=========================================================

双路召回（关键词/正则 + BGE 语义）解决的是"这条输入像库里哪一类诈骗"。
但诈骗每天都在出新花样——库里没有的变体怎么办？

第三路从输入中抽取【通用诈骗行为信号】（要求转账、索要验证码、诱导共享屏幕、
冒充权威、制造紧迫、脱离平台、超额回报、要求保密……），每个信号对应国家反诈
"八个凡是"。只要行为模式像诈骗，**即使案例库里没有对应类型，也能给出风险预警**。

这让引擎从"案例匹配"升级为"案例匹配 + 行为研判"：更准、更鲁棒、更适用于未知骗局。
纯标准库实现，Python 端引擎、评测、H5 可共用同一套定义。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# severity：3=强信号（几乎必诈），2=中信号，1=弱信号（需与其它信号叠加）
SIGNALS: list[dict] = [
    {"id": "transfer", "name": "要求转账 / 垫付资金", "severity": 3,
     "rule": "凡是要求转账、垫付、缴纳保证金 / 解冻费的，高度可疑",
     "patterns": [r"(转账|汇款|打款|垫付|垫资|保证金|定金|押金|手续费|解冻费|激活费|清算账户|安全账户|先转|转入|转到|转给|把钱转|充值)"]},
    {"id": "credential", "name": "索要验证码 / 银行卡 / 密码", "severity": 3,
     "rule": "八个凡是·第七条：要你提供短信验证码、银行卡号 / 密码的，都是诈骗",
     "patterns": [r"(验证码|动态码|短信码|银行卡号|卡号|支付密码|交易密码|开户行|CVV)"]},
    {"id": "remote", "name": "诱导共享屏幕 / 远程控制", "severity": 3,
     "rule": "要你开启『屏幕共享』或安装远程控制软件的，都是诈骗",
     "patterns": [r"(共享屏幕|屏幕共享|远程协助|远程控制|向日葵|todesk|teamviewer|会议软件.{0,6}(协助|操作))"]},
    {"id": "secrecy", "name": "要求保密 / 单独行动", "severity": 3,
     "rule": "要你『别告诉家人 / 老师 / 警察』、单独行动的，几乎一定是诈骗",
     "patterns": [r"((不要|别|勿).{0,4}(告诉|让|声张|报警)|保密|单独(操作|前往|行动))"]},
    {"id": "impersonate", "name": "冒充权威 / 熟人身份", "severity": 2,
     "rule": "八个凡是·第五 / 六条：自称公检法要求转入『安全账户』、或自称领导熟人借钱的，都是诈骗",
     "patterns": [r"(公安|警官|检察院|法院|公检法|反诈中心|涉嫌(洗钱|犯罪))",
                  r"(自称|冒充|我是).{0,4}(客服|领导|辅导员|老师|学长|班主任|快递)"]},
    {"id": "install", "name": "诱导下载 App / 点不明链接", "severity": 2,
     "rule": "八个凡是·第七 / 八条：发来不明链接、要你下载陌生 App 的，都是诈骗",
     "patterns": [r"(下载.{0,5}(App|软件|应用|客户端)|点(击)?.{0,6}链接|扫码下载|安装.{0,5}(App|软件)|https?://|[a-z0-9-]+\.(xyz|top|cc|vip|link))"]},
    {"id": "toogood", "name": "承诺超额 / 稳赚回报", "severity": 2,
     "rule": "八个凡是·第一 / 二条：宣称稳赚不赔、内幕消息、高额返利、刷单返佣的，都是诈骗",
     "patterns": [r"(稳赚|稳定.{0,2}收益|高额(返利|收益|回报)|返利|返佣|内幕|必过|包过|日入|轻松赚|高回报|秒到账|低价转让|翻倍|空投)"]},
    {"id": "offplatform", "name": "诱导脱离平台私下交易", "severity": 2,
     "rule": "让你脱离正规平台、私下加微信 / QQ 交易的，要警惕",
     "patterns": [r"(私下交易|加(我)?(微信|qq)|脱离平台|不(要|走)平台|平台外|走线下|绕过.{0,4}平台)"]},
    {"id": "urgency", "name": "制造紧迫 / 恐吓", "severity": 1,
     "rule": "制造紧张气氛、催你『立即处理』、以冻结 / 涉案恐吓的，多半是诈骗",
     "patterns": [r"(立即|马上|尽快|限时|否则|冻结|涉案|通缉|逾期|影响征信|不然就|最后(期限|机会))"]},
]


@dataclass
class SignalHit:
    id: str
    name: str
    severity: int
    rule: str


def extract_signals(text: str) -> list[SignalHit]:
    """抽取输入中命中的诈骗行为信号。"""
    out: list[SignalHit] = []
    for s in SIGNALS:
        for p in s["patterns"]:
            try:
                if re.search(p, text, re.IGNORECASE):
                    out.append(SignalHit(s["id"], s["name"], s["severity"], s["rule"]))
                    break
            except re.error:
                continue
    return out


def behavior_assessment(hits: list[SignalHit]) -> tuple[float, str | None]:
    """根据红旗组合给出 (行为风险增量, 行为研判等级)。

    研判等级用于在案例库未命中时兜底——这正是对未知骗局的泛化能力：
    - 高危：≥2 个强信号，或严重度合计 ≥ 6（如 转账 + 索要验证码 + 紧迫）
    - 中危：≥2 个信号，或严重度合计 ≥ 3
    - 低-中：单个弱/中信号
    """
    if not hits:
        return 0.0, None
    sev = sum(h.severity for h in hits)
    strong = sum(1 for h in hits if h.severity >= 3)
    if strong >= 2 or sev >= 6:
        level = "high"
    elif len(hits) >= 2 or sev >= 3:
        level = "medium"
    else:
        level = "low-medium"
    return float(sev), level


if __name__ == "__main__":  # 自测
    samples = [
        "客服说我快递丢了要退款，让我下载会议软件开共享屏幕核对银行卡流水",
        "你涉嫌洗钱，请立即把钱转入安全账户配合调查，不要告诉家人",
        "今天天气不错一起去图书馆吧",  # 非诈骗
        "一个库里完全没有的新骗局：扫码领数字藏品空投，先转 0.1 验证地址再返高额收益",
    ]
    for t in samples:
        hits = extract_signals(t)
        sev, lvl = behavior_assessment(hits)
        print(f"\n输入：{t[:30]}")
        print(f"  红旗 {len(hits)} 个 / 严重度 {sev:.0f} / 行为研判：{lvl or '无'}")
        for h in hits:
            print(f"    · {h.name}")
