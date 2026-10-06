"""fetch_deps.py —— 无 pip 写权限环境下的依赖安装器。

本机沙箱禁止 pip 在临时目录写文件（OSError: Permission denied），因此这里
直接访问 PyPI JSON API 下载 wheel / sdist，再解包到目标目录（默认 .deps）。
纯 Python 的 sdist（如 jieba 只有源码包）会把其中的包目录复制过去。

用法:  python scripts/fetch_deps.py [--target .deps]
运行时代码只需把 .deps 加入 PYTHONPATH 或 sys.path。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tarfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_TAG = f"cp{sys.version_info.major}{sys.version_info.minor}"
PLATFORM = "win_amd64" if os.name == "nt" else "manylinux_2_17_x86_64"

PACKAGES = [
    "scipy", "scikit-learn", "joblib", "threadpoolctl", "cloudpickle", "narwhals",
    "Flask", "Werkzeug", "Jinja2", "MarkupSafe", "itsdangerous",
    "click", "blinker", "colorama", "flask-cors", "jieba",
]
# 只有「要打包成 .exe」或「要开原生窗口」时才需要的包（体积大，按需装）：
#   pywebview  -> 原生窗口（Windows 下经 pythonnet 调 WebView2）
#   pythonnet / clr_loader -> pywebview 在 Windows 上的 .NET 桥
#   PyInstaller / altgraph / pyinstaller-hooks-contrib -> 打包器
#   bottle / proxy_tools   -> pywebview 的 http 与线程代理依赖
EXE_PACKAGES = [
    "pywebview", "pythonnet", "clr_loader", "bottle", "proxy_tools",
    "PyInstaller", "pyinstaller-hooks-contrib", "altgraph",
    "packaging", "setuptools", "typing_extensions",
]


def pick_artifact(urls: list):
    """优先选与当前解释器匹配的 wheel，否则退回 sdist。"""
    wheels, sdists = [], []
    for u in urls:
        fn = u["filename"]
        if fn.endswith(".whl"):
            if "none-any.whl" in fn or f"-{PY_TAG}-{PY_TAG}-{PLATFORM}.whl" in fn:
                wheels.append(u)
        elif fn.endswith(".tar.gz"):
            sdists.append(u)
    return (wheels or sdists or [None])[0]


def install_package(name: str, target: str) -> str:
    meta = json.load(urllib.request.urlopen(
        f"https://pypi.org/pypi/{name}/json", timeout=60))
    art = pick_artifact(meta["urls"])
    if art is None:
        return f"{name}: 无匹配构件，跳过"
    data = urllib.request.urlopen(art["url"], timeout=300).read()
    if art["filename"].endswith(".whl"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(target)
        kind = "wheel"
    else:
        # 注意：沙箱下 TemporaryDirectory 清理会报 PermissionError，这里用固定暂存目录
        tmp = os.path.join(os.path.dirname(target), ".deps-build", name)
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            tf.extractall(tmp, filter="data")
        for root, dirs, _ in os.walk(tmp):
            for d in list(dirs):
                src = os.path.join(root, d)
                if os.path.exists(os.path.join(src, "__init__.py")):
                    shutil.copytree(src, os.path.join(target, d), dirs_exist_ok=True)
                    dirs.remove(d)
        kind = "sdist"
    return f"{name}=={meta['info']['version']} ({kind})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=os.path.join(ROOT, ".deps"))
    ap.add_argument("--only", default="", help="只安装指定包，逗号分隔")
    ap.add_argument("--exe", action="store_true",
                    help="额外安装打包/原生窗口所需依赖（pywebview + PyInstaller 等）")
    args = ap.parse_args()
    os.makedirs(args.target, exist_ok=True)
    wanted = [p.strip() for p in args.only.split(",") if p.strip()] or PACKAGES
    if args.exe:
        wanted = wanted + [p for p in EXE_PACKAGES if p not in wanted]
    for pkg in wanted:
        try:
            print(install_package(pkg, args.target), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{pkg}: FAILED {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
