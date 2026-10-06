"""diag_nl_rank.py —— 打印 NL 查询在每个阶段的候选分（定位召回/重排/规则哪一步错）。

只读诊断，不改业务代码。用法：
    $env:PYTHONPATH = "<repo>\\.deps;<repo>\\prototype"
    & <DSH python> scripts\\diag_nl_rank.py "3.3V 低功耗 LDO SOT-23-5"
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "prototype"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from data_loader import load_chips  # noqa: E402
from recall import RecallIndex, expand_terms  # noqa: E402
from recommend import detect_iface_protocol, pkg_matches, text_sort_score  # noqa: E402
from rules import CATEGORY_SYNONYMS, check_rules, detect_category, parse_constraints  # noqa: E402
from recommend import resolve_category  # noqa: E402


def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else "3.3V 低功耗 LDO SOT-23-5"
    df = load_chips()
    index = RecallIndex(df)
    category = resolve_category(df, detect_category(query))
    req = parse_constraints(query)
    print(f"query={query!r}\ncategory={category!r}  package={req['package']!r}  "
          f"pin={req['pin_count']}  iface={detect_iface_protocol(query)!r}")
    print(f"synonyms={CATEGORY_SYNONYMS.get(category, [])}")
    rq = expand_terms(query, CATEGORY_SYNONYMS.get(category, [])) if category else query
    print(f"recall_query={rq!r}\n")

    q_row = pd.Series({
        "part_no": query, "category": category, "package": req["package"],
        "pin_count": req["pin_count"], "vcc_min": 0.0, "vcc_max": 0.0,
        "temp_min": 0.0, "temp_max": 0.0,
        "price_cny": float(df["price_cny"].median()), "description": str(query),
    })
    print(f"{'#':>2} {'part_no':<24} {'raw':>7} {'sort':>7} {'pkg':>8} "
          f"{'rule':>5} {'cat?':>5}")
    print("-" * 68)
    shown = 0
    for rank_i, (i, sim) in enumerate(index.recall(rq, top_k=24), 1):
        cand = df.iloc[i]
        if category and str(cand["category"]) != category:
            continue
        shown += 1
        res = check_rules(q_row, cand, soft=True)
        sort = text_sort_score(sim, cand, category, req["package"])
        flag = "OK" if str(cand["category"]) == category else "--"
        print(f"{rank_i:>2} {str(cand['part_no']):<24} {sim:7.4f} {sort:7.4f} "
              f"{pkg_matches(req['package'], str(cand['package'])):>8} "
              f"{res['score']:5.2f} {flag:>5}")
        if shown >= 16:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
