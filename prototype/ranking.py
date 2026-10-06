"""ranking.py —— 供应链感知加权排序（权重公式可解释、可调参）。

参数分 param = 0.70 * 规则分 + 0.30 * TF-IDF 余弦相似度
供应链因子 supply = w_stock^0.45 * w_price^0.20 * w_lead^0.20 * w_life^0.15
最终分 total = param * (0.65 + 0.35 * supply)        # 供应链最多影响 ±35%
其中 param = 0.70*规则分 + 0.30*相似度；自然语言查询没有原件参数，param 直接取相似度。
其中（stock 为库存，price 为单价，lead 为交期天数）
  w_stock = clamp(log1p(stock)/log1p(1e6), 0, 1)      # 1e6 颗库存视为满分
  w_price = clamp(1 - (price/原价 - 1) * 0.15, 0.6, 1) # 涨价 10% 约扣 1.5%
  w_lead  = clamp(1 - (lead - 7)/60, 0.4, 1)           # 7 天为基准，67 天触底
  w_life  = {量产:1.0, NRND:0.75, 预览:0.6, EOL:0.15, 未知:0.7}
缺货（stock<=0）时 supply *= 0.2 并在风险模块标红。
"""
from __future__ import annotations

import math

import pandas as pd

LIFECYCLE_W = {"量产": 1.0, "NRND": 0.75, "预览": 0.6, "EOL": 0.15, "未知": 0.7}
W_STOCK, W_PRICE, W_LEAD, W_LIFE = 0.45, 0.20, 0.20, 0.15
# 供应链因子的影响力上限：total = param * (0.65 + 0.35*supply)
SUPPLY_IMPORTANCE = 0.35


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def supply_factor(query: pd.Series, cand: pd.Series) -> tuple:
    """返回 (supply∈[0,1], 各分项权重详情)。"""
    stock = float(cand["stock"])
    w_stock = clamp(math.log1p(stock) / math.log1p(1_000_000), 0.0, 1.0)

    q_price = float(query["price_cny"])
    c_price = float(cand["price_cny"])
    price_ratio = (c_price / q_price) if q_price > 0 else 1.0
    w_price = clamp(1 - (price_ratio - 1) * 0.15, 0.6, 1.0)

    lead = float(cand["lead_time_days"])
    w_lead = clamp(1 - (lead - 7) / 60.0, 0.4, 1.0)
    w_life = LIFECYCLE_W.get(str(cand["lifecycle"]), 0.7)

    supply = (w_stock ** W_STOCK) * (w_price ** W_PRICE) * (w_lead ** W_LEAD) * (w_life ** W_LIFE)
    if stock <= 0:
        supply *= 0.2
    return clamp(supply, 0.0, 1.0), {
        "w_stock": round(w_stock, 4),
        "w_price": round(w_price, 4),
        "w_lead": round(w_lead, 4),
        "w_life": w_life,
        "price_ratio": round(price_ratio, 3),
    }


def total_score(rule_score: float, similarity: float, supply: float, soft: bool = False) -> float:
    """参数分与供应链因子的合成；soft=True（自然语言查询）时参数分只看相似度。"""
    param = similarity if soft else 0.70 * rule_score + 0.30 * similarity
    return round(clamp(param, 0, 1) * (1 - SUPPLY_IMPORTANCE + SUPPLY_IMPORTANCE * supply), 4)


def rank(query: pd.Series, candidates: list, ablate=frozenset()) -> list:
    """candidates: [(sort_sim, cand_series, rule_result, raw_sim?), ...] -> 排序结果。

    第 1 个元素是实际参与排序的相似度（NL 模式下已经过同品类加分/封装降权）；
    第 4 个元素（raw_sim）是进入重排前的纯 TF-IDF 余弦，**只用于 `--ablate rerank`
    还原基准排序**，正常路径不用它。

    ablate 是消融实验开关（默认空集，行为与不带该参数完全一致）：
      "supply"   供应链因子不参与（supply 固定为 1.0，剩 0.65+0.35*1 的常数因子）
      "rules"    规则分不参与，param 只取相似度
      "category" / "rerank"  由 recommend.py 在候选生成阶段处理（此处无副作用）
    风险评级与替代等级不受影响 —— 消融只改排序，不改过滤，这样 E4 才有可比性。
    """
    from risk import assess  # 局部导入避免循环依赖

    rows = []
    for item in candidates:
        cand, rule_res = item[1], item[2]
        sim = item[0]
        supply, detail = supply_factor(query, cand)
        if "supply" in ablate:
            supply = 1.0
        effective_rule = 0.0 if "rules" in ablate else rule_res["score"]
        score = total_score(effective_rule, sim, supply, soft=rule_res.get("soft", False))
        risk = assess(query, cand, rule_res, supply)
        rows.append({
            "part_no": cand["part_no"],
            "manufacturer": cand["manufacturer"],
            "category": cand["category"],
            "package": cand["package"],
            "pin_count": int(cand["pin_count"]),
            "price_cny": float(cand["price_cny"]),
            "stock": int(cand["stock"]),
            "lead_time_days": int(cand["lead_time_days"]),
            "lifecycle": cand["lifecycle"],
            "similarity": round(sim, 4),
            "rule_score": rule_res["score"],
            "supply": round(supply, 4),
            "score": score,
            "supply_detail": detail,
            "checks": rule_res["checks"],
            "risk_level": risk["level"],
            "replacement_tier": risk["tier"],
            "reasons": risk["reasons"],
            "summary": risk["summary"],
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


if __name__ == "__main__":
    from data_loader import load_chips

    df = load_chips()
    a = df[df.part_no == "STM32F103C8T6"].iloc[0]
    b = df[df.part_no == "GD32F103C8T6"].iloc[0]
    s, d = supply_factor(a, b)
    print("supply=", round(s, 4), d)
