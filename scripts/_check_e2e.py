"""_check_e2e.py -- end-to-end smoke probe used by scripts/check.ps1.

Runs one part-number query and one natural-language query through the full
pipeline (recall -> rules -> supply ranking -> risk/grade) and prints the top
hit. Exits 0 on success, 1 if either query yields no result.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "prototype"))

from data_loader import load_chips  # noqa: E402
from recall import RecallIndex  # noqa: E402
from recommend import recommend  # noqa: E402

QUERIES = ["STM32F103C8T6", "3.3V low-power LDO SOT-23-5".replace("low-power", "\u4f4e\u529f\u8017")]


def main() -> int:
    df = load_chips(os.environ.get("CHIPS_CSV") or None)
    index = RecallIndex(df)

    for query in QUERIES:
        res = recommend(df, index, query, 3)
        results = res.get("results") or []
        if not results:
            print(f"FAIL no result for: {query}")
            return 1
        top = results[0]
        print(
            "  {q:<28} -> {part:<24} {risk:<8} {tier:<16} {score:.3f}  "
            "({ms:.1f} ms, hits={n})".format(
                q=query,
                part=str(top["part_no"]),
                risk=str(top["risk_level"]),
                tier=str(top["replacement_tier"]),
                score=float(top["score"]),
                ms=float(res["elapsed_ms"]),
                n=len(results),
            )
        )

    print("E2E_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
