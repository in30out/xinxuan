"""build_exe.py —— 把「芯选」打包成可迁移的 Windows 交付物。

用法（本机沙箱下必须用 DSH runtime 解释器，见 README 第 1 步）：
    $py build_exe.py --portable          # 推荐：onedir + 便携 ZIP（解压即用的一个文件）
    $py build_exe.py --onedir            # 只出目录形态 dist/芯选/芯选.exe
    $py build_exe.py --onefile           # 只出单文件 exe（在受限沙箱里跑不起来，见下）
    $py build_exe.py --with-sklearn      # 保留 scikit-learn 原版 TF-IDF，体积更大
    $py build_exe.py --console           # 保留控制台窗口（排错用）
    $py build_exe.py --clean             # 打包前清掉 build/ dist/

产物：
    dist/芯选/芯选.exe              目录形态（onedir，默认）
    dist/芯选-便携版.zip             portable：目录形态 + 双击运行.cmd + 使用说明.txt

为什么默认 onedir 而不是 onefile（本机实测，附最小复现）
--------------------------------------------------------
本 harness 的沙箱**禁止**一个进程往"不是它自己创建的目录"里写文件，而 PyInstaller
onefile 的 bootstrapper 恰好必须先把自己解包到 `%TEMP%\\_MEIxxxxxx` 再启动，
于是必定失败：

    [PYI-62052:ERROR] Failed to extract VCRUNTIME140.dll: failed to open target file!
    fopen: Permission denied

用 9 行的最小脚本复现同样报错，与本项目代码无关；实测所有 `_MEI*` 目录都是 0 文件，
手工往同一目录写文件被拒，而用 python 自己在同一 `%TEMP%` 下 `makedirs()` 后写文件成功。
`--windowed` 下失败更隐蔽：双击之后**什么都没有发生**（所以 xinxuan.py 现在会写
`xinxuan-crash.log` 并弹原生消息框）。
在普通机器上 onefile 是可用的，但 Lead 无法在本机证明这一点，因此交付形态定为
**便携 ZIP** —— 对用户来说同样是"一个文件"，解压即用。

为什么默认裁剪 scipy / scikit-learn
-----------------------------------
prototype/recall.py 用 sklearn 的 TfidfVectorizer。scipy + sklearn 打进 exe 会多出
约 150 MB，而调用面只有两个 API。`--exclude-module` 排除后，recall.py 里内置的
**纯 numpy 兜底 TF-IDF**（相同公式：sublinear TF × idf，word 1-2gram，L2 归一化）
自动接管，两条路径由 `scripts/compare_vectorizer.py` 证明等价：
Top-5 顺序一致 10/10、相似度最大相对误差 2.429e-06、词表同为 1400 项。
需要严格用 sklearn 原版时加 `--with-sklearn`。

exe 会带上：
  web/            可视化页面（模板 + 静态资源）
  data/samples/chips_seed.csv   89 条演示数据（离线可用）
  jieba 词典      中文分词
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(HERE, "xinxuan.py")
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")
SPEC = os.path.join(HERE, "芯选.spec")
NAME = "芯选"

# 打进包里的数据（源目录, 包内目录）
DATAS = [
    (os.path.join(HERE, "web"), "web"),
    (os.path.join(HERE, "data", "samples", "chips_seed.csv"), "data/samples"),
]
# 运行时可选：存在就打进去（体积换功能）
OPTIONAL_DATAS = [
    (os.path.join(HERE, "data", "chips_real_semi.csv"), "data"),
]

# 裁剪清单：这些包对 exe 无用或代价过高
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "doctest", "lib2to3",
    "IPython", "jupyter", "notebook", "pytest", "_pytest",
    "matplotlib", "PIL", "pandas.tests", "numpy.tests", "scipy.tests",
    "sklearn.tests", "sqlite3.test", "pytz", "setuptools", "pip", "wheel",
    "urllib3", "requests", "bs4", "lxml", "openpyxl", "docx", "pptx",
    "flask_cors.test", "torch", "tensorflow",
]
SKLEARN_EXCLUDES = ["scipy", "sklearn", "joblib", "threadpoolctl"]

# 便携包里的两个说明文件（纯 ASCII 是刻意的：cmd.exe 用本地代码页读批处理，
# 文件里出现 UTF-8 中文会变成乱码，所以屏幕提示一律英文，中文说明放 .txt）。
PORTABLE_README = """芯选 —— 芯片替代选型智能推荐系统（便携版）

怎么用
------
1. 把整个文件夹解压到任意目录（路径尽量不要有空格）。
2. 双击「双击运行.cmd」（会保留一个控制台黑框，方便看报错），
   或双击「静默启动（无黑框）.vbs」（隐藏控制台，界面照常打开）。
3. 程序会在本机起一个服务并打开界面；关闭浏览器页面后再关掉黑框窗口即退出。

> 为什么不用 "无控制台 exe" 形态：PyInstaller 的 --windowed 打包在受限环境里会
> 静默失败（双击毫无反应）。这里改成"有控制台内核 + VBS 隐藏窗口"，两种环境都能用。

需要什么
--------
- Windows 10/11 64 位。不需要装 Python，不需要联网。
- 想看原生窗口（而不是浏览器标签页）需要系统带有 WebView2 运行库
  （Win11 与较新的 Win10 默认自带）；没有也能用，程序会自动改用浏览器打开。

首次启动慢是正常的
------------------
程序要先构建中文分词词典缓存，第一次大约 1-20 秒，之后几秒内即可。

数据声明
--------
内置的 89 条芯片数据是人工整理的**演示数据**，用于跑通链路与构造兼容/不兼容样例。
其中交期（lead_time_days）与生命周期（lifecycle）是人工整理的演示字段，公开数据集
并不提供这两列，请勿当作实时供应链数据引用。

出问题了怎么办
--------------
- 什么都没发生 / 窗口一闪而过：先双击「双击运行.cmd」看控制台输出，再看
  芯选\\xinxuan-crash.log 与 芯选\\_internal\\xinxuan.log（或 %LOCALAPPDATA%\\xinxuan\\xinxuan.log）。
- 想只看服务是否能起来：命令行执行  芯选\\芯选.exe --no-window --verbose
  然后浏览器访问日志里打印的地址（默认 http://127.0.0.1:5000）。
- 想强制用浏览器打开：  芯选\\芯选.exe --browser
- 端口被占用会自动顺延（5000-5020），也可以用 --port 指定。

更完整的说明见仓库 README.md 第 6 节。
"""

PORTABLE_CMD = """@echo off
REM XinXuan portable launcher (visible console, useful for troubleshooting).
REM Keep this file ASCII-only: cmd.exe reads .cmd files using the local ANSI code page,
REM so UTF-8 Chinese in here would turn into mojibake. Chinese notes live in the .txt.
REM The exe name is Chinese, so look it up with a wildcard instead of hard-coding a
REM path that this file could not represent in ANSI.
setlocal
cd /d "%~dp0"
set "APP="
for /f "delims=" %%F in ('dir /b /s *.exe 2^>nul') do if not defined APP set "APP=%%F"
if not defined APP (
  echo [X] XinXuan exe not found. Keep the folder structure intact.
  pause
  exit /b 1
)
echo Starting XinXuan ... (a browser window should open)
start "" "%APP%"
exit /b 0
"""

# 静默启动器从 packaging/ 目录复制（那份以 GBK 存盘，VBScript 宿主按 ANSI 解析）。
PORTABLE_VBS = "静默启动（无黑框）.vbs"


def build_command(args) -> list:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm",
           "--name", NAME, "--distpath", DIST, "--workpath", BUILD,
           "--specpath", HERE,
           "--paths", os.path.join(HERE, "prototype"),
           "--paths", HERE,
           "--onefile" if args.onefile else "--onedir",
           # 默认保留控制台：实测 --windowed 在受限环境里会**静默失败**（双击无反应、
           # 不写日志、无进程），而 --console 稳定可用。给用户的"无黑框体验"由
           # packaging/silent_launch.vbs（WScript.Shell.Run 隐藏窗口）负责。
           "--windowed" if args.windowed else "--console"]
    for src, dest in DATAS + OPTIONAL_DATAS:
        if os.path.exists(src):
            cmd += ["--add-data", f"{src}{os.pathsep}{dest}"]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    if not args.with_sklearn:
        for mod in SKLEARN_EXCLUDES:
            cmd += ["--exclude-module", mod]
    # jieba 的词典是包内数据文件，必须显式收集
    cmd += ["--collect-data", "jieba"]
    if args.upx_dir:
        cmd += ["--upx-dir", args.upx_dir]
    cmd += [ENTRY]
    return cmd


def human(nbytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} GB"


def _dir_size(path: str):
    total = files = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(root, name))
                files += 1
            except OSError:
                continue
    return files, total


def make_portable(srcdir: str, outroot: str) -> str:
    """把 onedir 产物 + 启动脚本 + 使用说明打成一个便携 ZIP。

    为什么用 zip 而不是"自解压 exe"：本沙箱里**任何**自解压/onefile 形态都要
    先写临时解包目录，而这恰好是被拒绝的操作（见模块 docstring）。ZIP 是最不依赖
    环境、也最容易被 Windows 资源管理器直接打开的形式。
    """
    stage = os.path.join(outroot, "芯选-便携版")
    if os.path.exists(stage):
        shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, exist_ok=True)
    shutil.copytree(srcdir, os.path.join(stage, NAME))
    # 说明文件用 UTF-8 with BOM 写：Windows 记事本/写字板对无 BOM 的 UTF-8 可能按
    # 本地代码页解析而乱码，加 BOM 最稳。
    with open(os.path.join(stage, "使用说明.txt"), "w", encoding="utf-8-sig") as fh:
        fh.write(PORTABLE_README)
    with open(os.path.join(stage, "双击运行.cmd"), "w", encoding="ascii",
              newline="\r\n") as fh:
        fh.write(PORTABLE_CMD)
    vbs_src = os.path.join(HERE, "packaging", "silent_launch.vbs")
    if os.path.exists(vbs_src):
        shutil.copy2(vbs_src, os.path.join(stage, PORTABLE_VBS))
    else:
        print(f"[!] 未找到 {vbs_src}，便携包里不会有静默启动器")

    zpath = os.path.join(outroot, f"{NAME}-便携版.zip")
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _dirs, names in os.walk(stage):
            for name in names:
                full = os.path.join(root, name)
                arc = os.path.relpath(full, outroot)
                zf.write(full, arc)
    files, total = _dir_size(stage)
    print(f"[OK] 便携目录 {stage}  ({files} 个文件 / {human(total)})")
    print(f"[OK] 便携 ZIP  {zpath}  ({human(os.path.getsize(zpath))})")
    return zpath


def main(argv=None):
    ap = argparse.ArgumentParser(description="打包芯选为可迁移交付物")
    ap.add_argument("--onedir", action="store_true", help="目录模式（当前默认，见文件头说明）")
    ap.add_argument("--onefile", action="store_true",
                    help="单文件模式（在受限沙箱里必然失败；普通机器可用）")
    # 默认就出便携 ZIP：交付形态是"一个可迁移文件"，只出目录会让人以为打包没成功。
    # 用 --no-portable 可以跳过这一步（CI 里只想要 exe 目录时有用）。
    ap.add_argument("--portable", dest="portable", action="store_true", default=True,
                    help="onedir + 打包成 dist/芯选-便携版.zip（默认开启）")
    ap.add_argument("--no-portable", dest="portable", action="store_false",
                    help="只出 dist/芯选/ 目录，不生成便携 ZIP")
    ap.add_argument("--console", action="store_true",
                    help="保留控制台窗口（默认已保留，此开关为向后兼容保留）")
    ap.add_argument("--windowed", action="store_true",
                    help="构建 --windowed 形态（正常桌面上的标准形态；受限环境会静默失败）")
    ap.add_argument("--with-sklearn", action="store_true", help="保留 scipy/sklearn（体积更大）")
    ap.add_argument("--clean", action="store_true", help="打包前清理 build/ dist/ spec")
    ap.add_argument("--upx-dir", default=None, help="UPX 目录（可选，压缩体积）")
    args = ap.parse_args(argv)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 PyInstaller。请先运行：\n"
              f"  {sys.executable} scripts\\fetch_deps.py --exe", file=sys.stderr)
        return 2

    if args.clean:
        for path in (BUILD, DIST, SPEC):
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.isfile(path):
                os.remove(path)
        print("[clean] 已清理 build/ dist/ spec")

    cmd = build_command(args)
    print("[cmd]", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=HERE)
    if proc.returncode != 0:
        print(f"打包失败，退出码 {proc.returncode}", file=sys.stderr)
        return proc.returncode

    target = os.path.join(DIST, f"{NAME}.exe") if args.onefile \
        else os.path.join(DIST, NAME, f"{NAME}.exe")
    if not os.path.exists(target):
        print(f"打包结束但未找到产物：{target}", file=sys.stderr)
        return 1
    size = os.path.getsize(target)
    print(f"\n[OK] 耗时 {time.time() - t0:.1f} 秒")
    print(f"[OK] 产物 {target}  ({human(size)})")

    if args.onefile:
        print("[注意] 单文件 exe 需要先解包到 %TEMP%，在限制写临时目录的环境里会失败："
              "双击后没有任何反应。用 --portable 出便携 ZIP 更稳。")
    if args.portable:
        make_portable(os.path.join(DIST, NAME), DIST)
    print(f"[验证] 命令行： \"{target}\" --no-window  (只看服务是否能起来)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
