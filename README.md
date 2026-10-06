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
| GET | `/` | `part`、`top`（默认 5） | 搜索页 HTML，结果同页内联渲染 |
| GET | `/api/recommend` | `part`（型号**或**自然语言）、`top` | JSON（字段定义见文档 §3.5）；缺 `part` → 400 |
| GET | `/stats` | — | 统计页 HTML |

端口默认 `5000`，可用环境变量覆盖：`$env:PORT=8080`。数据文件默认 `data/samples/chips_seed.csv`，可用 `$env:CHIPS_CSV="<路径>"` 换成自己的数据集。

---

## 4. 目录结构

```
work_1/
├─ README.md                 本文件
├─ 需求及开发文档.md          开发依据（含第一版 MVP 设计，13 章）
├─ requirements.txt          实测版本锁定
├─ run.ps1                   一键启动 Web 服务
├─ prototype/                第一版原型（可运行）
│  ├─ data_loader.py         CSV 读取/清洗/型号查找/统计
│  ├─ recall.py              TF-IDF 召回 + 品类同义词 + 关键词重排
│  ├─ rules.py               六维兼容规则 + 功能参数指纹（最核心）
│  ├─ ranking.py             供应链加权排序
│  ├─ risk.py                风险三级 + 替代等级四档
│  ├─ recommend.py           编排 + CLI 入口
│  └─ app.py                 Flask 3 路由
├─ data/
│  └─ samples/chips_seed.csv 89 条种子数据（演示用，见下"数据声明"）
├─ tests/                    25 条回归测试（把评测发现的缺陷固化）
│  ├─ conftest.py
│  └─ test_xinxuan.py
├─ experiments/eval.py       离线评测器：E1 命中率 / E2 延迟 / E3 消融 / E4 硬约束违规
├─ scripts/                  环境/数据工具（fetch_deps / fetch_dataset / build_dataset / check）
└─ docs/refs/                赛题原文、开源核实、数据源核实、NL 评测、**评测报告**
```

---

## 5. 数据声明（**请勿误读**）

- `data/samples/chips_seed.csv` 是**人工整理的演示数据**（89 条 × 16 字段），用于跑通链路与构造兼容/不兼容样例。
- 其中 **`lead_time_days`（交期）与 `lifecycle`（生命周期）是人工整理的演示字段**，公开的 jlcparts 数据集**不提供**这两列。演示与报告中必须声明，不得声称是实时库存/交期。
- 公开数据源的真实可得性（型号/封装/库存/价格 100%，描述 61–81%，工作电压 46–59%，**引脚数 0% 需从封装串解析**）与拉取方式见文档 §4 与 `docs/refs/data-source-audit.md`。

---

## 6. 已验证的结论（可复现）

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

## 7. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `ModuleNotFoundError: No module named 'sklearn'`（或 flask/jieba） | 依赖没就位。用方式 A 装进 venv，或设 `$env:PYTHONPATH="<仓库>\.deps"` |
| `pip install` 报 `PermissionError ... .whl.metadata` | 受限沙箱拦截解包写文件，**不是网络问题**。改用 `python scripts\fetch_deps.py --target .deps` |
| 启动时中文乱码 | Windows 控制台需要 UTF-8：`chcp 65001`，并设 `$env:PYTHONIOENCODING="utf-8"`（`run.ps1` 已自动设置） |
| 查询返回一堆无关料号 | 该品类不在当前 89 条演示数据里（例如电容）。数据扩充后即改善，算法本身按"品类同义词 + 硬过滤"处理 |
| 想知道某个分数怎么来的 | 每个结果都带 `checks`（逐条规则 pass/warn/fail + 数值依据）与 `supply_detail`（供应链四个因子的实测值），无黑箱分数 |

---

## 8. 引用与许可

- 本原型**未使用任何开源项目的代码**，仅参考其设计思路；9 个候选项目的存在性/Star/License 已逐一核实，结论见 `docs/refs/opensource-audit.md`。
- 重要发现：其中多个高 Star 项目**没有 License**（默认保留版权，不可抄代码），**无 GPL/AGPL**。写报告或复用前请先看该审计文件。
- 数据来源为嘉立创 / LCSC 公开元件数据（经 jlcparts 项目整理），仅供竞赛研究使用；正式对外发布前请确认上游条款。
