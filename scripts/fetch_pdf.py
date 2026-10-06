"""Download the official AIC attachment PDFs and dump their text (no external deps)."""
import os
import re
import ssl
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "docs", "refs")
os.makedirs(OUT, exist_ok=True)

BASE = "https://www.aicomp.cn/wp-content/uploads/2026/07/"
FILES = {
    "rule1": "%E9%99%84%E4%BB%B61AIC%C2%B7AI%E9%9B%86%E6%88%90%E7%94%B5%E8%B7%AF%E7%AB%9E%E8%B5%9B%E8%A7%84%E5%88%99%E5%8F%8A%E4%BD%9C%E5%93%81%E6%8F%90%E4%BA%A4%E8%A6%81%E6%B1%82.pdf",
    "rule2": "%E9%99%84%E4%BB%B62AIC%C2%B7AI%E9%9B%86%E6%88%90%E7%94%B5%E8%B7%AF%E6%8A%80%E6%9C%AF%E6%8A%A5%E5%91%8A%E5%8F%82%E8%80%83%E5%A4%A7%E7%BA%B2.pdf",
}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
except ssl.SSLError:
    pass

REQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "*/*",
}


def fetch(url, dest):
    req = urllib.request.Request(url, headers=REQ_HEADERS)
    with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def extract_text(path):
    """Minimal PDF text extraction: inflate streams, pull Tj/TJ string operands."""
    with open(path, "rb") as f:
        raw = f.read()
    chunks = []
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        blob = raw[start:end]
        try:
            blob = zlib.decompress(blob)
        except zlib.error:
            continue
        chunks.append(blob)
    text_parts = []
    for blob in chunks:
        for tm in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\[\]]*)\]\s*TJ", blob):
            seg = tm.group(0)
            for sm in re.finditer(rb"\((?:\\.|[^\\()])*\)", seg):
                s = sm.group(0)[1:-1]
                s = s.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
                text_parts.append(s)
            text_parts.append(b"\n")
    return b"".join(text_parts)


if __name__ == "__main__":
    for name, tail in FILES.items():
        dest = os.path.join(OUT, name + ".pdf")
        try:
            n = fetch(BASE + tail, dest)
            print(f"{name}: downloaded {n} bytes -> {dest}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAIL {type(exc).__name__}: {exc}")
    for name in FILES:
        p = os.path.join(OUT, name + ".pdf")
        if not os.path.exists(p):
            continue
        try:
            txt = extract_text(p)
            enc = "utf-8"
            try:
                s = txt.decode(enc)
            except UnicodeDecodeError:
                s = txt.decode("latin-1")
            outp = os.path.join(OUT, name + ".txt")
            with open(outp, "w", encoding="utf-8") as f:
                f.write(s)
            print(f"{name}: text {len(s)} chars -> {outp}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: extract FAIL {type(exc).__name__}: {exc}")
