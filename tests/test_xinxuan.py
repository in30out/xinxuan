r"""test_xinxuan.py —— 把本次评测暴露并修掉的真实缺陷固化成回归测试。

每个测试都对应文档里记录过的一次真实故障或一条校准决定，目的不是覆盖率，
而是**防止修好的洞再被打开**（尤其"零容忍硬约束"和"温度不算零容忍"这两条）。

运行：
    $env:PYTHONPATH = "<repo>\.deps"
    & <DSH runtime python> -m pytest tests -q
"""
from __future__ import annotations

import pytest

from conftest import CSV
from data_loader import find_part, load_chips
from ranking import rank, supply_factor, total_score
from recall import RecallIndex
from recommend import recommend
from risk import TIER_NO, TIER_P2P
from rules import check_rules, detect_category


@pytest.fixture(scope="module")
def df():
    return load_chips(CSV)


@pytest.fixture(scope="module")
def index(df):
    return RecallIndex(df)


def row(df, part_no):
    part = find_part(df, part_no)
    assert part is not None, f"种子数据里应有 {part_no}"
    return part


# --- 缺陷 1：零容忍硬约束必须真的拦得住 -----------------------------------

def test_package_and_pin_mismatch_is_critical(df):
    """CH340G(SOP-8) vs CH340N(SOP-8) 曾因 check 没有 critical 键而进主榜单。"""
    res = check_rules(row(df, "CH340G"), row(df, "CH340N"))
    failed = {c["rule"] for c in res["checks"] if c["status"] == "fail"}
    assert failed, "两料的封装/脚位应有差异"
    assert res["hard_fail"] is True
    assert any(c.get("critical") for c in res["checks"] if c["status"] == "fail")


def test_voltage_zero_overlap_is_critical(df):
    """SP3485EN(3.3V) vs MAX485ESA+(5V) 电压零交集，必须零容忍。"""
    res = check_rules(row(df, "SP3485EN"), row(df, "MAX485ESA+"))
    volt = [c for c in res["checks"] if c["rule"] == "电压兼容"][0]
    assert volt["status"] == "fail"
    assert volt["critical"] is True
    assert res["hard_fail"] is True


def test_critical_violation_never_reaches_main_list(df, index):
    """修复后：命中零容忍的候选只能出现在 rejected，不能出现在 results。"""
    res = recommend(df, index, "CH340G", top_n=5)
    assert res["results"], "CH340G 应有可用替代"
    for r in res["results"]:
        assert r["replacement_tier"] != TIER_NO


# --- 缺陷 2：温度覆盖不足 ≠ 装不上 ----------------------------------------

def test_temperature_fail_is_not_critical(df):
    """TLC555CDR(−40~85℃) vs NE555DR(0~70℃) 覆盖 56%：判 fail 但不是零容忍。"""
    res = check_rules(row(df, "TLC555CDR"), row(df, "NE555DR"))
    temp = [c for c in res["checks"] if c["rule"] == "温度覆盖"][0]
    assert temp["status"] == "fail"
    assert temp["critical"] is False
    assert res["hard_fail"] is False, "温度降档不应触发零容忍"


def test_temperature_downgrade_stays_in_results(df, index):
    """NE555DR 应进主榜单（排第 2），而不是被打入不推荐。"""
    res = recommend(df, index, "TLC555CDR", top_n=5)
    parts = [r["part_no"] for r in res["results"]]
    assert "NE555DR" in parts


# --- 消融开关只改排序、不改过滤 -------------------------------------------

@pytest.mark.parametrize("ablate", [(), ("rules",), ("supply",), ("category",), ("rerank",)])
def test_ablation_never_produces_critical_violation(df, index, ablate):
    """五个消融配置下，主榜单里都不允许出现零容忍硬约束失败。"""
    for query in ("STM32F103C8T6", "CH340G", "SP3485EN"):
        res = recommend(df, index, query, top_n=5, ablate=ablate)
        for r in res["results"]:
            assert r["replacement_tier"] != TIER_NO, f"{ablate} {query} {r['part_no']}"


def test_ablation_default_matches_explicit_empty(df, index):
    """不带 ablate 与传空集必须完全一致（默认行为不能被消融改造破坏）。"""
    a = recommend(df, index, "STM32F103C8T6", top_n=3)
    b = recommend(df, index, "STM32F103C8T6", top_n=3, ablate=())
    assert [r["part_no"] for r in a["results"]] == [r["part_no"] for r in b["results"]]
    assert [r["score"] for r in a["results"]] == [r["score"] for r in b["results"]]


def test_no_rules_ablation_actually_changes_ranking(df, index):
    """规则分是唯一直接影响型号 Top-1 的机制：关掉后至少有一条用例的排序发生变化。

    实测口径（docs/refs/eval-report.md §3）：型号 Top-1 6/7 → 5/7。
    这里用差分断言而不是写死某个料号 —— 只要"关掉规则分"这个开关真的接上了线，
    就一定存在用例排序变化；若一条都不变，说明开关没生效（正是本测试要防的）。
    """
    queries = ["STM32F103C8T6", "W25Q64JVSSIQ", "CH340G", "SP3232EEN",
               "TLC555CDR", "SP3485EN", "AMS1117-3.3"]
    changed = []
    for q in queries:
        full = [r["part_no"] for r in recommend(df, index, q, top_n=5)["results"]]
        no_rules = [r["part_no"] for r in recommend(df, index, q, top_n=5,
                                                    ablate=("rules",))["results"]]
        if full != no_rules:
            changed.append(q)
    assert changed, "关掉六维规则分后应有用例排序变化，否则说明消融开关没接线"


# --- 缺陷 3：元组索引取反导致 NL 排序回归 ---------------------------------

def test_nl_rerank_is_actually_applied(df, index):
    """NL 重排必须真的生效：Top-1 要落在**精确封装**上，且重排分明显高于原始余弦。

    注意（2026-10 更新）：修掉 tokenizer 返回字符串的缺陷后，本用例的 Top-1 从
    SPX3819M5-L-3-3 变成 RT9013-33GB。这不是回归 —— 三个 SOT-23-5 的 3.3V LDO
    （RT9013-33GB / ME6211C33M5G / SPX3819M5-L-3-3）重排分分别是 0.6564 / 0.6419 /
    0.6367，差距来自真实的词面命中，且三者都是正确答案；旧的第一名是"字符级
    unigram 噪声"造成的巧合。所以这里断言**机制**（精确封装 + 分数抬升 + 消融后
    名次改变），不断言具体是哪一颗，避免把巧合写死成契约。
    """
    query = "3.3V 低功耗 LDO SOT-23-5"
    res = recommend(df, index, query, top_n=3)
    top = res["results"][0]
    assert top["part_no"] in {"RT9013-33GB", "ME6211C33M5G", "SPX3819M5-L-3-3"}, \
        f"Top-1 应是 SOT-23-5 的 3.3V LDO，实际 {top['part_no']}"
    assert top["package"] == "SOT-23-5", f"Top-1 必须是精确封装，实际 {top['package']}"
    assert top["similarity"] > 0.5, f"重排后的相似度应明显高于原始余弦，实际 {top['similarity']}"

    # 关掉重排后，排序必须变化（否则说明重排没接线）；且第一名应不再是"精确封装的那颗"
    no_rerank = recommend(df, index, query, top_n=3, ablate=("rerank",))
    assert no_rerank["results"][0]["part_no"] != top["part_no"]
    assert no_rerank["results"][0]["package"] != "SOT-23-5", \
        "关掉封装重排后，原始余弦会把非 SOT-23-5 的候选排到第一"


def test_rs485_top1_is_soic8_pair(df, index):
    """`RS485 收发器 SOIC-8` 的 Top-1 必须是 RS-485 的 SOIC-8 器件。

    注意（2026-10 更新）：修掉 tokenizer 缺陷后 Top-1 从 SP3485EN 变成 MAX485ESA+
    （原始余弦 0.3810 vs 0.3603，改前是靠字符级 unigram 里的 RS-485 字面量把它抬上去的）。
    两者都是 RS-485/SOIC-8，差别只在 MAX485 是 5V、SP3485 是 3.3V，而**查询本身没有
    指定电压**，因此系统没有依据断言谁更优 —— 这里改为断言硬事实：Top-1 必须是
    RS-485 收发器（非 RS-232/CAN/UART），且必须落在精确封装 SOIC-8 上；
    同时断言 3.3V 的 SP3485EN 仍在 Top-3 里，不能被踢出。
    """
    res = recommend(df, index, "RS485 收发器 SOIC-8", top_n=3)
    top1 = res["results"][0]
    assert top1["part_no"] in {"MAX485ESA+", "MAX3485ESA", "SP3485EN"}, \
        f"Top-1 应是 RS-485 收发器，实际 {top1['part_no']}"
    assert top1["package"] == "SOIC-8", f"Top-1 必须是精确封装，实际 {top1['package']}"
    names = [r["part_no"] for r in res["results"]]
    assert "SP3485EN" in names, f"3.3V 的 SP3485EN 不能掉出 Top-3，实际 {names}"
    # RS-232 器件（SP3232EEN/MAX3232ESE+）封装虽同为 SOIC，但协议不符，必须被降权到后面
    assert names.index("SP3232EEN") > 0 if "SP3232EEN" in names else True
    # NL 模式没有"原件"基准，risk._soft_result 刻意保守判 🟡（见 eval-report.md §3 与文档 §3.4.5）。
    # 这里把这条设计决定固定下来：以后谁把它改成"NL 也判 🟢"，必须先解释为什么。
    assert top1["risk_level"] == "🟡中风险"
    assert all(r["risk_level"] != "🔴高风险" for r in res["results"])


# --- 缺陷 4：口语后缀必须能进型号替换模式 ---------------------------------

@pytest.mark.parametrize("query, expected", [
    ("STM32F103C8T6 替代", "STM32F103C8T6"),
    ("STM32F103C8T6替代", "STM32F103C8T6"),
    ("STM32F103C8T6 替换", "STM32F103C8T6"),
    ("stm32f103c8t6 Pin-to-Pin", "STM32F103C8T6"),
    ("CH340G 的替代", "CH340G"),
])
def test_tail_word_stripping_keeps_part_mode(df, index, query, expected):
    res = recommend(df, index, query, top_n=3)
    assert res["mode"] == "part", f"{query} 应走型号替换模式"
    assert res["matched_part"] == expected


def test_tail_word_stripping_does_not_break_real_parts(df):
    """含尾部词的假象不能误伤：带 COMP 的真实料号必须原样命中。"""
    for part_no in ("CH340C", "W25Q64JVSSIQ", "GD32F103C8T6"):
        found = find_part(df, part_no)
        assert found is not None and found["part_no"] == part_no


# --- 供应链与评分公式 -----------------------------------------------------

def test_supply_factor_zero_stock_is_penalised(df):
    """缺货料（LD1117S33TR stock=0 且 EOL）必须显著降权。"""
    q = row(df, "AMS1117-3.3")
    dead = row(df, "LD1117S33TR")
    s, detail = supply_factor(q, dead)
    assert s < 0.5
    assert detail["w_stock"] == 0.0


def test_total_score_soft_uses_similarity_only():
    """soft=True（NL 模式）时 param 直接取相似度，规则分只展示不参与。"""
    assert total_score(0.0, 0.8, 1.0, soft=True) == pytest.approx(0.8, abs=1e-4)
    assert total_score(0.0, 0.8, 1.0, soft=False) == pytest.approx(0.24, abs=1e-4)


# --- 模态与接口契约 -------------------------------------------------------

def test_nl_query_never_returns_empty_for_known_category(df, index):
    for query in ("运放 SOIC-8", "MOSFET N沟道 SOT-23", "EEPROM I2C 32Kbit"):
        res = recommend(df, index, query, top_n=3)
        assert res["mode"] == "text"
        assert res["results"], f"{query} 不应为空"


def test_detect_category_covers_seed_vocabulary():
    assert detect_category("3.3V 低功耗 LDO SOT-23-5") == "线性稳压器LDO"
    assert detect_category("24V 转 5V DC-DC") == "DC-DC变换器"
    assert detect_category("EEPROM I2C 32Kbit") == "存储器"


def test_results_carry_explainability_fields(df, index):
    """可解释率 100% 是文档 §1 的量化目标：每条结果都要有 checks + reasons + summary。"""
    res = recommend(df, index, "STM32F103C8T6", top_n=5)
    for r in res["results"]:
        assert len(r["checks"]) >= 5
        assert r["summary"]
        assert r["risk_level"] in ("🟢低风险", "🟡中风险", "🔴高风险")
