r"""conftest.py —— 让 pytest 能找到 prototype/ 与 .deps/。

运行（本机沙箱下默认 python 是 PyCharm 的 3.14，必须用 DSH runtime）：
    $env:PYTHONPATH = "<repo>\.deps"
    & <DSH runtime python> -m pytest tests -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (os.path.join(ROOT, "prototype"), os.path.join(ROOT, ".deps")):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

CSV = os.path.join(ROOT, "data", "samples", "chips_seed.csv")
