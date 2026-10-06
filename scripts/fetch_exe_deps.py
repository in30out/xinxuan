#!/usr/bin/env python
"""One-command installer for every `.deps` package needed to freeze 芯选 into an .exe.

Run it with the bundled runtime interpreter (the only one that can install here):

    C:\\Users\\13718\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe \\
        scripts\\fetch_exe_deps.py

Why this script exists next to `scripts/fetch_deps.py`
------------------------------------------------------
`scripts/fetch_deps.py` covers the runtime deps, but its `pick_artifact()` only accepts
`*-none-any.whl` or `*-cp312-cp312-win_amd64.whl`.  PyInstaller publishes a *platform*
wheel without a python/abi tag - `pyinstaller-6.22.3-py3-none-win_amd64.whl` - so
`fetch_deps.py` silently falls back to the sdist.  This script accepts that tag and also
installs `pyinstaller-hooks-contrib`, which PyInstaller 6.x requires but nothing else
pulls in.

It then applies the three post-install fixups that make `pywebview` work on a
pythonnet/.NET-Core host and records them in `docs/refs/packaging-audit.md`:

  fixup 1  swap pywebview's bundled .NET-Framework-4.6.2 WebView2 interop assemblies for
           the last `lib/netcoreapp3.0` build published on NuGet (1.0.2478.35)
  fixup 2  patch `webview/platforms/winforms.py` so it imports on .NET 8
           (`System.Windows.Forms.FileDialogNative` was removed by WinForms)
  fixup 3  write the `*.runtimeconfig.json` the pythonnet coreclr host needs

Every step is idempotent; re-running is always safe.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / ".deps"
BUILD = ROOT / ".deps-build"
PKG_INDEX = "https://pypi.org/pypi/{name}/json"
NUGET_FLAT = "https://api.nuget.org/v3-flatcontainer/{id}/{ver}/{id}.{ver}.nupkg"

# ---------------------------------------------------------------- package specs
# Handled by scripts/fetch_deps.py, which already installs these correctly.
FETCH_DEPS_PACKAGES = [
    "pywebview", "bottle", "proxy_tools", "pythonnet", "clr_loader",
    "typing_extensions", "cffi", "pycparser",
    "altgraph", "pefile", "pywin32-ctypes", "setuptools",
]

# PyInstaller + its hook collection: platform wheels that fetch_deps.py cannot pick.
WHEEL_PACKAGES = {
    "pyinstaller": "6.22.3",
    "pyinstaller-hooks-contrib": "2026.8",
}

# Wheel tag preference: pure-python, then this interpreter's ABI, then any win_amd64.
WHEEL_TAG_PREFERENCE = (
    "py3-none-any.whl",
    "py2.py3-none-any.whl",
    "cp312-cp312-win_amd64.whl",
    "py3-none-win_amd64.whl",
)

# ------------------------------------------------- fixup 1: WebView2 interop DLLs
# pywebview 6.2.1 ships Microsoft.Web.WebView2.Core/WinForms with
# TFM=.NETFramework,Version=v4.6.2 (AssemblyVersion 1.0.3856.49).  Loading those on
# .NET 8 dies with
#   System.TypeLoadException: Could not load type 'System.Windows.Forms.ContextMenu'
#       from assembly 'System.Windows.Forms, Version=8.0.0.0'
# NuGet last published `lib/netcoreapp3.0` builds in 1.0.2478.35; 1.0.2792.45 and later
# only ship `lib/net462`.  Verified by reading each nupkg's zip central directory.
WEBVIEW2_NUPKG_VERSION = "1.0.2478.35"
WEBVIEW2_NUPKG_ID = "microsoft.web.webview2"
WEBVIEW2_ENTRIES = {
    "lib/netcoreapp3.0/Microsoft.Web.WebView2.Core.dll":
        "webview/lib/Microsoft.Web.WebView2.Core.dll",
    "lib/netcoreapp3.0/Microsoft.Web.WebView2.WinForms.dll":
        "webview/lib/Microsoft.Web.WebView2.WinForms.dll",
    "runtimes/win-x64/native/WebView2Loader.dll":
        "webview/lib/runtimes/win-x64/native/WebView2Loader.dll",
}
WEBVIEW2_EXPECTED_SIZES = {
    "webview/lib/Microsoft.Web.WebView2.Core.dll": 567896,
    "webview/lib/Microsoft.Web.WebView2.WinForms.dll": 38360,
    "webview/lib/runtimes/win-x64/native/WebView2Loader.dll": 165336,
}
WEBVIEW2_BACKUP = DEPS / ".webview2-netfx-backup"

# ----------------------------------------------------- fixup 2: winforms.py patch
CLR_PATCH_MARKER = "XINXUAN-CLR-PATCH"
WINFORMS_OLD_HEAD = """    iFileDialogType = windowsFormsAssembly.GetType(
        'System.Windows.Forms.FileDialogNative+IFileDialog'
    )
    OpenFileDialogType = windowsFormsAssembly.GetType('System.Windows.Forms.OpenFileDialog')
    FileDialogType = windowsFormsAssembly.GetType('System.Windows.Forms.FileDialog')
    createVistaDialogMethodInfo = OpenFileDialogType.GetMethod('CreateVistaDialog', flags)
    onBeforeVistaDialogMethodInfo = OpenFileDialogType.GetMethod('OnBeforeVistaDialog', flags)
    getOptionsMethodInfo = FileDialogType.GetMethod('GetOptions', flags)
    setOptionsMethodInfo = iFileDialogType.GetMethod('SetOptions', flags)
    fosPickFoldersBitFlag = (
        windowsFormsAssembly.GetType('System.Windows.Forms.FileDialogNative+FOS')
        .GetField('FOS_PICKFOLDERS')
        .GetValue(None)
    )

    vistaDialogEventsConstructorInfo = windowsFormsAssembly.GetType(
        'System.Windows.Forms.FileDialog+VistaDialogEvents'
    ).GetConstructor(flags, None, [FileDialogType], [])
    adviseMethodInfo = iFileDialogType.GetMethod('Advise')
    unadviseMethodInfo = iFileDialogType.GetMethod('Unadvise')
    showMethodInfo = iFileDialogType.GetMethod('Show')
"""

WINFORMS_NEW_HEAD = '''    # --- {marker}: keep the legacy private-COM path only where it still exists ---
    iFileDialogType = windowsFormsAssembly.GetType(
        'System.Windows.Forms.FileDialogNative+IFileDialog'
    )
    OpenFileDialogType = windowsFormsAssembly.GetType('System.Windows.Forms.OpenFileDialog')
    FileDialogType = windowsFormsAssembly.GetType('System.Windows.Forms.FileDialog')
    createVistaDialogMethodInfo = None
    onBeforeVistaDialogMethodInfo = None
    getOptionsMethodInfo = None
    setOptionsMethodInfo = None
    fosPickFoldersBitFlag = None
    vistaDialogEventsConstructorInfo = None
    adviseMethodInfo = None
    unadviseMethodInfo = None
    showMethodInfo = None
    _folder_dialog_error = None
    if iFileDialogType is None:
        # .NET 8 dropped System.Windows.Forms.FileDialogNative (CsWin32 interop now).
        _folder_dialog_error = AttributeError(
            'System.Windows.Forms.FileDialogNative is unavailable on this .NET runtime'
        )
    else:
        try:
            createVistaDialogMethodInfo = OpenFileDialogType.GetMethod(
                'CreateVistaDialog', flags
            )
            onBeforeVistaDialogMethodInfo = OpenFileDialogType.GetMethod(
                'OnBeforeVistaDialog', flags
            )
            getOptionsMethodInfo = FileDialogType.GetMethod('GetOptions', flags)
            setOptionsMethodInfo = iFileDialogType.GetMethod('SetOptions', flags)
            fosPickFoldersBitFlag = (
                windowsFormsAssembly.GetType('System.Windows.Forms.FileDialogNative+FOS')
                .GetField('FOS_PICKFOLDERS')
                .GetValue(None)
            )
            vistaDialogEventsConstructorInfo = windowsFormsAssembly.GetType(
                'System.Windows.Forms.FileDialog+VistaDialogEvents'
            ).GetConstructor(flags, None, [FileDialogType], [])
            adviseMethodInfo = iFileDialogType.GetMethod('Advise')
            unadviseMethodInfo = iFileDialogType.GetMethod('Unadvise')
            showMethodInfo = iFileDialogType.GetMethod('Show')
        except Exception as _exc:
            _folder_dialog_error = _exc
    # --- end {marker} ---

    @classmethod
    def _show_via_folder_browser(cls, initialDirectory, allow_multiple, title):
        dialog = WinForms.FolderBrowserDialog()
        if initialDirectory:
            dialog.SelectedPath = str(initialDirectory)
        if title:
            dialog.Description = str(title)
        if dialog.ShowDialog() == WinForms.DialogResult.OK:
            return (dialog.SelectedPath,)
        return None
'''

WINFORMS_OLD_SHOW = """    @classmethod
    def show(cls, parent=None, initialDirectory=None, allow_multiple=False, title=None):
        openFileDialog = WinForms.OpenFileDialog()
"""

WINFORMS_NEW_SHOW = """    @classmethod
    def show(cls, parent=None, initialDirectory=None, allow_multiple=False, title=None):
        if cls._folder_dialog_error is not None:
            return cls._show_via_folder_browser(initialDirectory, allow_multiple, title)
        openFileDialog = WinForms.OpenFileDialog()
"""

# -------------------------------------------- fixup 3: pythonnet coreclr host config
RUNTIMECONFIG_NAME = "xinxuan-pythonnet.runtimeconfig.json"
RUNTIMECONFIG_JSON = """{
  "runtimeOptions": {
    "tfm": "net8.0",
    "rollForward": "LatestMajor",
    "framework": {
      "name": "Microsoft.WindowsDesktop.App",
      "version": "8.0.0"
    },
    "configProperties": {
      "System.Runtime.Serialization.EnableUnsafeBinaryFormatterSerialization": true
    }
  }
}
"""


# ------------------------------------ fixup 4: the pythonnet coreclr bootstrap module
# `pythonnet.load()` calls `Python.Runtime.Loader.Initialize` with an EMPTY buffer, which
# makes the CLR fall back to `WindowsLoader.GetAllModules()` ->
# `Process.GetCurrentProcess().Handle` -> `OpenProcess(PROCESS_ALL_ACCESS)`, which the DSH
# sandbox denies (`Win32Exception 5: 拒绝访问` inside `Runtime.Delegates..cctor`).  Passing
# the libpython path instead gives `WindowsLoader.Load()` a real module handle, so it uses
# `GetProcAddress` and never touches the process handle.  This module is written into
# `.deps` so `desktop.py` can just `import xinxuan_clr_bootstrap`.
BOOTSTRAP_NAME = "xinxuan_clr_bootstrap.py"
BOOTSTRAP_PY = '''"""Python.NET (coreclr) bootstrap for the DSH `.deps` (PYTHONPATH) layout.

    import sys; sys.path.insert(0, <deps>)
    import xinxuan_clr_bootstrap as clr_boot
    clr_boot.install()          # BEFORE `import webview` / `import clr`
    import webview

Generated by `scripts/fetch_exe_deps.py`; see `docs/refs/packaging-audit.md`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DEPS = Path(__file__).resolve().parent
RUNTIMECONFIG = DEPS / "xinxuan-pythonnet.runtimeconfig.json"

RUNTIMECONFIG_JSON = """{
  "runtimeOptions": {
    "tfm": "net8.0",
    "rollForward": "LatestMajor",
    "framework": {
      "name": "Microsoft.WindowsDesktop.App",
      "version": "8.0.0"
    },
    "configProperties": {
      "System.Runtime.Serialization.EnableUnsafeBinaryFormatterSerialization": true
    }
  }
}
"""

# pywebview's winforms backend assumes .NET Framework, where these are reachable without
# an explicit reference.  On .NET Core they are separate assemblies.
PRELOAD_ASSEMBLIES = (
    "System.Windows.Forms",
    "Microsoft.Win32.SystemEvents",
    "System.Drawing.Common",
)


def native_dll_dirs(deps: Path | None = None) -> list[str]:
    """Directories holding native DLLs .NET P/Invoke must find (WebView2Loader)."""
    lib = (deps or DEPS) / "webview" / "lib"
    out = [str(lib)] if lib.is_dir() else []
    for cand in (lib / "runtimes" / "win-x64" / "native",
                 lib / "runtimes" / "win-x86" / "native"):
        if cand.is_dir():
            out.append(str(cand))
    return out


def libpython_path() -> str:
    """Absolute path of the CPython DLL belonging to the running interpreter."""
    name = "python%d%d.dll" % sys.version_info[:2]
    for base in (sys.base_prefix, sys.prefix, os.path.dirname(sys.executable)):
        for cand in (Path(base) / name, Path(base) / "DLLs" / name):
            if cand.is_file():
                return str(cand)
    raise FileNotFoundError("could not locate %s near %r" % (name, sys.base_prefix))


def ensure_sta_com() -> int:
    """CoInitializeEx(NULL, COINIT_APARTMENTTHREADED) on the calling thread.

    python.exe's main thread starts with no COM apartment, and WebView2 refuses to
    build a controller from a non-COM thread:
        COMException (0x800401F0): 尚未调用 CoInitialize。
          at Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateAsync(...)
    Returns the raw HRESULT (0 = S_OK, 1 = S_FALSE already initialised).
    """
    import ctypes

    return ctypes.windll.ole32.CoInitializeEx(None, 0x2) & 0xFFFFFFFF


def ensure_runtime_config(path=None) -> str:
    target = Path(path) if path else RUNTIMECONFIG
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(RUNTIMECONFIG_JSON, encoding="utf-8")
    return str(target)


def install(deps_dir=None, runtime_config=None, runtime="coreclr", preload=True) -> str:
    """Load Python.NET against *runtime*; returns the libpython path used."""
    deps = Path(deps_dir) if deps_dir else DEPS
    if str(deps) not in sys.path:
        sys.path.insert(0, str(deps))

    ensure_sta_com()

    for d in native_dll_dirs(deps):
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

    cfg = None
    if runtime == "coreclr":
        cfg = ensure_runtime_config(runtime_config)
        os.environ["PYTHONNET_RUNTIME"] = "coreclr"
        os.environ["PYTHONNET_CORECLR_RUNTIME_CONFIG"] = cfg

    import clr_loader
    import pythonnet

    if pythonnet._LOADED:
        return libpython_path()

    if pythonnet._RUNTIME is None:
        pythonnet.set_runtime(clr_loader.get_coreclr(runtime_config=cfg))

    dll = deps / "pythonnet" / "runtime" / "Python.Runtime.dll"
    assembly = pythonnet._RUNTIME.get_assembly(str(dll))
    func = assembly.get_function("Python.Runtime.Loader.Initialize")
    py_dll = libpython_path()
    rc = func(py_dll.encode("utf-8"))
    if rc != 0:
        raise RuntimeError("Python.Runtime.Loader.Initialize returned %d" % rc)

    pythonnet._LOADER_ASSEMBLY = assembly
    pythonnet._LOADED = True

    if preload:
        import clr

        for name in PRELOAD_ASSEMBLIES:
            try:
                clr.AddReference(name)
            except Exception as exc:
                print("[clr_bootstrap] AddReference(%r) failed: %r" % (name, exc))

    import atexit

    atexit.register(pythonnet.unload)
    return py_dll
'''


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def fetch_bytes(url: str, attempts: int = 4) -> bytes:
    """Download *url* fully, retrying on truncated/short reads.

    PyPI's CDN occasionally closes the connection mid-body, which surfaces as
    ``http.client.IncompleteRead(22048 bytes read, 440097 more expected)``.
    A single ``resp.read()`` is therefore not enough for a repeatable installer:
    read in chunks, compare with Content-Length, and retry the whole request.
    """
    log(f"    GET {url}")
    last: Exception = RuntimeError("no attempt made")
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=300) as resp:
                expected = resp.headers.get("Content-Length")
                expected = int(expected) if expected else None
                chunks, got = [], 0
                while True:
                    block = resp.read(65536)
                    if not block:
                        break
                    chunks.append(block)
                    got += len(block)
            blob = b"".join(chunks)
            if expected is not None and len(blob) != expected:
                raise IOError(f"short read: got {len(blob)} of {expected} bytes")
            if attempt > 1:
                log(f"    (attempt {attempt} succeeded)")
            return blob
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last = exc
            log(f"    ! attempt {attempt}/{attempts} failed: {exc!r}")
            if attempt < attempts:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"download failed after {attempts} attempts: {last!r}") from last


def pick_wheel(name: str, version: str) -> str:
    data = fetch_json(PKG_INDEX.format(name=name))
    files = [f for f in data["releases"][version] if f["filename"].endswith(".whl")]
    if not files:
        raise RuntimeError(f"{name}=={version}: no wheel published")
    for tag in WHEEL_TAG_PREFERENCE:
        for f in files:
            if f["filename"].endswith(tag):
                return f["url"]
    raise RuntimeError(
        f"{name}=={version}: no usable wheel among "
        + ", ".join(sorted(f["filename"] for f in files))
    )


def wheel_installed(target: Path, name: str, version: str) -> bool:
    """True when ``<name>-<version>.dist-info`` is already unpacked into *target*."""
    want = name.lower().replace("_", "-").replace(".", "-")
    for info in target.glob("*.dist-info"):
        stem = info.name[: -len(".dist-info")]
        dist, _, ver = stem.rpartition("-")
        if ver != version:
            continue
        if dist.lower().replace("_", "-").replace(".", "-") == want:
            return True
    return False


def extract_wheel(url: str, target: Path, label: str = "") -> None:
    target.mkdir(parents=True, exist_ok=True)
    blob = fetch_bytes(url)
    import io

    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{label or url}: downloaded {len(blob)} bytes, not a zip") from exc
    with zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"{label or url}: corrupt entry in wheel: {bad}")
        zf.extractall(target)


def install_wheels(names_and_versions, target: Path, force: bool = False) -> None:
    for name, version in names_and_versions.items():
        if not force and wheel_installed(target, name, version):
            log(f"  [wheel] {name}=={version} already installed - skipping")
            continue
        log(f"  [wheel] {name}=={version}")
        url = pick_wheel(name, version)
        log(f"    -> {url.rsplit('/', 1)[-1]}")
        extract_wheel(url, target, label=f"{name}=={version}")


def run_fetch_deps(packages) -> None:
    script = ROOT / "scripts" / "fetch_deps.py"
    cmd = [sys.executable, str(script), "--target", str(DEPS),
           "--only", ",".join(packages)]
    log("  [fetch_deps] " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    tail = (proc.stdout or "").strip().splitlines()[-15:]
    for line in tail:
        log("    " + line)
    if proc.returncode != 0:
        log((proc.stderr or "").strip()[-2000:])
        raise RuntimeError(f"fetch_deps.py failed with exit {proc.returncode}")


def fixup_webview2() -> str:
    """Replace pywebview's .NET Framework WebView2 interop with the netcoreapp3.0 build."""
    lib = DEPS / "webview" / "lib"
    if not lib.is_dir():
        return "SKIPPED: .deps/webview/lib missing (install pywebview first)"

    already = all(
        (DEPS / rel).is_file() and (DEPS / rel).stat().st_size == size
        for rel, size in WEBVIEW2_EXPECTED_SIZES.items()
    )
    if already:
        return "already netcoreapp3.0"

    url = NUGET_FLAT.format(id=WEBVIEW2_NUPKG_ID, ver=WEBVIEW2_NUPKG_VERSION)
    log(f"  [webview2] {WEBVIEW2_NUPKG_ID} {WEBVIEW2_NUPKG_VERSION}")
    blob = fetch_bytes(url)

    import io

    staged: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
        for entry, rel in WEBVIEW2_ENTRIES.items():
            if entry not in names:
                return f"SKIPPED: {entry} not present in nupkg"
            staged[rel] = zf.read(entry)

    WEBVIEW2_BACKUP.mkdir(parents=True, exist_ok=True)
    for rel in staged:
        dest = DEPS / rel
        if dest.is_file():
            backup = WEBVIEW2_BACKUP / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.is_file():
                shutil.copy2(dest, backup)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(staged[rel])

    wrong = [
        rel for rel, size in WEBVIEW2_EXPECTED_SIZES.items()
        if (DEPS / rel).stat().st_size != size
    ]
    if wrong:
        return "PARTIAL: unexpected sizes for " + ", ".join(wrong)
    return f"installed {WEBVIEW2_NUPKG_VERSION} netcoreapp3.0 interop"


def fixup_winforms_patch() -> str:
    target = DEPS / "webview" / "platforms" / "winforms.py"
    if not target.is_file():
        return "SKIPPED: .deps/webview/platforms/winforms.py missing"
    text = target.read_text(encoding="utf-8")
    if CLR_PATCH_MARKER in text:
        return "already patched"
    if WINFORMS_OLD_HEAD not in text:
        return "SKIPPED: OpenFolderDialog class body not found verbatim"
    if WINFORMS_OLD_SHOW not in text:
        return "SKIPPED: OpenFolderDialog.show not found verbatim"
    text = text.replace(WINFORMS_OLD_HEAD,
                        WINFORMS_NEW_HEAD.format(marker=CLR_PATCH_MARKER), 1)
    text = text.replace(WINFORMS_OLD_SHOW, WINFORMS_NEW_SHOW, 1)
    target.write_text(text, encoding="utf-8")
    return "patched"


def fixup_runtimeconfig() -> str:
    target = DEPS / RUNTIMECONFIG_NAME
    if target.is_file() and target.read_text(encoding="utf-8") == RUNTIMECONFIG_JSON:
        return f"already at {target.relative_to(ROOT)}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(RUNTIMECONFIG_JSON, encoding="utf-8")
    return f"wrote {target.relative_to(ROOT)}"


def fixup_bootstrap() -> str:
    target = DEPS / BOOTSTRAP_NAME
    if target.is_file() and target.read_text(encoding="utf-8") == BOOTSTRAP_PY:
        return f"already at {target.relative_to(ROOT)}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(BOOTSTRAP_PY, encoding="utf-8")
    return f"wrote {target.relative_to(ROOT)}"


def verify() -> int:
    log("\n== verify ==")
    failures = 0
    env = dict(os.environ, PYTHONPATH=str(DEPS))

    proc = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                          capture_output=True, text=True, env=env, cwd=str(ROOT))
    version = (proc.stdout or proc.stderr).strip()
    ok = proc.returncode == 0
    log(f"  python -m PyInstaller --version -> {version!r} (exit {proc.returncode})")
    failures += 0 if ok else 1

    checks = [
        ("PyInstaller", "import PyInstaller; print(PyInstaller.__version__)"),
        ("PyInstaller.utils.hooks", "import PyInstaller.utils.hooks as h; print(h.__file__)"),
        ("pywebview", "import webview; print(webview.__file__)"),
        ("pythonnet", "import pythonnet; print(pythonnet.__file__)"),
        ("clr_loader", "import clr_loader; print(clr_loader.get_coreclr.__name__)"),
        ("hooks-contrib", "import PyInstaller.hooks; print(PyInstaller.hooks.__file__)"),
    ]
    for label, code in checks:
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, env=env, cwd=str(ROOT))
        ok = proc.returncode == 0
        failures += 0 if ok else 1
        log(f"  {label}: {'OK' if ok else 'FAIL'} {(proc.stdout or proc.stderr).strip()[:120]}")

    # The crucial one for pywebview: the netcoreapp3.0 interop must load on the CLR.
    code = (
        "import sys; sys.path.insert(0, r'{d}');"
        "import xinxuan_clr_bootstrap as b;"
        "print(b.install());"
        "import clr;"
        "import webview;"
        "from webview.util import interop_dll_path;"
        "clr.AddReference(interop_dll_path('Microsoft.Web.WebView2.Core.dll'));"
        "from Microsoft.Web.WebView2.Core import CoreWebView2Environment as E;"
        "print('WebView2 interop OK')"
    ).format(d=str(DEPS))
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=env, cwd=str(ROOT))
    log(f"  coreclr + WebView2 interop: {'OK' if proc.returncode == 0 else 'FAIL'}")
    log("    " + (proc.stdout or "").strip().replace("\n", " | ")[:200])
    if proc.returncode != 0:
        failures += 1
        log("    " + (proc.stderr or "").strip()[-600:])
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-fetch-deps", action="store_true",
                    help="do not re-run scripts/fetch_deps.py")
    ap.add_argument("--skip-wheels", action="store_true",
                    help="do not install pyinstaller / pyinstaller-hooks-contrib")
    ap.add_argument("--skip-fixups", action="store_true",
                    help="only install packages")
    ap.add_argument("--verify-only", action="store_true",
                    help="run the verification suite and exit")
    ap.add_argument("--force", action="store_true",
                    help="re-download the wheels even if they are already installed")
    args = ap.parse_args()

    DEPS.mkdir(parents=True, exist_ok=True)
    log(f"target   : {DEPS}")
    log(f"python   : {sys.executable} ({sys.version.split()[0]})")

    if not args.verify_only:
        if not args.skip_fetch_deps:
            log("\n== 1/4 scripts/fetch_deps.py ==")
            run_fetch_deps(FETCH_DEPS_PACKAGES)
        if not args.skip_wheels:
            log("\n== 2/4 platform wheels ==")
            install_wheels(WHEEL_PACKAGES, DEPS, force=args.force)
        if not args.skip_fixups:
            log("\n== 3/4 fixups ==")
            log(f"  webview2     : {fixup_webview2()}")
            log(f"  winforms.py  : {fixup_winforms_patch()}")
            log(f"  runtimeconfig: {fixup_runtimeconfig()}")
            log(f"  bootstrap    : {fixup_bootstrap()}")
        BUILD.mkdir(parents=True, exist_ok=True)

    log("\n== 4/4 verify ==")
    failures = verify()
    log(f"\nRESULT: {'EXE_DEPS_OK' if failures == 0 else f'EXE_DEPS_FAILED ({failures})'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
