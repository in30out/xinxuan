"""data_loader.py —— 芯片样例数据读取与清洗。

读取 data/samples/chips_seed.csv，完成缺失值填充、类型转换、
供电/温度区间规范化，并拼接出供 TF-IDF 使用的文本字段 desc_text。
p2p_with 是人工维护的「同封装同引脚可直接替换」关系字段（分号分隔），
只参与规则判定，不进入 desc_text，避免污染 TF-IDF 词表。
"""
from __future__ import annotations

import os
import re
import sys
from typing import Optional

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 打包成 .exe 后 ROOT 指向 PyInstaller 的临时解包目录，因此显式检查 _MEIPASS。
# 顺序：环境变量 CHIPS_CSV > _MEIPASS/data > 仓库 data（开发态）。
_MEI = getattr(sys, "_MEIPASS", "")
DEFAULT_CSV = os.path.join(
    _MEI or ROOT, "data", "samples", "chips_seed.csv"
) if _MEI else os.path.join(ROOT, "data", "samples", "chips_seed.csv")
if _MEI and not os.path.exists(DEFAULT_CSV):  # pragma: no cover - 打包兜底
    DEFAULT_CSV = os.path.join(ROOT, "data", "samples", "chips_seed.csv")

# 查询尾部口语词：只做「尾部」剥离，且必须先原样匹配失败才启用，
# 否则会破坏真实型号（如含 "COMP" 的料号）。含中文的词不需要 \b。
_TAIL_WORDS = [
    "pin-to-pin", "pin to pin", "p2p",
    "替代", "替换", "兼容", "代用", "的替代", "的替换",
    "alternatives", "alternative", "replace", "replacement", "equivalent",
]
_TAIL_RE = re.compile(
    r"[\s,，;；:：、\-—]*(" + "|".join(re.escape(w) for w in _TAIL_WORDS) + r")[\s]*$",
    re.IGNORECASE,
)

NUM_COLS = [
    "pin_count", "vcc_min", "vcc_max", "temp_min", "temp_max",
    "stock", "price_cny", "lead_time_days",
]
TEXT_COLS = ["part_no", "manufacturer", "category", "package", "description", "p2p_with"]


def load_chips(path: Optional[str] = None) -> pd.DataFrame:
    """读 CSV 并清洗，返回规整后的 DataFrame。"""
    df = pd.read_csv(path or DEFAULT_CSV, encoding="utf-8-sig", dtype=str)
    for col in TEXT_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    for col in NUM_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in ["pin_count", "stock", "lead_time_days"]:
        df[col] = df[col].astype(int)
    if "lifecycle" not in df.columns:
        df["lifecycle"] = "未知"
    df["lifecycle"] = df["lifecycle"].fillna("").astype(str).str.strip().replace("", "未知")
    if "datasheet_url" not in df.columns:
        df["datasheet_url"] = ""
    df = df[df["part_no"] != ""].drop_duplicates(subset=["part_no"]).reset_index(drop=True)
    df["desc_text"] = (
        df["part_no"] + " " + df["category"] + " " + df["manufacturer"]
        + " " + df["package"] + " " + df["description"]
    )
    return df


def _match_once(df: pd.DataFrame, q: str):
    """一次精确→子串匹配。返回 Series 或 None。"""
    exact = df[df["part_no"].str.upper() == q]
    if not exact.empty:
        return exact.iloc[0]
    fuzzy = df[df["part_no"].str.upper().str.contains(q, regex=False)]
    if not fuzzy.empty:
        return fuzzy.iloc[0]
    return None


def strip_tail_words(query: str) -> str:
    """剥离查询尾部的口语词（如「STM32F103C8T6 替代」→「STM32F103C8T6」）。"""
    text = (query or "").strip()
    while True:
        stripped = _TAIL_RE.sub("", text).strip()
        if stripped == text or not stripped:
            return text
        text = stripped


def find_part(df: pd.DataFrame, query: str):
    """型号匹配：原样精确/子串 → 剥离尾部口语词后再试。返回 Series 或 None。"""
    q = (query or "").strip().upper()
    if not q:
        return None
    hit = _match_once(df, q)
    if hit is not None:
        return hit
    stripped = strip_tail_words(q)
    if stripped != q and stripped:
        return _match_once(df, stripped)
    return None


def stats(df: pd.DataFrame) -> dict:
    """统计页所需数据：总数、厂商分布、库存告警。"""
    low = df[(df["stock"] < 1000) | (df["lifecycle"].isin(["EOL", "NRND"]))]
    return {
        "total": int(len(df)),
        "manufacturers": df["manufacturer"].value_counts().to_dict(),
        "categories": df["category"].value_counts().to_dict(),
        "alerts": low[["part_no", "manufacturer", "lifecycle", "stock", "lead_time_days"]]
        .sort_values("stock").to_dict("records"),
    }


if __name__ == "__main__":
    d = load_chips()
    print(f"rows={len(d)} cols={list(d.columns)}")
    print(d[["part_no", "category", "package", "pin_count", "stock"]].head())
