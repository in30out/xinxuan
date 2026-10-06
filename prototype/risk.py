"""risk.py —— 风险评级、替代等级与推荐理由生成。

替代等级（按保守程度递进）：Pin-to-Pin 直接替换（封装/引脚/电压/温度/功能均无 fail 且有兼容证据）
-> 功能等效需改板（电压可覆盖但封装引脚不同或缺证据）-> 参考替代（功能冲突或电压仅部分覆盖）
-> 不推荐（类别不同 / EOL / 无现货）。🟢低 / 🟡中 / 🔴高（停产、零库存、电压不兼容、功能冲突触发 🔴）
"""
from __future__ import annotations

import pandas as pd

LEVEL_LOW, LEVEL_MID, LEVEL_HIGH = "🟢低风险", "🟡中风险", "🔴高风险"
TIER_P2P = "Pin-to-Pin 直接替换"
TIER_REDESIGN = "功能等效需改板"
TIER_REF = "参考替代"
TIER_NO = "不推荐"

# 描述中出现这些关键词才认为厂商有引脚兼容声明（避免仅凭封装/脚数误判 Pin-to-Pin）
P2P_KEYWORDS = ("引脚兼容", "引脚定义", "pin-to-pin", "直接替换", "兼容", "compatible")


def _status(rule_res: dict, name: str, default: str = "fail") -> str:
    for c in rule_res["checks"]:
        if c["rule"] == name:
            return c["status"]
    return default


def _soft_result(cand: pd.Series, f_status: str) -> dict:
    """自然语言查询：没有原件参数，跳过硬规则，仅按功能参数冲突 + 供货状态给保守结论。"""
    stock = int(cand["stock"])
    lifecycle = str(cand["lifecycle"])
    lead = int(cand["lead_time_days"])
    reasons = ["自然语言查询未指定封装/电压等硬约束，参数兼容性需人工核对"]
    if f_status == "fail":
        level, tier = LEVEL_HIGH, TIER_NO
        reasons.insert(0, "功能关键参数与查询要求冲突（输出电压/位宽/容量/沟道等），功能不等效")
    elif lifecycle == "EOL" or stock <= 0:
        level, tier = LEVEL_HIGH, TIER_NO
        reasons.append("停产或无现货，不建议选用")
    elif lifecycle == "NRND" or lead > 30:
        level, tier = LEVEL_MID, TIER_REF
        reasons.append("供货状态欠佳（NRND 或长交期），需确认长期供货")
    else:
        level, tier = LEVEL_MID, TIER_REF
    summary = (f"{cand['part_no']}（{cand['manufacturer']}）语义召回候选；"
               f"库存 {stock} 颗，交期 {lead} 天，状态 {lifecycle}；"
               "需按封装/供电/温度逐项核对后再选型")
    return {"level": level, "tier": tier, "reasons": reasons, "summary": summary}


def assess(query: pd.Series, cand: pd.Series, rule_res: dict, supply: float) -> dict:
    """返回 {level, tier, reasons, summary}。"""
    if rule_res.get("soft"):
        return _soft_result(cand, _status(rule_res, "功能一致", "pass"))

    reasons = []
    stock = int(cand["stock"])
    lifecycle = str(cand["lifecycle"])

    cat_ok = _status(rule_res, "类别一致") == "pass"
    pkg_ok = _status(rule_res, "封装一致") == "pass"
    pin_ok = _status(rule_res, "引脚一致") == "pass"
    v_status = _status(rule_res, "电压兼容")
    f_status = _status(rule_res, "功能一致")
    t_ok = _status(rule_res, "温度覆盖") == "pass"
    desc = str(cand.get("description", ""))
    # 引脚兼容证据：优先看人工维护的 p2p_with 关系表，其次看厂商描述措辞
    p2p_pairs = {p.strip().upper() for p in str(cand.get("p2p_with", "")).split(";") if p.strip()}
    p2p_pairs |= {p.strip().upper() for p in str(query.get("p2p_with", "")).split(";") if p.strip()}
    evidence = str(cand["part_no"]).upper() in p2p_pairs or any(k in desc.lower() for k in P2P_KEYWORDS)

    # ---------- 风险等级 ----------
    level = LEVEL_LOW
    if lifecycle == "EOL":
        level = LEVEL_HIGH
        reasons.append("原厂已停产（EOL），仅可做最后购买，不建议新设计采用")
    if stock <= 0:
        level = LEVEL_HIGH
        reasons.append("现货库存为 0，存在断供风险")
    if v_status == "fail":
        level = LEVEL_HIGH
        reasons.append("供电范围与原型号无交集，直接替换可能不工作或损坏")
    if f_status == "fail":
        level = LEVEL_HIGH
        reasons.append("功能关键参数与原型号冲突（输出电压/位宽/容量/沟道等），功能不等效")
    if lifecycle == "NRND" and level != LEVEL_HIGH:
        level = LEVEL_MID
        reasons.append("原厂标记 NRND（不推荐新设计），中长期供货存疑")
    if v_status == "warn" and level != LEVEL_HIGH:
        level = LEVEL_MID
        reasons.append("供电范围仅部分覆盖原件，需确认系统实际工作电压")
    if level == LEVEL_LOW:
        if not pkg_ok or not pin_ok:
            level = LEVEL_MID
            reasons.append("封装/引脚不一致，需改板或加转接，属于中等风险")
        if not t_ok:
            level = LEVEL_MID
            reasons.append("温度等级无法完全覆盖，需评估使用环境")
        if not cat_ok:
            level = LEVEL_MID
            reasons.append("类别不同，仅可作为功能参考，需重新设计外围电路")
        if int(cand["lead_time_days"]) > 30:
            level = LEVEL_MID
            reasons.append(f"交期 {int(cand['lead_time_days'])} 天偏长，需提前下单")
    if level == LEVEL_LOW:
        reasons.append("参数、封装、供电、温度均满足，现货充足，可直接批量替换")
    if not cat_ok:  # 类别不符是最重要的否决理由，放到最前
        cr = "类别不同，仅可作为功能参考，需重新设计外围电路"
        reasons = [cr] + [x for x in reasons if x != cr]

    # ---------- 替代等级 ----------
    # 零容忍硬约束：类别不符、封装不同、脚位差 >2、电压零交集、功能参数冲突、温度覆盖过低
    # 都属于"这块板子用不了"的情形 → 直接落「不推荐」，不再出现在主榜单（只列在 rejected 供核对）。
    # 该判断复用 rules 侧的 hard_fail，避免两处口径漂移。
    critical_failed = [c["rule"] for c in rule_res.get("checks", [])
                       if c["status"] == "fail" and c.get("critical")]
    pin_like = pkg_ok and pin_ok and v_status != "fail" and t_ok and f_status != "fail"
    if not cat_ok or lifecycle == "EOL" or stock <= 0 or rule_res.get("hard_fail"):
        tier = TIER_NO
    elif f_status == "fail":
        tier = TIER_REF
    elif pin_like and evidence:
        tier = TIER_P2P
    elif pkg_ok and pin_ok:
        tier = TIER_REDESIGN
        if not evidence:
            reasons.append("封装引脚一致但描述中无引脚兼容声明/内核架构不同，需核对引脚定义与固件")
    else:
        tier = TIER_REF
    if critical_failed:
        reasons.append("命中零容忍硬约束（" + "、".join(critical_failed) + "），已列入不推荐")

    # ---------- 一句话推荐理由 ----------
    parts = [f"{cand['part_no']}（{cand['manufacturer']}）"]
    warned = [c["rule"] for c in rule_res["checks"] if c["status"] == "warn"]
    if rule_res["failed_rules"]:
        parts.append("不达标规则: " + "/".join(rule_res["failed_rules"]))
    elif warned:
        parts.append("关键规则达标，需确认: " + "/".join(warned))
    else:
        parts.append("关键规则全部达标")
    parts.append(f"库存 {stock} 颗/单价 ¥{float(cand['price_cny']):.2f}/交期 {int(cand['lead_time_days'])} 天")
    parts.append(f"供应链因子 {supply:.2f}")
    parts.append({
        TIER_P2P: "可 Pin-to-Pin 直接替换",
        TIER_REDESIGN: "功能等效，需修改 PCB 布局或固件",
        TIER_REF: "仅供参考替代，需完整评估",
        TIER_NO: "不推荐作为替代",
    }[tier])
    summary = "；".join(parts)

    return {"level": level, "tier": tier, "reasons": reasons, "summary": summary}


if __name__ == "__main__":
    from data_loader import load_chips
    from rules import check_rules

    df = load_chips()
    a = df[df.part_no == "LD1117S33TR"].iloc[0]
    b = df[df.part_no == "AMS1117-3.3"].iloc[0]
    r = assess(a, b, check_rules(a, b), supply=0.9)
    print(r["level"], "|", r["tier"])
    print(r["summary"])
