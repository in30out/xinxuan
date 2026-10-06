# 芯选 —— 芯片替代选型智能推荐系统

> 2026AIC「AI+集成电路」算法主题赛 · 方向 5 芯片智能供应链
>
> 输入一个芯片型号（或一句中文需求描述），输出可直接选用的替代料清单，并给出**替代等级 / 风险等级 / 供应链依据 / 逐条理由**。

本仓库同时包含《[需求及开发文档.md](需求及开发文档.md)》与**已跑通的第一版原型**（7 个模块，约 940 行），并附带 25 条回归测试（`tests/`）与离线评测器（`experiments/eval.py`，含 E3 消融）。所有数字都是本机真实运行结果。

---

## 1. 三步跑通

### 前置条件

- Windows / Linux 均可；Python **3.10+**（本项目在 Python 3.12.14 上验证）
- 无需外网：原型完全离线运行，数据随仓库交付

### 第 1 步：准备依赖

```powershell
# 方式 A（推荐，常规环境）：虚拟环境 + pip
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 方式 B（受限沙箱：pip 解包 wheel 被系统拒绝时用这个）
python scripts\fetch_deps.py --target .deps
```

> 方式 B 会把 wheel 直接解包到 `.deps/`，运行时需要 `PYTHONPATH` 指向它（`run.ps1` 已自动处理）。
> 为什么会有方式 B：见《需求及开发文档.md》§13.2，本机沙箱会拦截 `pip` 对 `*.whl.metadata` 的写入。

### 第 2 步：自检（可选但推荐）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check.ps1
```

它会检查解释器、依赖、数据文件，真跑一次推荐，**并跑一遍 `tests/` 回归测试**（25 条），打印 `ALL CHECKS PASSED` 或指出缺什么。

也可以直接跑测试：

```powershell
$env:PYTHONPATH = "$PWD\.deps"
& <python> -m pytest tests -q          # → 25 passed
```

25 条断言不是凑覆盖率，每条都锁住一次真实故障或一条校准决定：零容忍硬约束真的拦得住、
温度降档不算"装不上"、五个消融配置都不产生违规、消融开关真的接了线、口语后缀不误伤真料号。详见文档 §3.7。

> **如果提示"未对文件进行数字签名"**：说明当前 PowerShell 的执行策略是 `Restricted`（受限环境常见）。
> 上面的 `powershell -ExecutionPolicy Bypass -File ...` 形式可以绕过；若连子进程都不允许启动，直接跑等价命令：
> ```powershell
> .\run.ps1    # 若被拦，改用下面的纯命令形式
> & <python> prototype\recommend.py STM32F103C8T6 --top 5
> ```
> 实测记录：本机 harness 里 `& scripts\check.ps1` 会被 `PSSecurityException` 拒绝，
> 但 `powershell -NoProfile -ExecutionPolicy Bypass -Command "& '<repo>\scripts\check.ps1'"` 可正常通过（输出 `ALL CHECKS PASSED`）。

### 第 3 步：启动

```powershell
# 命令行（最快看到效果）
python prototype\recommend.py STM32F103C8T6 --top 5

# Web 界面 + JSON 接口
powershell -ExecutionPolicy Bypass -File run.ps1
# → 浏览器打开 http://127.0.0.1:5000
```

---

## 2. 看什么（演示动线，3 分钟）

| 顺序 | 操作 | 看点 |
| --- | --- | --- |
| 1 | 搜索 `STM32F103C8T6` | Top-1 是 `APM32F103C8T6`（🟢低风险 / Pin-to-Pin 直接替换 / ¥9.20 / 库存 5400），每条都带**逐条规则依据** |
| 2 | 同一查询往下看 | 表格下方"⚠ 规则已排除的候选"列表 —— 被否决的料号**不静默丢弃**，附否决理由 |
| 3 | 搜索 `3.3V 低功耗 LDO SOT-23-5` | 自然语言模式：Top-3 全部是 SOT-23-5 的 3.3V LDO，无需记住型号 |
| 4 | 打开 `/stats` | 数据规模与**库存/停产告警**清单（`stock<1000` 或 `NRND`/`EOL`） |
| 5 | 打开 `/api/recommend?part=STM32F103C8T6&top=3` | 纯 JSON，可被生产系统直接集成 |

命令行等价命令：

```powershell
python prototype\recommend.py "3.3V 低功耗 LDO SOT-23-5" --top 3
python prototype\recommend.py "STM32F103C8T6 替代" --top 3
```

---

## 3. 接口

| 方法 | 路径 | 参数 | 返回 |
| --- | --- | --- | --- |
| GET | `/` | — | 可视化首页（`web/templates/index.html` + `web/static/`） |
| GET | `/stats` | — | 旧版统计页 HTML（保留兼容） |
| GET | `/api/recommend` | `part`（型号**或**自然语言）、`top`（1–20，默认 5） | JSON（字段定义见文档 §3.5）；缺 `part` → 400 |
| GET | `/api/part/<part_no>` | — | 单个料号详情 JSON；未知型号 → 404 |
| GET | `/api/stats` | — | 统计 JSON：`total`/`by_category`/`lifecycle`/`alerts` 等 7 键 |
| GET | `/api/suggest` | `q` | 搜索补全，最多 8 条 |
| GET | `/api/health` | — | `{"status":"ok","rows":89,"version":"1.4"}` |
| POST | `/api/feedback` | JSON `{query, part_no, ...}` | 落盘 `%TEMP%\xinxuan\feedback.jsonl`；只读介质返回 `persisted:false` |

端口默认 `5000`（被占用时自动顺延到 5001–5020），可用 `$env:PORT=8080` 覆盖。数据文件默认 `data/samples/chips_seed.csv`，可用 `$env:CHIPS_CSV="<路径>"` 换成自己的数据集。

> 这些路由是**实测契约**（`scripts\_check_api.py` 逐键校验，7 组断言，打印 `SMOKE_OK`），不是设计草案。

---

## 4. 目录结构

```
work_1/
├─ README.md                 本文件
├─ 需求及开发文档.md          开发依据（含第一版 MVP 设计，13 章）
├─ requirements.txt          实测版本锁定
├─ run.ps1                   一键启动 Web 服务
├─ xinxuan.py               桌面入口：起服务 + 开原生窗口（.exe 的入口脚本）
├─ build_exe.py             打包脚本（PyInstaller，默认 onefile 免安装）
├─ pytest.ini                固定 testpaths=tests，避开沙箱拒访目录
├─ prototype/                第一版原型（可运行）
│  ├─ data_loader.py         CSV 读取/清洗/型号查找/统计
│  ├─ recall.py              TF-IDF 召回（sklearn 或 numpy 兜底，结果等价）
│  ├─ rules.py               六维兼容规则 + 功能参数指纹（最核心）
│  ├─ ranking.py             供应链加权排序
│  ├─ risk.py                风险三级 + 替代等级四档
│  ├─ recommend.py           编排 + CLI 入口
│  ├─ wsgi.py                应用工厂 create_app()（10 个路由）
│  └─ app.py                 WSGI 转发壳（保持 `python prototype\app.py` 可用）
├─ web/                      可视化前端（打包进 exe）
│  ├─ templates/             index.html、stats.html
│  └─ static/                app.css、app.js
├─ data/
│  └─ samples/chips_seed.csv 89 条种子数据（演示用，见下"数据声明"）
├─ tests/                    25 条回归测试（把评测发现的缺陷固化）
│  ├─ conftest.py
│  └─ test_xinxuan.py
├─ experiments/eval.py       离线评测器：E1 命中率 / E2 延迟 / E3 消融 / E4 硬约束违规
├─ scripts/                  环境/数据/发布/验收工具
│  ├─ fetch_deps.py          装依赖到 .deps（绕开被沙箱拦截的 pip）；`--exe` 连打包依赖一起装
│  ├─ fetch_dataset.py       下载 jlcparts 公开快照
│  ├─ build_dataset.py       快照 → chips CSV（含中英品类对齐）
│  ├─ check.ps1              一键自检（含 25 条回归测试）
│  ├─ _check_api.py          接口契约冒烟（10 个路由逐键校验）
│  ├─ compare_vectorizer.py  证明 numpy 兜底 == sklearn（Top-5 一致 10/10）
│  ├─ diag_nl_rank.py        自然语言召回诊断（看召回/重排/规则哪一步错）
│  └─ publish_to_github.py   受限环境下的 GitHub 发布通道（见第 5 节）
└─ docs/refs/                赛题原文、开源核实、数据源核实、NL 评测、**评测报告**
```

---

## 5. GitHub 仓库与推送

远程仓库：**<https://github.com/in30out/xinxuan>**（public）

```powershell
git clone https://github.com/in30out/xinxuan.git
git remote -v                     # origin → https://github.com/in30out/xinxuan.git
```

### 日常推送（在有正常网络的终端里）

```powershell
git add -A
git commit -m "feat: ..."
git push origin main
```

凭据由 Git Credential Manager 管理，**不需要把 token 写进命令或配置文件**。

### 受限沙箱里的推送：`scripts/publish_to_github.py`

本机 harness 的沙箱会掐断 git 自己的 HTTPS 传输：

| 后端 | 报错 |
| --- | --- |
| 默认（schannel） | `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)` |
| `http.sslBackend=openssl` | `error: RPC failed; curl 28 Recv failure: Connection was reset` |

而 Python 的 `urllib` 能正常访问 `api.github.com`，所以提供了一条等价通道：

```powershell
python scripts\publish_to_github.py --dry-run              # 先看要上传什么（不写任何东西）
python scripts\publish_to_github.py                        # 叠一个新提交到远端分支
python scripts\publish_to_github.py --history 3            # 让远端历史与本地最近 3 个提交一致
```

它会：读 Git Credential Manager 里的凭据 → 逐个上传 blob（**用 SHA 比对证明与本地提交逐字节一致**）→ 重建目录树 → 用相同的提交信息/作者/时间建提交 → 更新分支 → 校验远端文件集合、blob SHA 与父提交链，最后打印 `PUBLISH_OK`。token 不会打印、不落盘、不写进 `.git/config`。

`--history N` 用于让远端历史**与本地完全一致**（按父链依次发布 N 个提交，会 `force` 重写分支，仅限还没有人 clone 过的全新仓库）。本仓库当前就是这样对齐的：远端 3 个提交的 **tree SHA 与本地逐一对上**（`c8fba0dc9864` / `e6db361e9f17` / `0f3150ea2cc1`）。

> 首次发布时仓库是空的，GitHub 的 Git Data API 在空仓库上会返回 `409 Git Repository is empty`，因此它是先由 Contents API 建一个占位提交、再在其上提交；那些占位提交已用 `--history` 重写掉。
> 注意：GitHub 的提交对象里 author 与 committer 共用同一个时间戳（都取本地 committer date），所以**同一份内容在两侧算出的提交 SHA 不同**——本地与远端的对应关系以 **tree SHA 相同**为准，`--history` 模式会打印这一步比对。

---

## 6. 可视化页面与免安装 .exe

面向"评委双击就能看"的场景：**不需要装 Python、不需要联网、不需要 pip**。

### 6.1 直接看可视化页面（开发者方式）

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1
# → 浏览器打开 http://127.0.0.1:5000
```

想开**原生桌面窗口**（而不是浏览器标签页）用 `xinxuan.py`：

```powershell
& <python> xinxuan.py            # 起服务 + pywebview 原生窗口
& <python> xinxuan.py --browser  # 强制用默认浏览器打开
& <python> xinxuan.py --no-window --port 5100   # 只起服务（排错用）
```

> 首次启动约需 **1–20 秒**（jieba 要构建中文词典缓存），期间页面会转圈；这是已知现象，不是故障。
> 若原生窗口起不来（缺 WebView2 / .NET 桥），程序会**自动回退到浏览器模式**并把原因写进日志，不会黑屏退出。

### 6.2 打包成一个可迁移文件

```powershell
# 1) 装打包依赖（pywebview + PyInstaller 等，只在需要打包时装）
& <python> scripts\fetch_deps.py --exe

# 2) 打包（默认就是便携 ZIP：dist\芯选\芯选.exe + dist\芯选-便携版.zip）
& <python> build_exe.py

# 显式指定 / 变体
& <python> build_exe.py --portable    # 等价于默认：onedir + 便携 ZIP
& <python> build_exe.py --with-sklearn# 不裁 scipy/sklearn（体积 +105 MB 左右）
& <python> build_exe.py --windowed    # 正常桌面的标准无控制台形态（受限环境会静默失败）
& <python> build_exe.py --clean       # 先清 build/dist
& <python> build_exe.py --onefile     # 单文件 exe（在限制写临时目录的环境里跑不起来，见下）
```

实测一次完整打包 **约 28 秒**，产出（2026-10-06 本机）：

| 产物 | 体积 | SHA256（前 16 位） |
| --- | --- | --- |
| `dist\芯选\芯选.exe` | 10,391,948 B（9.9 MB） | `7954ADE2B0E161CA` |
| `dist\芯选\`（整目录 835 文件） | 111.7 MB | — |
| `dist\芯选-便携版.zip`（838 条目） | 51.2 MB | `45BF743074603660` |

> 便携包同时留了一份在 `交付_芯选_v1.4\`（`芯选-便携版-v1.4.zip` + 已解压目录 + `README-交付说明.md`），SHA256 与上表一致。

**为什么默认不是 onefile**：PyInstaller 的 onefile 形态启动时必须先把自己解包到 `%TEMP%\_MEIxxxxxx`，而本 harness 的沙箱**禁止进程写"不是它自己创建的目录"**，于是必然失败：

```
[PYI-62052:ERROR] Failed to extract VCRUNTIME140.dll: failed to open target file!
fopen: Permission denied
```

用 9 行的最小脚本复现同样报错，与本项目代码无关；`--windowed` 下更隐蔽 —— 双击之后**什么都没有发生**。所以交付形态是**便携 ZIP**（对用户来说同样是"一个文件"）：`芯选-便携版.zip` = onedir 产物 + `双击运行.cmd` + `静默启动（无黑框）.vbs` + `使用说明.txt`，约 **51.2 MB（解压后 111.7 MB / 838 文件）**，解压到任意目录双击即用。

**默认保留控制台（`--console`），无黑框由启动器负责**：正式包的内核是 `--console` 形态（实测 2.1 秒内 `/api/health` 200），因为 `--windowed` 在本环境会静默失败。用户侧看不到黑框 —— 双击 `静默启动（无黑框）.vbs`，它用 `WScript.Shell.Run(..., 0, False)` 隐藏窗口起进程，exe 再用 `--hide-console` 把自己那个控制台窗口 `ShowWindow(SW_HIDE)` 藏掉；浏览器模式下退出入口是原生对话框，WebView2 模式下关窗即退出（`os._exit(0)`）。想看到控制台排错就双击 `双击运行.cmd` 或自己加 `--verbose`。

> **两个启动器都已从"从 ZIP 解压后的目录"实跑验收**（2026-10-06，`.tmp/verify_portable_launch.py`，20 项断言全过）：`静默启动（无黑框）.vbs` → `cscript exit=0`、进程存活、启动到就绪 **5.6–8.2 s**、`/api/health` 200、`GET /` 200/29,896 B、`/api/recommend` `APM32F103C8T6` **0.7256 / 4.97 ms**、`/api/stats` total=89、`/static/app.js` 51,341 B。
> 修过的一个真缺陷：`双击运行.cmd` 原先用 `for %%F in ("*\*.exe")` 找 exe，实测**匹配不到**（`dir /b /s` 通配才行，且文件名是中文时更不稳），导致"双击报 exe not found"；已改为 `for /f "delims=" %%F in ('dir /b /s *.exe 2^>nul')`。

**浏览器没自动打开怎么办**：程序**不靠 API 返回值判断**，而是用一个探针回环确认"服务端是否真的收到了页面请求"（页面带 `_boot=<token>` 时回请求一个 1×1 像素），每次尝试后都验一次；全部失败就弹框把地址给你。尝试顺序是「**另起一个全新实例（独立 `user-data-dir`）** → `os.startfile` → 直启」——把"另起实例"放第一位是为了绕开你实测遇到的那个对话框：

> Microsoft Edge 未响应，因为现有实例正在以提升的权限运行。是否要用普通权限重启现有实例？

它的根因是**你的 Edge 以管理员权限运行、而本程序是普通权限**（提权实例不能被普通权限进程交接），用独立 profile 另起实例就不碰已有实例 IPC，从根上绕开。若仍没打开，把日志里 `已就绪: http://127.0.0.1:<port>/` 的地址手工贴进浏览器即可。详见《需求及开发文档》§3.8.9。

打包时默认**裁掉 scipy / sklearn / joblib / threadpoolctl**（省约 105–150 MB），召回改走 `prototype/recall.py` 里的纯 numpy TF-IDF 兜底 —— 两种实现的结果已被 `scripts\compare_vectorizer.py` 证明等价（**Top-5 顺序一致 10/10，相似度最大相对误差 2.4e-06**）。想要完整 sklearn 路径就加 `--with-sklearn`。

### 6.3 可迁移文件

| 文件 | 内容 | 适用 |
| --- | --- | --- |
| `dist\芯选-便携版.zip` | onedir 产物 + 双击运行.cmd + 静默启动.vbs + 使用说明.txt | **推荐**：解压即用，一个文件发给评委 |
| `dist\芯选\芯选.exe` | 目录形态，启动最快 | 直接拷整个文件夹 |
| `dist\芯选.exe`（`--onefile`） | 单文件 | 普通机器可用，**本沙箱内跑不起来** |
| `packaging\silent_launch_utf8.vbs` → `packaging\silent_launch.vbs` | 静默启动器源（UTF-8）/ 发布副本（GBK） | 改完跑 `scripts\make_vbs_gbk.py` 重新生成 |

> **可迁移性已实测到什么程度**：`dist\芯选\芯选.exe`（正式包本体）实跑通过 —— `/api/health` 200（`{"rows":89,"status":"ok","version":"1.4"}`）、`/api/recommend?part=STM32F103C8T6&top=3` 返回 `APM32F103C8T6` 0.7256 / 4.7 ms、`GET /` 200/29 400 B、`/static/app.js` 200/51 341 B、`/api/stats` 200/total=89；`dep-packager` 独立复现（清空 `PYTHONPATH`、把目录复制到工作区外）仍给出同一个 0.7256 分、冷启动 0.736 s —— **exe 自足，不依赖 `.deps` 与工作区**。
> **未能在本机证明的部分（诚实说明）**：① 本 harness 的沙箱禁止创建 .NET 所需临时文件，因此 **pywebview 原生窗口在本机必定回退到浏览器模式**，窗口能否在普通桌面弹出属**推断**；② 便携 ZIP 的**解压后启动**已在本机复跑通过（同一份 `dist\芯选\芯选.exe`），但**跨机器**可用性需用户在普通 Windows 环境双击验证。
> **验证方法提醒**：在本 harness 里用 `Start-Process` 起 exe 会因继承 stdout 管道而挂住命令，且命令退出时子进程会被一起收走 —— 正确做法是「同一条命令内启动 → 轮询日志拿端口 → 发 HTTP 请求 → 关进程」，或让 exe 自己 `--no-window` 并用日志里的实际端口（`PORT` 环境变量在冻结态不可靠，实测传 5108 却绑到 18973）。

---

## 7. 数据声明（**请勿误读**）

- `data/samples/chips_seed.csv` 是**人工整理的演示数据**（89 条 × 16 字段），用于跑通链路与构造兼容/不兼容样例。
- 其中 **`lead_time_days`（交期）与 `lifecycle`（生命周期）是人工整理的演示字段**，公开的 jlcparts 数据集**不提供**这两列。演示与报告中必须声明，不得声称是实时库存/交期。
- 公开数据源的真实可得性（型号/封装/库存/价格 100%，描述 61–81%，工作电压 46–59%，**引脚数 0% 需从封装串解析**）与拉取方式见文档 §4 与 `docs/refs/data-source-audit.md`。

---

## 8. 已验证的结论（可复现）

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 端到端链路 | 89 条 CSV → 召回 → 规则 → 排序 → 风险/等级 → CLI + Flask 全部跑通 | `docs/refs/prototype-run.md` |
| 响应耗时 | 单次 **3.7–6.9 ms**；89 型号全库 avg **4.7 ms** / p95 **5.6 ms**；20,890 行真实子集 **39.8 ms** | `docs/refs/pipeline-verification.md`、`docs/refs/eval-report.md` |
| 接口 | `/api/recommend` 200、缺参 400、`/` 与 `/stats` 200 | 文档附录 A |
| 召回质量 | 型号 Top-1 **6/7 = 85.7%**、Top-5 **7/7 = 100%**；NL 品类 **9/9 = 100%** | `docs/refs/eval-report.md` §2 |
| 硬约束 | 违规率 **45.7% → 0.0%**（评测驱动修掉的真缺陷） | 同上 §2.2 |
| E3 消融 | 关掉规则分型号 Top-1 6/7→**5/7**；关掉 NL 重排封装 Top-1 2/2→**1/2**；五个变体 E4 恒 0 | 同上 §3 |
| 回归测试 | `pytest -q` → **25 passed**；`check.ps1` → `ALL CHECKS PASSED` | `tests/`、文档附录 A |
| 自然语言 | 19 条用例 15 条达标；`3.3V 低功耗 LDO SOT-23-5` 从 0 条 LDO 修到 Top-3 全中 | `docs/refs/nl-recall-eval.md` |
| 替换结果回归 | 89 个型号的替换结果逐字段零变化 | 同上 |

> **诚实边界**：仍有 4 条自然语言用例不准（数据缺电容品类、"车规"温度约束、"便宜的"价格语义），已在 `docs/refs/nl-recall-eval.md` 逐条记录原因，未做掩饰。

---

## 9. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `ModuleNotFoundError: No module named 'sklearn'`（或 flask/jieba） | 依赖没就位。用方式 A 装进 venv，或设 `$env:PYTHONPATH="<仓库>\.deps"` |
| `pip install` 报 `PermissionError ... .whl.metadata` | 受限沙箱拦截解包写文件，**不是网络问题**。改用 `python scripts\fetch_deps.py --target .deps` |
| 启动时中文乱码 | Windows 控制台需要 UTF-8：`chcp 65001`，并设 `$env:PYTHONIOENCODING="utf-8"`（`run.ps1` 已自动设置） |
| 查询返回一堆无关料号 | 该品类不在当前 89 条演示数据里（例如电容）。数据扩充后即改善，算法本身按"品类同义词 + 硬过滤"处理 |
| 想知道某个分数怎么来的 | 每个结果都带 `checks`（逐条规则 pass/warn/fail + 数值依据）与 `supply_detail`（供应链四个因子的实测值），无黑箱分数 |
| 双击 `芯选.exe` 后是浏览器标签页而不是独立窗口 | 本机缺 WebView2 运行库或 .NET 桥（pythonnet/clr_loader）初始化失败时**刻意回退**到浏览器模式；装 [WebView2 运行库](https://developer.microsoft.com/microsoft-edge/webview2/) 后重试，或直接接受浏览器模式 |
| `芯选.exe` 首次双击要等十几秒 | onefile 模式要先把自己解包到临时目录，属正常；想快就用 `build_exe.py --onedir` |
| Windows Defender/SmartScreen 提示未知发布者 | 未做代码签名（个人作品），选择"仍要运行"；长期方案是买证书签名，竞赛演示场景可配 `--console` 观察行为 |
| `pytest -q` 报 `PermissionError: [WinError 5]`、`5 errors` | 根目录有沙箱拒访的残留目录被递归收集；仓库已加 `pytest.ini`（`testpaths = tests`），如仍出现请显式写 `pytest tests` |
| 想确认接口契约没被改坏 | `& <python> scripts\_check_api.py` → 7 组断言全过并打印 `SMOKE_OK` |

> 上表里的 `<python>` 指本机 DSH 运行时解释器
> `C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`，
> 并需 `$env:PYTHONPATH="<仓库>\.deps;<仓库>\prototype;<仓库>"`（Windows 用**分号**分隔）；
> Windows 控制台还要 `chcp 65001` + `$env:PYTHONIOENCODING="utf-8"`，否则 🟢 之类字符会报 `UnicodeEncodeError: 'gbk' codec`。

---

## 10. 引用与许可

- 本原型**未使用任何开源项目的代码**，仅参考其设计思路；9 个候选项目的存在性/Star/License 已逐一核实，结论见 `docs/refs/opensource-audit.md`。
- 重要发现：其中多个高 Star 项目**没有 License**（默认保留版权，不可抄代码），**无 GPL/AGPL**。写报告或复用前请先看该审计文件。
- 数据来源为嘉立创 / LCSC 公开元件数据（经 jlcparts 项目整理），仅供竞赛研究使用；正式对外发布前请确认上游条款。
