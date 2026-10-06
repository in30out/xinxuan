"""recommend.py —— 主链路：召回 -> 规则 -> 排序 -> 风险/理由。

CLI:  python prototype/recommend.py STM32F103C8T6 --top 5
"""
from __future__ import annotations
import argparse
import os
import re
import sys
import time
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import find_part, load_chips  # noqa: E402
from ranking import rank  # noqa: E402
from recall import RecallIndex, expand_terms, tokenize  # noqa: E402
from risk import TIER_NO  # noqa: E402
from rules import (CATEGORY_SYNONYMS, CATEGORY_SYNONYMS_ALL, check_rules,  # noqa: E402
                   detect_category, parse_constraints)
# NL 查询的语义相关性修正：同品类加分、封装不符显著降权（TF-IDF 无法感知这两件事）
CAT_BONUS, PKG_PENALTY = 0.20, 0.65
# 同大类但不同脚位的封装（SOT-23 vs SOT-23-5）用轻降权，避免把精确封装挤下去。
# 实测 0.90 不足以翻盘（XC6206 与 SPX3819 的原始余弦只差 0.002），取 0.75：
# 与 PKG_PENALTY(0.65) 同向但更轻，只纠正同族封装内的错排，不误伤跨封装候选。
PKG_FAMILY_PENALTY = 0.75
# 接口芯片是一个大类（RS-232/RS-485/CAN/USB 共用），TF-IDF 分不出具体协议，需按协议重排
IFACE_PROTOCOLS = (
    ("RS232", ("rs232", "rs-232", "max232", "max3232", "sp3232", "电平转换")),
    ("RS485", ("rs485", "rs-485", "rs422", "rs-422", "max485", "max3485",
               "sp3485", "sn65hvd")),
    ("CAN", ("can", "canbus", "can 总线", "tja1050", "sn65hvd230")),
    ("USB-UART", ("usb转串口", "usb 转串口", "ch340", "cp2102", "串口芯片")),
)
IFACE_BONUS = 0.15
def key_tokens_of(text: str) -> list:
    """自然语言查询的关键词（含字母/汉字且长度>=2），用于关键词覆盖率重排。"""
    return [t for t in str(tokenize(str(text))).lower().split()
            if len(t) >= 2 and any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in t)]
def soft_key_tokens(query: str, category: str = "") -> list:
    """关键词覆盖率用的 token：剔除已作硬约束处理的品类词与查询原文里出现的分词。

    品类/封装/电压已经由 detect_category + parse_constraints 实际比对，
    不能再用覆盖率二次惩罚 —— 否则 "低功耗 LDO SOT-23-5" 里 SOT-23-5 的
    分词碎片会把真正的 LDO 候选压下去。
    """
    ignore = set()
    if category:
        for alias in CATEGORY_SYNONYMS.get(category, []):
            ignore.update(a for a in alias.lower().split())
    ignore.update(t for t in key_tokens_of(query) if t in str(query).lower())
    return [t for t in key_tokens_of(query) if t not in ignore]
def detect_iface_protocol(query: str) -> str:
    """接口芯片大类里的具体协议（RS-232/RS-485/CAN/USB 转串口），无命中返回 ""。"""
    text = str(query).lower()
    for proto, keys in IFACE_PROTOCOLS:
        if any(k in text for k in keys):
            return proto
    return ""
def pkg_of(package) -> str:
    """封装归一：SOT-23-5 -> SOT235，SOT-23 -> SOT23，SOIC-8 -> SOIC8。"""
    return "".join(re.split(r"[\s\-_]+", str(package).strip().upper()))
def pkg_matches(q_pkg: str, c_pkg: str) -> str:
    """返回 exact / family / mismatch，供重排降权（family = 同族但脚位后缀不同）。

    库里的 SOT-23 / SOT-23-5 / SOT-23-6 是三种不互通的封装，必须区分脚位，
    否则 "SOT-23-5" 的查询会把 SOT-23 的候选排到前面去；而查询只写 "SOT-23"
    时，SOT-23-5/-6 都算命中（本就没有更细的要求）。
    """
    if not q_pkg or not c_pkg:
        return "exact"
    q, c = pkg_of(q_pkg), pkg_of(c_pkg)
    if q == c:
        return "exact"
    if c.startswith(q) and len(c) > len(q):
        # 候选比查询更具体：查询 SOT23 命中 SOT235/SOT236
        return "exact"
    if q.startswith(c) and len(q) > len(c):
        # 查询比候选更具体：查询 SOT235，候选是未标脚位的 SOT23 -> 同族降权
        return "family"
    return "mismatch"
def text_sort_score(raw_sim: float, cand, category: str, q_pkg: str,
                    iface_proto: str = "") -> float:
    """NL 模式的重排分：TF-IDF 余弦 + 同品类加分 - 封装不符降权 - 接口协议不符降权。"""
    score = raw_sim
    if category:
        score += CAT_BONUS if str(cand["category"]) == category else -CAT_BONUS
    verdict = pkg_matches(q_pkg, str(cand["package"]))
    if verdict == "family":
        score *= PKG_FAMILY_PENALTY
    elif verdict == "mismatch":
        score *= PKG_PENALTY
    if iface_proto:
        proto = detect_iface_protocol(str(cand.get("desc_text", "")))
        if proto == iface_proto:
            score += IFACE_BONUS
    return score
def resolve_category(df: pd.DataFrame, raw) -> str:
    """把 detect_category 的中文标签对齐到当前数据集实际使用的 category 取值。

    种子集（89 行）的 category 是中文（「线性稳压器LDO」），jlcparts 全量集是英文
    （「Power Management」）。规则里的 CATEGORY_SYNONYMS 是按中文种子集写的，因此直接用
    中文标签去过滤英文数据集会 0 命中。这里反查每个候选品类在库中的别名是否出现在查询里，
    命中几个就是几个，天然支持中英两种命名。
    """
    if not raw:
        return ""
    try:
        values = df["category"].dropna().unique().tolist()
    except Exception:
        return str(raw)
    if raw in values:
        return raw
    low = str(raw).lower()
    # 别名索引：每个库里真实存在的 category -> 它的中英同义写法（中英两套表都要查）
    hits = []
    for value in values:
        aliases = {str(value).lower(), str(value)}
        for table in (CATEGORY_SYNONYMS_ALL,):
            for zh, syns in table.items():
                if zh == value:
                    aliases.update(str(s).lower() for s in syns)
                elif any(str(s).lower() == low for s in syns):
                    aliases.update(str(s).lower() for s in syns)
        if any(a and a in low for a in aliases):
            hits.append(str(value))
    # 唯一命中就换成库里的英文标签；一个都没命中时保留模型给出的中文标签（宁可过滤为空，
    # 也不要静默退回"不过滤"），多个命中说明查询跨品类，交给词面召回。
    return hits[0] if len(hits) == 1 else ("" if hits else str(raw))


def recommend(df: pd.DataFrame, index: RecallIndex, query: str, top_n: int = 5,
              ablate: tuple = ()) -> dict:
    """对单个型号或自然语言查询给出 Top-N 推荐。

    ablate 是消融实验开关（默认空元组，不传时行为与之前完全一致），取值：
      "supply"   关闭供应链因子（只保留参数分），验证"供应链感知"到底贡献多少排序质量
      "rules"    关闭规则分（param 只取 TF-IDF 相似度），验证六维规则的价值
      "category" 关闭 NL 品类硬过滤，验证品类归一/同义词的价值
      "rerank"   关闭 NL 重排（同品类加分 + 封装族降权 + 接口协议重排）
    """
    ablate = frozenset(ablate)
    t0 = time.perf_counter()
    base = find_part(df, query)
    soft = base is None
    query_text = base["desc_text"] if base is not None else str(query)
    query_row = None
    category, filtered, q_pkg = "", 0, ""
    if base is not None:
        query_row = base
    else:
        # 自然语言查询：先做品类归一 + 硬约束解析，再构造虚拟原件用于规则对比
        category = resolve_category(df, detect_category(query))
        req = parse_constraints(query)
        q_pkg = req["package"]
        query_row = pd.Series({
            "part_no": query, "category": category, "package": req["package"],
            "pin_count": req["pin_count"],
            "vcc_min": 0.0, "vcc_max": 0.0, "temp_min": 0.0, "temp_max": 0.0,
            "price_cny": float(df["price_cny"].median()),
            # 查询文本当作"原件描述"，供电压/封装/引脚约束与功能参数指纹比对
            "description": str(query),
        })
    exclude = base["part_no"] if base is not None else ""
    # 命中品类时品类词已作硬约束，不再用关键词覆盖率二次惩罚（SOT-23-5 的分词碎片会误伤）
    key_tokens = soft_key_tokens(query, "") if (soft and not category) else []
    iface_proto = detect_iface_protocol(query) if (soft and category == "接口芯片") else ""
    weights = {t: index.idf_of(t) for t in key_tokens}
    w_sum = sum(weights.values()) or 1.0
    # 把同义品类词加权注入查询向量，让 "LDO" 这类口语词能匹配库中"线性稳压器LDO"
    recall_query = expand_terms(query_text, CATEGORY_SYNONYMS.get(category, [])) if category \
        else query_text
    cands = []
    for i, sim in index.recall(recall_query, exclude=exclude, top_k=max(top_n * 4, 20)):
        cand = df.iloc[i]
        if category and "category" not in ablate and str(cand["category"]) != category:
            filtered += 1
            continue
        if weights:
            hit = sum(w for t, w in weights.items() if t in str(cand["desc_text"]).lower())
            sim = round(sim * (0.5 + 0.5 * hit / w_sum), 4)
        # 第 4 个位置保存"进入重排前"的相似度，供 --ablate rerank 还原纯 TF-IDF 排序
        raw_sim = sim
        sort_score = raw_sim if "rerank" in ablate else \
            text_sort_score(sim, cand, category, q_pkg, iface_proto)
        cands.append((sort_score, cand, check_rules(query_row, cand, soft=soft), raw_sim))
    cands = [(c[3], c[1], c[2], c[3]) for c in cands] if "rerank" in ablate else cands
    if category and "category" not in ablate:
        # NL 模式没有原件参数，顺序即语义相关性；仅在品类过滤生效时才重排，
        # 无品类的查询保持原有顺序（不可回退既有正确结果）
        cands.sort(key=lambda c: c[0], reverse=True)
    all_rows = rank(query_row, cands, ablate=ablate)
    # 「不推荐」候选（停产/无现货/类别不符）不进主榜单，但单独列出，避免规则过滤变成静默丢弃
    rows = [r for r in all_rows if r["replacement_tier"] != TIER_NO][:top_n]
    rejected = sorted(
        (r for r in all_rows if r["replacement_tier"] == TIER_NO),
        key=lambda r: r["similarity"], reverse=True,
    )[:3]
    return {
        "query": query,
        "matched_part": None if base is None else base["part_no"],
        "mode": "text" if soft else "part",
        "category": category or None,
        "filtered_out": filtered,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        "results": rows,
        "rejected": rejected,
    }
def render(result: dict) -> str:
    lines = [
        f"查询: {result['query']}  模式: {'自然语言召回' if result['mode'] == 'text' else '型号替换'}  "
        f"匹配原件: {result['matched_part']}  耗时: {result['elapsed_ms']} ms",
        "-" * 108,
    ]
    for i, r in enumerate(result["results"], 1):
        lines.append(
            f"{i}. {r['part_no']:<24} {r['manufacturer']:<22} 总分 {r['score']:.3f} "
            f"相似 {r['similarity']:.2f} 规则 {r['rule_score']:.2f} 供应链 {r['supply']:.2f}"
        )
        lines.append(
            f"   {r['risk_level']} | {r['replacement_tier']} | {r['package']}/{r['pin_count']}脚 "
            f"| 库存 {r['stock']} | ¥{r['price_cny']:.2f} | 交期 {r['lead_time_days']}天 | {r['lifecycle']}"
        )
        lines.append(f"   理由: {r['summary']}")
    if result.get("rejected"):
        lines.append("-" * 108)
        lines.append("⚠ 规则已排除的候选（同系列但不可直接选用，列出以备核对）:")
        for r in result["rejected"]:
            lines.append(
                f"   ✗ {r['part_no']:<24} {r['risk_level']} | {r['replacement_tier']} | "
                f"相似 {r['similarity']:.2f} | 库存 {r['stock']} | {r['lifecycle']} | {r['reasons'][0]}"
            )
    return "\n".join(lines)
def main() -> None:
    ap = argparse.ArgumentParser(description="芯选 —— 芯片替代选型智能推荐 CLI")
    ap.add_argument("part", help="芯片型号或自然语言需求")
    ap.add_argument("--top", type=int, default=5, help="返回条数")
    ap.add_argument("--csv", default=None, help="自定义数据 CSV")
    args = ap.parse_args()
    df = load_chips(args.csv)
    index = RecallIndex(df)
    print(render(recommend(df, index, args.part, args.top)))
if __name__ == "__main__":
    main()
