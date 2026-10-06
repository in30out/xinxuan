r"""compare_vectorizer.py —— 验证 numpy 兜底 TF-IDF 与 sklearn 路径的一致性。

打包 exe 时排除 scipy/sklearn 会切到 numpy 路径，必须证明召回结果不变，
否则"打包后评测数字不变"这句话就是空话。

运行：
    $env:PYTHONPATH = "<repo>\\.deps;<repo>\\prototype"
    & <DSH python> scripts\compare_vectorizer.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "prototype"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from data_loader import load_chips  # noqa: E402
from recall import RecallIndex  # noqa: E402

QUERIES = [
    "STM32F103C8T6",
    "GD32F103C8T6",
    "3.3V 低功耗 LDO SOT-23-5",
    "RS485 收发器 SOIC-8",
    "24V 转 5V DC-DC",
    "EEPROM I2C 32Kbit",
    "光耦 隔离 DIP-4",
    "MOSFET N沟道 SOT-23",
    "16位 ADC 四通道",
    "便宜的 5V LDO SOT-23",
]


def topk(index, query, k=5, exclude=""):
    return [(index.df.at[i, "part_no"], round(s, 6))
            for i, s in index.recall(query, exclude=exclude, top_k=k)]


def main() -> int:
    df = load_chips()
    sk = RecallIndex(df, kind="sklearn")
    np_ = RecallIndex(df, kind="numpy")
    print(f"rows={len(df)}  vocab sklearn={len(sk.vectorizer.vocabulary_)}  "
          f"vocab numpy={len(np_.vectorizer.vocabulary_)}")

    same_order = 0
    max_rel_err = 0.0
    exact = 0
    for q in QUERIES:
        a = topk(sk, q, k=5)
        b = topk(np_, q, k=5)
        order_a = [p for p, _ in a]
        order_b = [p for p, _ in b]
        ma = dict(a)
        mb = dict(b)
        err = 0.0
        for p in set(ma) & set(mb):
            base = abs(ma[p]) or 1e-9
            err = max(err, abs(ma[p] - mb[p]) / base)
        max_rel_err = max(max_rel_err, err)
        if order_a == order_b:
            same_order += 1
        if order_a[:1] == order_b[:1]:
            exact += 1
        flag = "OK  " if order_a == order_b else "DIFF"
        print(f"[{flag}] {q}")
        print(f"       sklearn: {order_a}")
        print(f"       numpy  : {order_b}")

    print("-" * 72)
    print(f"Top-5 顺序完全一致: {same_order}/{len(QUERIES)}")
    print(f"Top-1 命中一致    : {exact}/{len(QUERIES)}")
    print(f"相似度最大相对误差: {max_rel_err:.3e}")
    ok = same_order == len(QUERIES) and max_rel_err < 1e-4
    print("VECTORIZER_MATCH_OK" if ok else "VECTORIZER_MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
