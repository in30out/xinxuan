# 打包审计：pywebview / pythonnet / PyInstaller / 芯选.exe（全部实测）

> 作者：`dep-packager`（队友）｜范围：`.deps/`、`scripts/fetch_exe_deps.py`、`docs/refs/packaging-audit.md`、`.tmp/exe-probe/`
> **文中每个数字都来自本机实跑**；凡是"推断/未实测"的地方都在第 9 节单独列出，绝不混进结论。

---

## 0. 结论先行

| 问题 | 结论 | 证据等级 |
|---|---|---|
| `.deps` 里能否装上 pywebview + PyInstaller | **能** | 实测（`RESULT: EXE_DEPS_OK`） |
| pywebview 的 Python 侧能否在 `PYTHONPATH=.deps` 模式跑起来 | **能**（要绕过 pythonnet 的默认初始化，见 3.2） | 实测 |
| pywebview 能否在本沙箱里**真的显示出窗口** | **不能**，且是沙箱边界（Chromium Mojo IPC 被拒），不是代码问题 | 实测（`chrome_debug.log` FATAL） |
| 截图能不能用 | **不能**（窗口都起不来） | 实测 |
| PyInstaller 能否在这一模式打包 | **能**，但**只有 `--onedir` 的产物能运行** | 实测 |
| `--onefile` | 能**构建**，不能**运行**（bootloader 解压 `_MEIPASS` 被拒） | 实测（原始报错见 4.2） |
| 打包后的 exe 是否还需要外部 `.deps` | **不需要** | 实测（搬到工作区外、`PYTHONPATH` 清空仍正常） |
| 裁掉 scipy/sklearn 后 exe 能否起来 | **能**，实跑出正确推荐结果 | 实测（第 5 节） |
| 交付形态建议 | `--onedir`（+ 便携 ZIP）＋ 浏览器模式兜底 | 结论 |

打包后的 `芯选.exe` 冷启动实测：**0.736 s** 起 HTTP 服务、`/api/recommend` **386 ms** 返回，
`STM32F103C8T6 → APM32F103C8T6 / Pin-to-Pin 直接替换 / 🟢低风险 / score 0.7256`
——与 Lead 在 m00274 给的新基线**逐位一致**。

---

## 1. 复现命令

### 1.1 一键装依赖（可反复执行）

```powershell
$ws = "C:\MyFiles\Develop\dsh\work_1"
$py = "C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
& $py "$ws\scripts\fetch_exe_deps.py"          # 加 --verify-only 只做校验；--force 强制重下 wheel
```

实测输出（`docs/refs` 同目录外的原始日志：`.tmp\exe-probe\audit_fetch_exe_deps2.txt`）：

```
target   : C:\MyFiles\Develop\dsh\work_1\.deps
python   : ...\dependencies\python\python.exe (3.12.14)

== 1/4 scripts/fetch_deps.py ==
    pywebview==6.2.1 (wheel) / pythonnet==3.2.0 (wheel) / clr_loader==0.3.1 (wheel) / bottle==0.13.4 (wheel) ...
== 2/4 platform wheels ==
  [wheel] pyinstaller==6.22.3 already installed - skipping
  [wheel] pyinstaller-hooks-contrib==2026.8 already installed - skipping
== 3/4 fixups ==
  webview2     : installed 1.0.2478.35 netcoreapp3.0 interop
  winforms.py  : patched
  runtimeconfig: already at .deps\xinxuan-pythonnet.runtimeconfig.json
  bootstrap    : already at .deps\xinxuan_clr_bootstrap.py
== 4/4 verify ==
  python -m PyInstaller --version -> '6.22.3' (exit 0)
  PyInstaller: OK 6.22.3
  pywebview: OK ...\.deps\webview\__init__.py
  pythonnet: OK ...\.deps\pythonnet\__init__.py
  clr_loader: OK get_coreclr
  hooks-contrib: OK ...\.deps\PyInstaller\hooks\__init__.py
  coreclr + WebView2 interop: OK
    C:\Users\13718\.dsh\...\python312.dll | WebView2 interop OK

RESULT: EXE_DEPS_OK
```

**语义说明（重要）**：每跑一次，第 1 步 `scripts/fetch_deps.py` 会把 pywebview 的 wheel **重新解包覆写**
（WebView2 的 netfx DLL 会被还原、`winforms.py` 的补丁会被冲掉），第 3 步再把三个 fixup 打回去。
所以它是"**重置 + 重打补丁**"式幂等：终态永远一致，但**不能把 fixup 和 fetch 分开跳过**。
如果要连续打包两次，直接再跑一次本脚本即可。

### 1.2 打包（与 `build_exe.py` 同参数，产物落在 `.tmp` 内）

`build_exe.py` 不是我该改的文件，我没有执行它、也没有产生 `dist/`。我用一个只改输出路径的探针
`.tmp\exe-probe\build_xinxuan_probe.py` 复刻了它的全部参数（`EXCLUDES`、`SKLEARN_EXCLUDES`、
`--add-data web;web`、`--add-data data\samples\chips_seed.csv;data/samples`、`--collect-data jieba`、
`--name 芯选`、`--onedir --console`）：

```powershell
$env:PYTHONPATH = "$ws\.deps"
& $py "$ws\.tmp\exe-probe\build_xinxuan_probe.py"
```

---

## 2. 实测环境与版本

```powershell
"PYTHONPATH=" + $env:PYTHONPATH     # <ws>\.deps;<ws>\prototype;<ws>  ← 分号分隔（本机不是冒号）
```

| 组件 | 版本 | 位置 |
|---|---|---|
| 解释器 | CPython **3.12.14** | `C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` |
| pywebview | **6.2.1** | `.deps\webview\` |
| pythonnet | **3.2.0** | `.deps\pythonnet\` |
| clr_loader | **0.3.1** | `.deps\clr_loader\` |
| bottle / proxy_tools | 0.13.4 / 0.1.0 | `.deps\` |
| PyInstaller | **6.22.3**（`py3-none-win_amd64` 平台 wheel） | `.deps\PyInstaller\` |
| pyinstaller-hooks-contrib | **2026.8** | `.deps\_pyinstaller_hooks_contrib\` |
| altgraph / pefile / pywin32-ctypes | 0.17.5 / 2024.8.26 / 0.2.3 | `.deps\` |
| cffi / pycparser / typing_extensions | 2.1.1 / 3.0 / 4.16.0 | `.deps\` |
| setuptools | 84.0.0 | `.deps\` |
| numpy / pandas（**不在 `.deps`，在解释器 site-packages**） | 2.3.5 / 3.0.1 | `...\dependencies\python\Lib\site-packages\` |

`.deps` 现状：**111 个顶层目录 + 12 个顶层文件，7449 个文件，222.33 MB**。

为什么需要 `scripts/fetch_exe_deps.py`（而不是直接用 `scripts/fetch_deps.py`）：

1. `fetch_deps.py` 的 `pick_artifact()` 只认 `*-none-any.whl` 或 `*-cp312-cp312-win_amd64.whl`，
   PyInstaller 发的是**没有 python/abi tag 的平台 wheel** `pyinstaller-6.22.3-py3-none-win_amd64.whl`，
   会被误判为"无 wheel"，回退到 sdist。
2. `pyinstaller-hooks-contrib` 是 PyInstaller 6.x 的硬依赖，但 `fetch_deps.py` 的 `PACKAGES` 里没有。
3. 三个 fixup（见第 3 节）没有它们 pywebview 在这台机器上根本起不来。

---

## 3. pywebview + pythonnet：三层障碍与破解（含原始报错）

### 3.1 障碍 1：netfx 路线（clr_loader 在 Windows 的默认）彻底不可用

默认 `import clr`（`webview/platforms/winforms.py:13` 的 `import clr`）直接失败：

```
RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize from
C:\MyFiles\Develop\dsh\work_1\.deps\pythonnet\runtime\Python.Runtime.dll
```

逐层剥开后（`clr_loader` 源码 `netfx_loader/ClrLoader.cs`、`DomainData.cs`）：

* `pyclr_create_appdomain()` 返回的是 **AppDomain 索引**（默认域 = 0），所以 `ffi.NULL` 合法；
* `DomainData.GetFunctor` 用 `AssemblyName.GetAssemblyName(path)` → `domain.Load(name)` → `GetType(...)`，
  即**按程序集名在 AppDomain.ApplicationBase 里解析，而不是按传入路径加载**；
* 唯一的路径回退是 `AssemblyResolve` 里的 `Assembly.LoadFrom(assemblyPath)`。

而在本机（DSH 沙箱），**`Assembly.LoadFrom` 对非框架路径一律被拒**，即使把 DLL 复制到
`.tmp\` 或 `$env:TEMP` 也一样：

```
Could not load file or assembly 'file:///C:\MyFiles\Develop\dsh\work_1\.deps\pythonnet\runtime\Python.Runtime.dll'
or one of its dependencies. Operation is not supported. (Exception from HRESULT: 0x80131515)
```

（`.NET Framework` 本身在沙箱里是好的：PowerShell 5.1 进程里 `CreateDomain`、`EnumProcessModules`、
`Assembly.LoadFrom` 加载 `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Windows.Forms.dll` 全部成功；
`[Assembly]::Load([IO.File]::ReadAllBytes($p))` 也是成功的——坏的只有"**按路径**加载非框架程序集"。
也没有 `Zone.Identifier` 数据流，不是 MOTW 问题。）

**结论：netfx 路线放弃。** 这是环境边界，改代码改不掉。

### 3.2 破解 1：改用 coreclr，并手工调用 `Loader.Initialize`

`webview/platforms/winforms.py` 里本来就有兜底：`import clr` 失败就把 `PYTHONNET_RUNTIME` 设成 `coreclr` 再试一次。
但**直接用 coreclr 也会炸**：

```
Failed to initialize pythonnet: System.TypeInitializationException:
  The type initializer for 'Delegates' threw an exception. --->
  System.ComponentModel.Win32Exception (5): 拒绝访问。
     at System.Diagnostics.ProcessManager.OpenProcess(Int32 processId, Int32 access, Boolean throwIfExited)
     at Python.Runtime.Platform.WindowsLoader.GetAllModules()
     at Python.Runtime.Runtime.Delegates..cctor()
```

根因（pythonnet 3.2.0 源码，`Runtime.cs`）：

```csharp
// WindowsLoader.GetFunction(IntPtr hModule, string procedureName)
if (hModule == IntPtr.Zero) { foreach (var module in GetAllModules()) {...} }   // ← 需要进程句柄
else { return GetProcAddress(hModule, procedureName); }                          // ← 不需要

// GetAllModules() 第一行
using var self = Process.GetCurrentProcess();   // .NET Core 下要 PROCESS_ALL_ACCESS，沙箱拒绝
```

而 `pythonnet/__init__.py:143` 走的是 `func(b"")`——**空缓冲区**，于是
`Python.Runtime.Loader.Initialize` 把 `PythonDLL` 设为 `null`，`WindowsLoader` 就掉进
`GetAllModules()` 分支，正好踩中 `OpenProcess` 拒绝。

**修复**：不用 `pythonnet.load()` 的默认入口，自己取出函数指针并把 libpython 路径传进去：

```python
pythonnet.set_runtime(clr_loader.get_coreclr(runtime_config=cfg))     # cfg = 显式写好的 runtimeconfig.json
asm = pythonnet._RUNTIME.get_assembly(str(DEPS / "pythonnet" / "runtime" / "Python.Runtime.dll"))
fn  = asm.get_function("Python.Runtime.Loader.Initialize")
rc  = fn(libpython_path().encode("utf-8"))      # 非空 → PythonDLL != null → 走 GetProcAddress
assert rc == 0
pythonnet._LOADER_ASSEMBLY, pythonnet._LOADED = asm, True
```

实测（`.tmp\exe-probe\probe_coreclr2.txt`）：

```
STEP 6 Initialize(libpython_path) rc = 0
STEP 7 import clr OK
STEP 8 WinForms OK: 3.12.14
STEP 11 WebView2 Core OK: <class 'Microsoft.Web.WebView2.Core.CoreWebView2Environment'>
RESULT: PYTHONNET_CORECLR_PATH_OK
```

这段逻辑已经固化进 `.deps\xinxuan_clr_bootstrap.py`（由 `fetch_exe_deps.py` 的 `fixup_bootstrap()` 生成），
入口是 `install(deps_dir=None, runtime_config=None, runtime="coreclr", preload=True) -> str`。
它同时做三件事：把 `.deps\webview\lib` 和 `...\runtimes\win-x64\native` 加进 `PATH`；
`ensure_sta_com()`（`CoInitializeEx(None, COINIT_APARTMENTTHREADED)`，否则
`CoreWebView2Environment.CreateAsync` 报 `COMException (0x800401F0): 尚未调用 CoInitialize。`）；
预加载 `System.Windows.Forms` / `Microsoft.Win32.SystemEvents` / `System.Drawing.Common`。

`runtimeconfig.json` 用显式文件而不是让 `clr_loader` 自己生成，是因为后者会建临时目录再 `cleanup()`，
本沙箱的临时目录清理会抛 `PermissionError`：

```json
{"runtimeOptions": {"tfm": "net8.0", "rollForward": "LatestMajor",
  "framework": {"name": "Microsoft.WindowsDesktop.App", "version": "8.0.0"},
  "configProperties": {"System.Runtime.Serialization.EnableUnsafeBinaryFormatterSerialization": true}}}
```

### 3.3 障碍 2：pywebview 自带的 WebView2 interop 只有 .NET Framework 版

pywebview 6.2.1 里 `webview\lib\Microsoft.Web.WebView2.Core.dll` / `.WinForms.dll`
（AssemblyVersion `1.0.3856.49`，`TargetFramework=.NETFramework,Version=v4.6.2`）在 coreclr 下加载到

```
System.TypeLoadException: Could not load type 'System.Windows.Forms.ContextMenu'
from assembly 'System.Windows.Forms, Version=8.0.0.0'
   at webview\platforms\edgechromium.py:48
```

（`ContextMenu`/`MainMenu` 在 .NET Core 3.0 的 WinForms 里已被删除。）

**修复**：换 NuGet 上**最后一个提供 `lib/netcoreapp3.0` 的版本** `microsoft.web.webview2 1.0.2478.35`。
分界线是实测出来的（用 HTTP Range 只读 nupkg 的中央目录，不下 9 MB 全文）：

* `1.0.1774.30 / 1.0.1901.177 / 1.0.2088.41 / 1.0.2210.55 / 1.0.2478.35`：有 `lib/net45` + `lib/netcoreapp3.0`
* `1.0.2792.45 / 1.0.3296.44 / 1.0.3800.47 / 1.0.4258.31`：**只剩 `lib/net462`**

替换后的实测尺寸（原 netfx 版备份在 `.deps\.webview2-netfx-backup\`）：

| 文件 | netfx（原） | netcoreapp3.0（替换后） |
|---|---|---|
| `webview\lib\Microsoft.Web.WebView2.Core.dll` | 649,800 | **567,896** |
| `webview\lib\Microsoft.Web.WebView2.WinForms.dll` | 39,016 | **38,360** |
| `webview\lib\runtimes\win-x64\native\WebView2Loader.dll` | 161,864 | **165,336** |

### 3.4 障碍 3：`OpenFolderDialog` 在 .NET 8 上反射必炸

`webview/platforms/winforms.py` 的 `class OpenFolderDialog` 在**类体里**就取反射句柄：

```python
iFileDialogType = windowsFormsAssembly.GetType('System.Windows.Forms.FileDialogNative+IFileDialog')  # → None
setOptionsMethodInfo = iFileDialogType.GetMethod('SetOptions', flags)
# AttributeError: 'NoneType' object has no attribute 'GetMethod'
```

.NET 8 的 WinForms 改用 CsWin32（`OpenFileDialog.CreateVistaDialog()` 返回
`Windows.Win32.Foundation.ComScope\`1[Windows.Win32.UI.Shell.IFileDialog]`，`OnBeforeVistaDialog` 已删除），
程序集里**根本不存在** `*FileDialogNative*` 类型（`probe_filedialog.py` 枚举确认）。
异常被 guilib 吞掉后，`webview.start()` 对外只报一句误导性的
`WebViewException('You must have pythonnet installed in order to use pywebview.')`。

**修复**：`fixup_winforms_patch()` 做文本补丁（幂等，锚点是原文逐字片段，标记 `XINXUAN-CLR-PATCH`）：
把 `iFileDialogType` 的计算挪出 `try`、九个反射句柄默认 `None`、设 `_folder_dialog_error`，
并在 `OpenFolderDialog.show` 顶部插入回退分支 `_show_via_folder_browser()`（用 `FolderBrowserDialog`）。
补丁只能用文本方式做——`winforms.py:672/716` 出现标记，`687/690/715` 是 `_folder_dialog_error`，`731` 是回退分支。

补丁后 WinForms 后端**能导入了**，`webview.start()` 打印 `[pywebview] Using WinForms / Chromium`。

### 3.5 最终边界：窗口永远起不来（Chromium Mojo IPC 被沙箱拒）

打通上面三层后，`webview.start()` 仍然失败：

```
(0x8000FFFF): E_UNEXPECTED
   at Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateCoreWebView2ControllerAsync(IntPtr, CoreWebView2ControllerOptions)
   ← Microsoft.Web.WebView2.WinForms.WebView2.InitCoreWebView2Async
   → pywebview 包装成 WebViewException('Main window failed to start')   (webview\window.py:44)
```

逐个排除掉的假设（都实测过，都**不是**主因）：

| 假设 | 实验 | 结果 |
|---|---|---|
| COM 单元状态 | 裸探针 + `CoInitializeEx(STA)`；`threading.setprofile` 钩住建窗线程 | 已修（`0x800401F0` 消失），但窗口仍失败 |
| Chromium 沙箱 | `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--no-sandbox --disable-gpu"` | 无变化 |
| 命名管道被禁 | `CreateNamedPipeW(r"\\.\pipe\xinxuan-pipe-test", ...)` | 句柄 `0x64`，`LastError=0` → **管道没被禁** |
| 进程根本没起来 | Toolhelp32 快照轮询（`probe_wv2proc.py`） | `CreateAsync` 阶段不启动浏览器进程（懒加载），无法据此判断 |

**决定性证据**：用户数据目录 `.tmp\exe-probe\wv2data\EBWebView\` 被完整创建
（`Default`、`Crashpad`、`BrowserMetrics`、`Local State`、`component_crx_cache` …），
说明 `msedgewebview2.exe` **确实启动过并写了 profile**。加上
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--enable-logging --v=1 --no-sandbox --disable-gpu"` 后，
`.tmp\exe-probe\wv2data\EBWebView\chrome_debug.log`（232 字节）全文只有两行：

```
[45028:36540:1006/160321.658:ERROR:base\win\edge_dpi_util.cc:218] failed to set WebView dpi awareness of 1
[45028:22692:1006/160321.701:FATAL:mojo\public\cpp\platform\platform_channel.cc:187] Check failed: . : 拒绝访问。 (0x5)
```

即：`msedgewebview2.exe` 走到 Chromium **Mojo 平台通道**（它自己的 IPC 命名管道建立）时被沙箱拒绝，
FATAL 退出；宿主因此拿到 `E_UNEXPECTED`。这与之前记录的 headless Edge 崩溃
（`msedge.exe ... exception 0x80000003 ... 拒绝访问`）是同一类失败。

### 3.6 pywebview 可行性判定（明确结论）

* **在普通 Windows 桌面上**：pywebview + pythonnet 这一套是**可用**的。理由：从 Python 层层往上
  到 `CoreWebView2Environment.CreateAsync` 成功返回 `BrowserVersionString = 154.0.4258.53`
  （与机器上装的 WebView2 Runtime 一致）——**每一层都实测通过**，唯一失败的调用是
  `CreateCoreWebView2ControllerAsync`，而其失败原因是浏览器进程被沙箱杀死。
  ⚠️ **"在正常桌面上就能弹出窗口"这一步我没有实测过，属于高置信度推断**，不要写成实测。
* **在 DSH 沙箱内**：**不可用，且不可绕过**。因此：
  * 截图**做不了**（窗口起不来），不要伪造；
  * 交付必须保留 `xinxuan.py` 已有的浏览器模式兜底（`webbrowser.open`，见 `xinxuan.py:248-253`）。
* 以上修复仍然值得保留：它们让 `import webview` → `webview.start()` 这条路在**真实桌面上**
  从"必然崩"变成"可用"，成本只有三个 fixup。

---

## 4. PyInstaller：onefile 不可运行，onedir 可用

### 4.1 环境变量与冒烟脚本

`.tmp\exe-probe\hello.py`：打印 `HELLO-FROM-FROZEN-EXE`、`sys.frozen`、`sys._MEIPASS`、`sys.path`、
`.deps` 命中项，然后起 `http.server.ThreadingHTTPServer(("127.0.0.1", 0))` 自请求一个固定串，
要求 `status==200 and "FROZEN-HTTP-OK" in body and not deps_on_path`，最后打印
`RESULT: FROZEN_EXE_SMOKE_OK`。

构建命令（`--onefile` 版，实测可构建）：

```powershell
$env:PYTHONPATH = "$ws\.deps"
& $py -m PyInstaller --onefile --noconfirm --clean --log-level WARN `
    --workpath "$ws\.tmp\exe-probe\build" --distpath "$ws\.tmp\exe-probe\dist" `
    --specpath "$ws\.tmp\exe-probe" "$ws\.tmp\exe-probe\hello.py"
```

* 构建耗时 **8.99 s / 11.34 s**（两次），产物 **9,201,103 B / 9,201,659 B**；
* bootloader 用的是 `.deps\PyInstaller\bootloader\Windows-64bit-intel\run.exe`（sdist 里带了预编译 bootloader）；
* **不需要** `--collect-all`，也不需要 `--paths .deps`（纯标准库负载）；构建日志尾：
  `Appending PKG archive to EXE` / `Fixing EXE headers` / `Build complete!`。

### 4.2 `--onefile` 产物在本沙箱**无法运行**（原始报错）

把 exe 复制到 `.tmp\exe-independence\` 后直接运行（`PYTHONPATH`/`PYTHONHOME` 已清空），
约 0.27 s 即退出：

```
[PYI-39092:ERROR] Failed to extract VCRUNTIME140.dll: failed to open target file!
fopen: Permission denied
[PYI-39092:ERROR] Failed to extract entry: VCRUNTIME140.dll.
```

试过并**全部同样失败**的三种配置：默认 `TEMP`、把 `$env:TEMP`/`$env:TMP` 指到工作区内目录、
构建期烤入 `--runtime-tmpdir <工作区内目录>`。

诊断（已排除的解释）：
* `_MEIxxxxx` 解压目录**创建成功**（`...\pytemp\_MEI000093542`、`...\dsh-iIBJgs\_MEI000098b42`，均为 0 文件）；
* 用 Python 子进程往同一目录写一个 `.dll` 是**成功**的（`WRITE_DLL_OK 32`），所以不是"DLL 不能写"；
* PyInstaller 源码位置：`bootloader\src\pyi_archive.c:277` 的 `pyi_path_fopen(output_filename, "wb")` 返回 NULL，
  调用方是 `pyi_launch.c:147`，`output_filename = application_home_dir + entry_filename`。

**机制未完全定位**，表现像是沙箱对**非 Python 子进程**的文件创建做了限制。结论：
**本机只能证明 `--onedir`**；`build_exe.py` 默认 `--onedir` 是对的选择（它的文件头也记录了同样的失败）。

### 4.3 `--onedir` 实测通过

```
RESULT: FROZEN_EXE_SMOKE_OK
```
* 退出码 0，墙钟 **0.894 s**，54 文件 / **22.92 MB**（构建 7.52 s）；
* 运行时 `_MEIPASS = ...\dist-od\hello\_internal`，`sys.path = [_internal\base_library.zip, _internal\python3.12\lib-dynload, _internal]`；
* `external .deps entries on sys.path: []`、`PYTHONPATH env: None`、`PYTHONHOME env: None`；
* 自请求 `status=200`、`body` 含 `FROZEN-HTTP-OK`、`elapsed_ms: 28`。

---

## 5. 真机冒烟：打包后的 `芯选.exe`（未改 `build_exe.py`，产物在 `.tmp`）

用 `build_exe.py` 的**全部参数**（含 `--exclude-module scipy/sklearn/joblib/threadpoolctl`、
`--collect-data jieba`、`--name 芯选`、`--onedir --console`）构建到
`.tmp\exe-probe\dist-xinxuan\芯选\`：

```
build time : 26.89 s
app exe    : ...\.tmp\exe-probe\dist-xinxuan\芯选\芯选.exe (10,385,209 B)
files      : 834
total size : 111,753,896 B = 106.58 MB
RESULT: XINXUAN_BUILD_DONE
```

构建期两条**非致命但值得看**的警告：

```
WARNING: Hidden import "pycparser.lextab" not found!
WARNING: Hidden import "pycparser.yacctab" not found!
WARNING: QtLibraryInfo(PyQt5): failed to obtain Qt library info: Child process call to
  _read_qt_library_info() failed with: AttributeError: module 'PyQt5.QtCore' has no attribute 'QCoreApplication'
```

（第二条是 `.deps` 里 **空的 `PyQt5` 命名空间目录** 引起的——`fetch_deps.py` 盲目解包 sdist 的副产物。
建议：打包前删掉 `.deps\PyQt5`、`.deps\pyi_*` / `hookutils_package` / `multipackage_test_pkg` / `unzipped_egg` 等
PyInstaller 自测夹具目录，可消除这类噪声。）

### 5.1 冷启动与真实接口（工作区内运行）

`.tmp\exe-probe\run_xinxuan_probe.py`：清空 `PYTHONPATH/PYTHONHOME/PYTHONUTF8/PYTHONIOENCODING`，
子进程 stdio 重定向到**真实文件**（本沙箱禁止进程间管道 stdio），
从 `Popen` 开始计时，轮询 `/api/health`：

```
health     : 200 {"rows":89,"status":"ok","version":"1.4"} after 0.736 s
index      : 200 23426 bytes in 0.005 s
index 芯选 : True
recommend  : 200 in 386 ms  matched='STM32F103C8T6' mode='part' filtered_out=0
top1       : 'APM32F103C8T6' sim=0.2736 score=0.7256 tier='Pin-to-Pin 直接替换' risk='🟢低风险'
RESULT: XINXUAN_RUN_OK
```

### 5.2 独立性证明：搬到工作区之外仍然正常

把整个 `芯选\` 目录复制到 **`C:\Users\13718\AppData\Local\Temp\dsh-iIBJgs\xinxuan-independence\xinxuan\`**
（工作区外），清空 `PYTHONPATH`/`PYTHONHOME` 再跑：

```
health     : 200 {"rows":89,"status":"ok","version":"1.4"} after 0.748 s
recommend  : 200 in 380 ms
top1       : 'APM32F103C8T6' sim=0.2736 score=0.7256 tier='Pin-to-Pin 直接替换' risk='🟢低风险'
RESULT: XINXUAN_RUN_OK
```

→ **exe 不依赖 `.deps`、不依赖工作区**。子进程 stderr 只有 jieba 的三行自述
（`Building prefix dict from the default dictionary ... Loading model cost 0.369 seconds.`）。
`sys.stdout` 为空是因为应用自己把日志写进 `xinxuan.log`，不是丢失。

### 5.3 打包后的完整链路冒烟（更早一次，`.tmp\exe-probe\hello_app.py`）

```
RESULT: FROZEN_APP_SMOKE_OK        (exit 0, 墙钟 1.442 s)
external .deps entries on sys.path: []
sklearn : not importable -> No module named 'sklearn'
vectorizer: numpy   HAS_JIEBA= True
default CSV -> _internal\data\samples\chips_seed.csv   rows=89
recommend : top1=APM32F103C8T6 similarity=0.2736 score=0.7256 tier=Pin-to-Pin 直接替换 risk=🟢低风险
recommend elapsed_ms: 4.44  mode: part
```

同时做了开发态 vs 冻结态交叉验证：`data\samples\chips_seed.csv`（89 行）下
dev-numpy / dev-sklearn / 冻结态三者都是 `vocab 1311`、`[('APM32F103C8T6', 0.188625)]`，
**逐位一致**。

> 提醒 Lead：`RecallIndex.recall()` 的裸余弦是 **0.188625**，而 `recommend()` 报的相似度是 **0.2736**、
> score **0.7256**——这是不同阶段的数，两个都能复现，不是互相矛盾。
> 另外 `data\chips.csv`（300 行，vocab 4653）里**没有** `STM32F103C8T6`/`APM32F103C8T6`，
> 只有 `data\samples\chips_seed.csv` 里有（分别 6 次 / 4 次）；`chips_real*.csv` 同样没有。

---

## 6. 体积账与 sklearn 取舍

同一份应用负载、`--onedir`：

| 配置 | 文件数 | 体积 | 构建耗时 |
|---|---|---|---|
| **不含** `--exclude-module scipy/sklearn/joblib/threadpoolctl` | 812 | **127.47 MB** | 35.8 s |
| **含**以上 excludes | 1298 | **232.92 MB** | 62.2 s |

→ 裁掉这四个包**省 105.45 MB**。（顺便修正 `prototype/recall.py:12-13` 里"约 40 MB"的说法。）
裁剪后的 127 MB 里最大项：`numpy.libs\libscipy_openblas64_...dll` 20.4 MB、应用 exe 14.0 MB、
`jieba\lac_small\model_baseline\word_emb` 10.7 MB、`libcrypto-3-x64.dll` 8.0 MB、
`PIL\_avif.cp312-win_amd64.pyd` 7.9 MB、`python312.dll` 7.0 MB、`jieba\analyse\idf.txt` 6.2 MB、
`jieba\dict.txt` 5.1 MB。按包计：jieba 29.58 MB、numpy.libs 20.02 MB、pandas 13.11 MB、
PIL 12.89 MB、numpy 6.74 MB、lxml 6.68 MB。

**还能再砍的大概 49 MB**（未实施，仅供参考）：`PIL` 12.89 + `lxml` 6.68 + `jieba\lac_small` 10.7 已被
`build_exe.py` 的 EXCLUDES 覆盖了前两个；`jieba\lac_small`（词向量模型）如果不用 jieba 的相似度功能可以删。

**sklearn 是不是真的没被打进去**：`hello_app.py` 在冻结态断言过
`sklearn : not importable -> No module named 'sklearn'`，且 `--exclude-module` 生效后 exe 照常工作
——**没有发现任何隐藏 import 把 sklearn 拽回来**（Lead 问的那件事，答案是没有）。

---

## 7. 打包进 exe 的 pywebview 资源（冻结态实测）

`.tmp\exe-probe\hello_wv.py`（`import webview` 放在函数里，模拟 `xinxuan.py:124` 的 try 块）
构建结果：**92 文件 / 28.54 MB，exe 4,979,744 B**。冻结态里存在：

```
webview\lib\Microsoft.Web.WebView2.Core.dll                  567,896 B
webview\lib\Microsoft.Web.WebView2.WinForms.dll                38,360 B
webview\lib\runtimes\win-x64\native\WebView2Loader.dll        165,336 B
pythonnet\runtime\Python.Runtime.dll                          451,072 B
clr_loader\ffi\dlls\amd64\ClrLoader.dll                        10,752 B
clr_loader: OK get_coreclr
```

→ pywebview 自己的 hook（`.deps\webview\__pyinstaller\hook-webview.py` 与
`_pyinstaller_hooks_contrib\stdhooks\hook-webview.py`，两者都做
`collect_data_files('webview', subdir='lib')` + `collect_dynamic_libs('webview')`）
**自动收集了全部 .NET interop DLL，不需要 `--collect-all webview`**。

带不带 `--paths .deps` 的产物清单**逐字节相同**（92 文件 / 28.54 MB）——因为构建本身就要求
`PYTHONPATH=<ws>\.deps`（PyInstaller 自己就装在 `.deps` 里；清空 `PYTHONPATH` 会直接
`No module named PyInstaller`），而 `PYTHONPATH` 里的目录本来就在 PyInstaller 的搜索路径上。

### 7.1 一个不确定项：`WebView2Loader.dll` 的解析时好时坏

两次"同样参数"的构建表现不同（**机制未完全解释，如实记录**）：

* 一次：`webview.util.interop_dll_path('WebView2Loader.dll')` → `FileNotFoundError: Cannot find WebView2Loader.dll`
* 下一次：→ `...\_internal\WebView2Loader.dll exists=True`（该副本 **137,144 B**，
  `build-wv2\hello_wv\COLLECT-00.toc` 里记录的来源是**相对路径** `'Toolkit\\WebView2Loader.dll'`；
  我在 `.deps`、工作区、`C:\Program Files (x86)\Microsoft\EdgeWebView\Application\154.0.4258.53`
  里都**没找到**这个 137,144 B 的文件）

`Microsoft.Web.WebView2.Core.dll` / `.WinForms.dll` 在冻结树里**始终能正确解析**
（`webview\util.py:489` 的非冻结分支 `os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib', dll_name)`
在 onedir 下依然成立，因为 `_internal\webview\lib\...` 结构被保留）。
`ctypes.WinDLL("WebView2Loader.dll")` 从冻结 exe 里**两种搜索路径都成功**。

**建议**：不要依赖 `interop_dll_path` 的运气，显式钉死 loader：

```powershell
--add-binary "<ws>\.deps\webview\lib\runtimes\win-x64\native\WebView2Loader.dll;."
```

---

## 8. 给 `build_exe.py` / Lead 的建议清单

1. **保持 `--onedir` 默认**；`--onefile` 在本沙箱不可运行（4.2），交付形态用便携 ZIP。
2. **显式钉死 `WebView2Loader.dll`**（7.1），别赌 hook 的收集顺序。
3. **打包前清 `.deps` 噪声**：空的 `PyQt5`、PyInstaller 自测夹具目录（`pyi_*`、`hookutils_package`、
   `multipackage_test_pkg`、`unzipped_egg`、`waflib`…）。它们会带来 PyQt5 那条 WARNING，
   也可能解释 7.1 的不确定项。
4. `fetch_exe_deps.py` 应当在**每次打包前**跑一次（或至少 `--verify-only` 校验），
   因为它同时负责把 netcoreapp3.0 interop 和 winforms 补丁打回去。
5. `fetch_exe_deps.py` 的网络下载已加**重试 + `Content-Length` 校验**（见第 10 节的原始报错），
   并新增 `--force`；wheel 已装好时默认跳过下载。
6. 应用侧建议（**属于代码改动，我没动**）：`xinxuan.py` 在 `--windowed` 下配合 GBK 控制台时，
   给 `sys.stdout/stderr` 加 `reconfigure(encoding="utf-8", errors="replace")`。
   依据：`scripts/_check_api.py:104` 在 GBK 控制台下打印 🟢 会直接
   `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f7e2'` 而崩；
   冻结态之所以没崩，是因为日志走 `xinxuan.log` 文件而不是 stdout——控制台路径仍值得加固。

---

## 9. 实测 / 推断 / 未测 三分清单（诚实标注）

**✅ 实测（有原始输出）**
* `fetch_exe_deps.py` 幂等、`RESULT: EXE_DEPS_OK`（exit 0）；
* `PyInstaller 6.22.3` 在该 `PYTHONPATH` 模式下可 `--version`、可构建 onefile/onedir；
* coreclr 路线的 `Initialize(libpython) rc = 0` → `import clr` → WinForms → WebView2 Core 全部 OK；
* netfx 路线失败的两条原始异常（`Failed to resolve ... Loader.Initialize`、`0x80131515`）；
* `--onefile` 构建成功但运行失败（`Failed to extract VCRUNTIME140.dll`）；
* `--onedir` 冒烟 `FROZEN_EXE_SMOKE_OK`；应用级 `FROZEN_APP_SMOKE_OK`；
* 真机 `芯选.exe`：106.58 MB / 834 文件 / 构建 26.89 s / 冷启动 **0.736 s** / 推荐 **score 0.7256**；
* 工作区外运行 `XINXUAN_RUN_OK`（0.748 s）；
* 体积 127.47 MB（裁）vs 232.92 MB（不裁）；
* 冻结态里 `.NET` interop 与 `pythonnet` 运行时文件的存在与尺寸；
* `chrome_debug.log` 的 Mojo `FATAL ... 拒绝访问 (0x5)`。

**🟡 推断（未实测，别当结论引用）**
* "在普通 Windows 桌面上 pywebview 能弹出窗口"——所有中间层都实测 OK，但**没有在非沙箱环境验证过**；
* `--onefile` 在正常环境下应当可用（失败原因指向沙箱，但未在沙箱外验证）；
* 7.1 里 137,144 B `WebView2Loader.dll` 的来源；
* 删掉 `.deps` 噪声目录能消除 PyQt5 WARNING（合理但未验证）。

**⬜ 未测 / 测不了**
* `dist\芯选.exe` 的**官方构建**（`dist/` 目前不存在，构建它不在我的写入范围；
  我用同参数产物代替，未逐字节比对）。
  我构建的 `芯选.exe` = 10,385,209 B，834 文件，106.58 MB。
* **窗口渲染**与**截图**：沙箱内不可能（3.5）。
* 真实冷启动"到窗口可用"的耗时：只能给"到 HTTP 服务可用 = 0.736 s"这一代理指标，
  且是 `--no-window` 路径；窗口路径在本沙箱跑不起来（且可能弹原生对话框而挂住，故未跑）。
* `--windowed`（无控制台）形态：未测，我构建的是 `--console`。

---

## 10. 遗留风险

1. **下载脆弱性（已修）**：第一次跑 `fetch_exe_deps.py` 时 PyPI CDN 中途断开，
   原始报错 `http.client.IncompleteRead: IncompleteRead(22048 bytes read, 440097 more expected)`。
   现已改为分块读取 + `Content-Length` 校验 + 最多 4 次重试；`--force` 可强制重下。
   仍未做的是**校验哈希**（PyPI 的 `digests.sha256` 没取），属于可接受的少量残留风险。
2. **`WebView2Loader.dll` 收集不确定**（7.1）——缓解办法见第 8 节第 2 条。
3. **沙箱外行为未验证**：所有"能在真实桌面弹窗"的说法都是推断（第 9 节）。
4. **许可**：`pyinstaller-hooks-contrib` 是 **GPL-2.0-or-later**（其 `hook-webview.py` 头部声明），
   仅在**构建期**使用、不随 exe 分发；PyInstaller 本体有 bootloader 例外条款。
   如果比赛对交付物许可有要求，请自行复核——**我不是法律意见**。
5. **`.deps` 是构建期依赖，不是运行期依赖**：exe 已证明自足（5.2）。
   但 `.deps` 里混着 scipy/scikit-learn/pytest/pypdf 等与打包无关的包（222 MB），
   若要交付"可复现构建"，建议明确 `.deps` 的最小清单 = 本文件第 2 节表格所列 + numpy/pandas（来自解释器）。
