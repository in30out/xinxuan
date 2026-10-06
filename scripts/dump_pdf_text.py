"""Dump text from the official AIC attachment PDFs using pypdf from .venv/libs."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, ".venv", "libs"))
from pypdf import PdfReader  # noqa: E402

REFS = os.path.join(ROOT, "docs", "refs")

for name in ("rule1", "rule2"):
    pdf = os.path.join(REFS, name + ".pdf")
    if not os.path.exists(pdf):
        print(f"{name}: missing {pdf}")
        continue
    reader = PdfReader(pdf)
    parts = []
    for i, page in enumerate(reader.pages):
        try:
            parts.append(f"\n===== page {i + 1} =====\n" + (page.extract_text() or ""))
        except Exception as exc:  # noqa: BLE001
            parts.append(f"\n===== page {i + 1} ===== EXTRACT FAIL {exc}")
    text = "".join(parts)
    out = os.path.join(REFS, name + ".txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"{name}: {len(reader.pages)} pages, {len(text)} chars -> {out}")
