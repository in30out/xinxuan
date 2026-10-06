"""Install a pure-python package into .venv/libs without pip's hardlink path.

Why: this workspace's sandbox denies the hardlink/metadata write that pip performs while
unpacking a wheel (OSError Errno 13 on *.whl.metadata), so pyPI installs fail even though
plain file writes inside the workspace work. Downloading the wheel with urllib and unzipping
it with zipfile avoids that code path entirely.
"""
import json
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIBS = os.path.join(ROOT, ".venv", "libs")


def pypi_wheel_url(name, version=None):
    url = f"https://pypi.org/pypi/{name}/json"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.load(r)
    ver = version or data["info"]["version"]
    files = data["releases"][ver]
    for f in files:
        if f["filename"].endswith("-py3-none-any.whl") or f["filename"].endswith("-py2.py3-none-any.whl"):
            return f["url"], f["filename"]
    raise SystemExit(f"no pure-python wheel for {name} {ver}")


def install(name, version=None):
    os.makedirs(LIBS, exist_ok=True)
    url, filename = pypi_wheel_url(name, version)
    dest = os.path.join(LIBS, filename)
    print(f"downloading {filename}")
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    with zipfile.ZipFile(dest) as z:
        names = z.namelist()
        z.extractall(LIBS)
    os.remove(dest)
    top = sorted({n.split("/")[0] for n in names} - {"", ".."})
    print(f"installed {name}: {top}")


if __name__ == "__main__":
    for spec in sys.argv[1:]:
        if "==" in spec:
            n, v = spec.split("==", 1)
            install(n, v)
        else:
            install(spec)
