"""eval.py -- offline evaluation for 芯选 (E1/E2/E4 of the design doc).

What it measures, and why each metric is here:

  E1 Top-K hit rate   -- for a part in the label set, does the expected substitute
                         appear in the returned Top-K? This is the "does the system
                         actually find the right answer" number.
  E2 latency          -- wall-clock per query, reported as mean / p95.
  E4 self-consistency -- share of RETURNED rows that still carry a hard rule
                         failure. Hard constraints are supposed to be zero-tolerance,
                         so this must be exactly 0; anything else is a filter bug.

Honesty rules baked into this file:
  * `hit` only counts pins that are genuinely pin-compatible. A functional drop-in
    that needs a board change is listed under `functional`, never counted as a pin hit.
  * Cases whose expected answers do not exist in the loaded CSV are reported as
    SKIPPED, not as failures -- the seed set (89 rows) is smaller than the real
    dataset, so a case can legitimately be absent.
  * Every printed number comes from a real run of `recommend.recommend()`.

Usage
-----
    set PYTHONPATH=.deps
    python experiments/eval.py                                  # seed data
    python experiments/eval.py --csv data/chips_real_semi.csv --top 5
    python experiments/eval.py --json out/eval.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "prototype"))

from data_loader import find_part, load_chips  # noqa: E402
from recall import RecallIndex  # noqa: E402
from recommend import recommend  # noqa: E402

# --- label set ---------------------------------------------------------------------------
# Every entry was derived from the actual rows in data/samples/chips_seed.csv, i.e. from
# evidence present in the dataset (a `p2p_with` reference or an explicit "兼容/引脚兼容"
# claim in the description). Keep this file free of invented compatibility claims.
CASES = [
    {
        "query": "STM32F103C8T6",
        "note": "国内 MCU 替代最典型场景",
        "pins": ["APM32F103C8T6", "CH32V203C8T6"],
        "functional": ["CH32F103C8T6", "GD32F103C8T6"],
        "expect_top1": "APM32F103C8T6",
    },
    {
        "query": "W25Q64JVSSIQ",
        "note": "SPI NOR Flash，另颗料描述里写明兼容",
        "pins": ["GD25Q64ESIG"],
    },
    {
        "query": "CH340G",
        "note": "USB 转串口，仅外部电容不同（CH340N 是 SOP-8，属改板替代，不计入 pin 命中）",
        "pins": ["CH340C"],
        "functional": ["CH340N"],
    },
    {
        "query": "SP3232EEN",
        "note": "RS-232 收发器（SP3485EN/MAX485 是 RS-485，类别相同但封装不同，应被排除）",
        "pins": ["MAX3232ESE+"],
    },
    {
        "query": "TLC555CDR",
        "note": "CMOS 定时器。NE555DR 温度为 0~70℃、仅覆盖原件 -40~85℃ 需求的 82%，"
                "按 §3.4.2 的校准判 warn，因此同封装同脚位的 NE555DR 仍应入选",
        "pins": ["NE555DR"],
        "functional": ["ICM7555IBAZ"],
    },
    {
        "query": "SP3485EN",
        "note": "3.3V RS-485。MAX3485ESA 同封装同脚位同电压区间，是唯一真正 Pin-to-Pin 的候选；"
                "MAX485ESA+ 是 5V 器件，电压零交集，属「参考替代」而非 pin 替代",
        "pins": ["MAX3485ESA"],
        "functional": ["MAX485ESA+"],
    },
    {
        "query": "AMS1117-3.3",
        "note": "LDO 替代（LM1117 与 LD1117 均在数据中互为兼容）",
        "pins": ["LM1117-3.3"],
        "functional": ["LD1117S33TR"],
    },
]

# Natural-language cases: assert the category and package shape of the Top-1, not a part no.
NL_CASES = [
    {"query": "3.3V 低功耗 LDO SOT-23-5", "category": "线性稳压器LDO", "pkg": "SOT235"},
    {"query": "RS485 收发器 SOIC-8", "category": "接口芯片", "pkg": "SOIC8"},
    {"query": "RS232 电平转换", "category": "接口芯片"},
    {"query": "24V 转 5V DC-DC", "category": "DC-DC变换器"},
    {"query": "16位 ADC 四通道", "category": "数据转换器"},
    {"query": "EEPROM I2C 32Kbit", "category": "存储器"},
    {"query": "运放 SOIC-8", "category": "运算放大器"},
    {"query": "光耦 隔离 DIP-4", "category": "光耦"},
    {"query": "MOSFET N沟道 SOT-23", "category": "MOSFET"},
]

# Hard constraints are supposed to be zero-tolerance: a candidate whose check carries
# `critical=True` must never appear in the returned ranking. Warnings (pin delta <= 2,
# partial voltage/temperature coverage) are an accepted, documented downgrade.
VERDICT = {"pass": "PASS", "fail": "FAIL", "info": "INFO"}


def pkg_token(package: str) -> str:
    return "".join(ch for ch in str(package).upper() if ch.isalnum())


def critical_failures(row: dict) -> list:
    """Rule names that failed AND were flagged as must-not-recommend."""
    return [c["rule"] for c in row.get("checks", [])
            if c.get("status") == "fail" and c.get("critical")]


def run_part_cases(df, index, top_n: int, out: list, ablate: tuple = ()) -> dict:
    stats = {"total": 0, "skipped": 0, "hit_top1": 0, "hit_topk": 0,
             "pin_hit_top1": 0, "pin_total": 0, "top1_ok": 0, "top1_expected_present": 0,
             "order_ok": 0, "order_total": 0, "violations": 0, "rows": 0}
    latencies = []
    for case in CASES:
        src = find_part(df, case["query"])
        if src is None:
            stats["skipped"] += 1
            out.append({"query": case["query"], "verdict": "SKIPPED",
                        "why": "query part not present in this CSV"})
            continue
        present = [p for p in case["pins"] + case.get("functional", [])
                   if find_part(df, p) is not None]
        if not present:
            stats["skipped"] += 1
            out.append({"query": case["query"], "verdict": "SKIPPED",
                        "why": "no labelled substitute present in this CSV"})
            continue
        stats["total"] += 1
        res = recommend(df, index, case["query"], top_n, ablate=ablate)
        latencies.append(res["elapsed_ms"])
        got = [r["part_no"] for r in res["results"]]
        expect = [p for p in case["pins"] if p in present]

        pin_expected = [p for p in expect if p in got]
        stats["pin_total"] += len(expect)
        stats["pin_hit_top1"] += 1 if (expect and got and got[0] == expect[0]) else 0
        if pin_expected:
            stats["hit_topk"] += 1
        if expect and got and got[0] == expect[0]:
            stats["hit_top1"] += 1
        if case.get("expect_top1"):
            stats["top1_expected_present"] += 1
            if got and got[0] == case["expect_top1"]:
                stats["top1_ok"] += 1
        if len(expect) >= 2:
            stats["order_total"] += 1
            positions = [got.index(p) for p in expect if p in got]
            if len(positions) == len(expect) and positions == sorted(positions):
                stats["order_ok"] += 1

        bad = [(r["part_no"], critical_failures(r)) for r in res["results"] if critical_failures(r)]
        stats["violations"] += len(bad)
        stats["rows"] += len(res["results"])
        out.append({
            "query": case["query"], "note": case["note"], "verdict": "PASS" if pin_expected else "FAIL",
            "expected_pins": case["pins"], "got_top": got[:top_n],
            "hard_failures": bad, "elapsed_ms": res["elapsed_ms"],
            "top1": got[0] if got else None,
        })
    return stats, latencies


def run_nl_cases(df, index, top_n: int, out: list, ablate: tuple = ()) -> dict:
    stats = {"total": 0, "cat_ok": 0, "pkg_ok": 0, "pkg_total": 0, "empty": 0,
             # 只看 Top-1 是否为要求封装的料 —— 这是 NL 重排真正起作用的地方：
             # Top-K 只要有一条命中就永远看得见，掩盖了"错的料排在第一位"这个问题。
             "pkg_top1": 0, "pkg_rank_sum": 0, "pkg_rank_n": 0}
    for case in NL_CASES:
        res = recommend(df, index, case["query"], top_n, ablate=ablate)
        top = res["results"][0] if res["results"] else None
        stats["total"] += 1
        if top is None:
            stats["empty"] += 1
            out.append({"query": case["query"], "verdict": "FAIL", "why": "empty result"})
            continue
        # rank() rows carry package but not category, so resolve the category from the CSV.
        src = find_part(df, top["part_no"])
        got_category = str(src["category"]) if src is not None else "?"
        cat_ok = got_category == case["category"]
        want_pkg = case.get("pkg")
        pkg_ok = True if not want_pkg else (pkg_token(top["package"]) == want_pkg
                                            or pkg_token(top["package"]).startswith(want_pkg))
        stats["cat_ok"] += 1 if cat_ok else 0
        if want_pkg:
            stats["pkg_total"] += 1
            stats["pkg_ok"] += 1 if pkg_ok else 0
            stats["pkg_top1"] += 1 if pkg_ok else 0
            # 期望封装在结果里的第几位（1 基）；找不到记 0，用于算 MRR 式的"封装排名"
            pos = 0
            for i, r in enumerate(res["results"], 1):
                if pkg_token(r["package"]) == want_pkg or pkg_token(r["package"]).startswith(want_pkg):
                    pos = i
                    break
            if pos:
                stats["pkg_rank_sum"] += pos
                stats["pkg_rank_n"] += 1
        ok = cat_ok and pkg_ok
        out.append({"query": case["query"], "verdict": "PASS" if ok else "FAIL",
                    "want_category": case["category"], "got_category": got_category,
                    "want_pkg": want_pkg, "got_pkg": top["package"], "top1": top["part_no"]})
    return stats


def print_table(title: str, rows: list, columns: list) -> None:
    print(f"\n== {title} ==")
    widths = [max(len(str(c)), *(len(str(r.get(c, ""))) for r in rows)) if rows else len(str(c))
              for c in columns]
    print("  " + "  ".join(str(c).ljust(w) for c, w in zip(columns, widths)))
    for r in rows:
        print("  " + "  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(columns, widths)))


# ---------------------------------------------------------------------------------------
# Ablation variants (E3). Each one disables exactly ONE optional mechanism; the baseline
# ("full") keeps everything on. Nothing here touches the hard-constraint filter, so the
# E4 violation rate must stay 0 in every variant -- that is the point of the comparison.
ABLATIONS = [
    ("full", (), "完整方案（基准）"),
    ("no-supply", ("supply",), "关闭供应链因子（只按参数分排序）"),
    ("no-rules", ("rules",), "关闭六维规则分（只按 TF-IDF 相似度排序）"),
    ("no-category", ("category",), "关闭 NL 品类硬过滤与同义词注入"),
    ("no-rerank", ("rerank",), "关闭 NL 重排（同品类加分/封装族降权/协议重排）"),
]


def evaluate_config(df, index, top_n: int, ablate: tuple) -> dict:
    """Run the whole case suite once under one ablation setting."""
    part_rows: list = []
    pstats, latencies = run_part_cases(df, index, top_n, part_rows, ablate)
    nl_rows: list = []
    nstats = run_nl_cases(df, index, top_n, nl_rows, ablate)
    return {"stats": (pstats, nstats), "part": part_rows, "nl": nl_rows,
            "latencies": latencies}


def ablation_rows(results: dict) -> list:
    rows = []
    for name, _ablate, why in ABLATIONS:
        pstats, nstats = results[name]["stats"]
        latencies = results[name]["latencies"]
        mean = statistics.mean(latencies) if latencies else 0.0
        rows.append({
            "variant": name,
            "part_top1": f"{pstats['hit_top1']}/{pstats['total']}",
            "part_topK": f"{pstats['hit_topk']}/{pstats['total']}",
            "nl_cat": f"{nstats['cat_ok']}/{nstats['total']}",
            "nl_pkg_top1": f"{nstats['pkg_top1']}/{nstats['pkg_total']}",
            "nl_empty": nstats["empty"],
            "E4": f"{pstats['violations']}/{pstats['rows']}",
            "mean_ms": f"{mean:.1f}",
            "说明": why,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="芯选 offline evaluation")
    ap.add_argument("--csv", default=None, help="chips CSV (default: data/samples/chips_seed.csv)")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--json", default=None, help="also write raw results to this path")
    ap.add_argument("--ablate", action="store_true",
                    help="also run E3: the baseline plus one variant per disabled mechanism")
    args = ap.parse_args()

    t0 = time.perf_counter()
    df = load_chips(args.csv)
    index = RecallIndex(df)
    warmup = time.perf_counter() - t0

    print(f"芯选 evaluation  |  rows={len(df)}  top={args.top}  "
          f"csv={args.csv or 'data/samples/chips_seed.csv'}")
    print(f"索引构建 {warmup*1000:.0f} ms")

    results = {name: evaluate_config(df, index, args.top, ablate)
               for name, ablate, _why in ABLATIONS} if args.ablate else \
              {"full": evaluate_config(df, index, args.top, ())}
    pstats, nstats = results["full"]["stats"]
    part_rows, nl_rows = results["full"]["part"], results["full"]["nl"]
    latencies = results["full"]["latencies"]

    print_table("型号替换用例", part_rows,
                ["query", "verdict", "top1", "expected_pins", "hard_failures", "elapsed_ms"])
    print_table("自然语言用例", nl_rows,
                ["query", "verdict", "want_category", "got_category", "got_pkg", "top1"])

    print("\n== 汇总 ==")
    if pstats["total"]:
        print(f"  E1 型号用例           : {pstats['total']} 例（跳过 {pstats['skipped']} 例，数据集缺料）")
        print(f"     Top-1 命中         : {pstats['hit_top1']}/{pstats['total']}"
              f" = {100.0*pstats['hit_top1']/pstats['total']:.1f}%")
        print(f"     Top-{args.top} 含任一预期 Pin-to-Pin : {pstats['hit_topk']}/{pstats['total']}"
              f" = {100.0*pstats['hit_topk']/pstats['total']:.1f}%")
        print(f"     有序性（预期顺序未被颠倒）: {pstats['order_ok']}/{pstats['order_total']}")
    if nstats["total"]:
        print(f"  E1 自然语言用例       : {nstats['total']} 例，空结果 {nstats['empty']}")
        print(f"     品类正确           : {nstats['cat_ok']}/{nstats['total']}"
              f" = {100.0*nstats['cat_ok']/nstats['total']:.1f}%")
        if nstats["pkg_total"]:
            print(f"     封装正确           : {nstats['pkg_ok']}/{nstats['pkg_total']}"
                  f" = {100.0*nstats['pkg_ok']/nstats['pkg_total']:.1f}%")
    if latencies:
        lat_sorted = sorted(latencies)
        p95 = lat_sorted[min(len(lat_sorted) - 1, int(round(0.95 * (len(lat_sorted) - 1))))]
        print(f"  E2 单次延迟           : mean {statistics.mean(latencies):.2f} ms  "
              f"p95 {p95:.2f} ms  max {max(latencies):.2f} ms  (n={len(latencies)})")
    if pstats["rows"]:
        rate = 100.0 * pstats["violations"] / pstats["rows"]
        mark = "OK" if pstats["violations"] == 0 else "BUG"
        print(f"  E4 硬约束违规         : {pstats['violations']}/{pstats['rows']} 条返回结果"
              f" = {rate:.1f}%  [{mark}]")

    if args.ablate:
        print_table("E3 消融对比（每行只关闭一个机制，其余保持完整）", ablation_rows(results),
                    ["variant", "part_top1", "part_topK", "nl_cat", "nl_pkg_top1", "nl_empty",
                     "E4", "mean_ms", "说明"])
        print("  注：part_top1/part_topK = 型号用例 Top-1 / Top-K 命中数；nl_cat = 自然语言"
              "用例品类正确数；nl_pkg_top1 = NL 用例里 Top-1 就是要求封装的条数（重排的真正作用点）；"
              "E4 = 返回结果中带零容忍硬约束失败的条数（应恒为 0）。")

    if args.json:
        dest = Path(args.json)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({
            "csv": str(args.csv or "data/samples/chips_seed.csv"), "rows": len(df), "top": args.top,
            "index_build_ms": round(warmup * 1000, 1),
            "part_cases": pstats, "nl_cases": nstats, "latencies_ms": latencies,
            "part_detail": part_rows, "nl_detail": nl_rows,
            "ablation": {name: {"stats": results[name]["stats"],
                                "top1": [r.get("top1") for r in results[name]["part"]],
                                "nl_top1": [r.get("top1") for r in results[name]["nl"]]}
                         for name in results} if args.ablate else None,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n原始结果写入 {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
