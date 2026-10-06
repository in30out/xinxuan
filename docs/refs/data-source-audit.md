# 芯片元器件数据源实测审计（data-scout）

> 审计时间：2026-10-05。**所有 URL 均为本机实测结果**；未实测的条目一律标注「未验证」。
> 实测方式：Node.js `fetch`（GitHub API / GitHub Pages / codeload 可通；`raw.githubusercontent.com`、`github.com/.../raw` 在本机被网络策略阻断，curl/IWR 因 schannel 无凭证失败）。真实下载与解包见 `data/samples/`。

## 1. 结论速览

| 数据源 | 实测结论 | 是否需要 Key | 可用性 |
|---|---|---|---|
| `sleemanj/jlcparts`（仓库本身） | **没有 Releases**（`/releases` 返回 `[]`）；它是 `yaqwsx/jlcparts` 的 fork，仓库里只有抓取/生成脚本（Python + React），**不是现成数据库** | 否 | 只能当工具链用 |
| `sleemanj.github.io/jlcparts/data/all.jsonlines.tar` | **实测 200/206 可下**，tar 47,575,040 B（≈47.6 MB），1,281 个子类文件 + LUT，**567,259 条记录**；`Last-Modified: Wed, 01 Apr 2026 20:03:58 GMT`（**快照偏旧**） | 否 | ⭐ 全量首选 |
| `dougy83.github.io/jlcparts/data/all.jsonlines.tar` | **实测 200/206 可下**，transfer 4,434,808 B / 落地 tar 5,171,200 B（≈5.17 MB），419 个子类文件，**55,123 条记录**；`Last-Modified: Sun, 04 Oct 2026 10:50:12 GMT`（**日更**） | 否 | ⭐ 日更新鲜 |
| `yaqwsx.github.io/jlcparts/data/all.jsonlines.tar` | **实测 404**（上游站点未公开该路径） | 否 | 不可用 |
| `zhr1008/szlcsc-mcp` | **GitHub API 返回 404**（该路径不存在：已删/改名/私有）；**未能获得任何 README、工具名或调用方式** | 未知 | 未验证，不可用 |
| `SourceParts/parts-mcp` | 仓库存在（2026 创建，描述 "Source Parts MCP Server"）。本地 stdio 需 `SOURCE_PARTS_API_KEY`；官方托管的 `https://mcp.source.parts/` 走 OAuth「无需 API key」。含 `find_alternatives` 工具 | 本地要，托管不要 | 可用但未实测调用 |
| 立创商城（LCSC）内部 API | 仓库内 `LCSC-API.md` 记载：`GET https://lcsc.com/api/global/additional/search?q=<part>`、`POST https://lcsc.com/api/products/search`，**需 CSRF token + cookies** | 需 cookie/CSRF | 未实测（ToS 风险） |

## 2. 实测证据（可复制的下载方式）

```bash
# 全量快照（567,259 条，47.6 MB，Last-Modified 2026-04-01）
curl -L -o all.jsonlines.tar https://sleemanj.github.io/jlcparts/data/all.jsonlines.tar
# 日更包（55,123 条，约 5.17 MB，Last-Modified 2026-10-04）
curl -L -o all.jsonlines.tar https://dougy83.github.io/jlcparts/data/all.jsonlines.tar
```

实测响应头（dougy83 日更包）：`HTTP 200`、`Content-Type: application/x-tar`、`Accept-Ranges: bytes`、`Range: bytes=0-1023` → **206**；
实测响应头（sleemanj 全量）：`HEAD 200`、`Content-Range: bytes 0-4095/47575040`；下载 `BYTES=47575040`，`tar -xf` 退出码 0。

本仓库落地样本：`data/samples/jlcparts-all.jsonlines.tar`（**5,171,200 B，来自 dougy83 日更 URL**，2026-10-05 下载）。

### 2.1 数据格式（tar 内 3 类文件）

- `components-<subcategoryIdx>.jsonlines.gz`：第 1 行是**字段名→下标映射**，之后每行是 JSON 数组
  `{"lcsc":0,"mfr":1,"description":2,"attrsIdx":3,"stock":4,"subcategoryIdx":5,"joints":6,"datasheet":7,"price":8,"img":9,"url":10}`
  示例记录：`["C6595379","MP1720DH-216-LF-Z","-40℃~+85℃ … 2.5V~5.5V … MSOP-10-EP Audio Amplifiers ROHS",[0,1,…],19,1,11,"https://jlcpcb.com/api/file/downloadByFileSystemAccessId/8601067456886681600",[{"qFrom":1,"qTo":49,"price":0.9381},…],null,null]`
- `attributes-lut.jsonlines.gz`：第 N 行（0 基）= `[属性名, {"format":…,"primary":"占位名","values":{"占位名":[值,…]}}]`；**取值 = `values[primary][0]`**（注意：`primary` 不是值，别直接当值用）。dougy83 包有 43,102 条、1,030 个不同属性名。
- `subcategories.jsonlines.gz`：`[子类名, 大类名, 下标]`，例 `["Audio Amplifiers","Amplifiers and Comparators",1]` → 可还原「类别」字段。

### 2.2 字段可得性（实测 real 数据，非文档推测）

| 目标字段 | 日更包 55,123 行 | 全量包 567,259 行 | 判定 |
|---|---|---|---|
| 型号 | `lcsc`(C 编号)+`mfr`(厂商型号) 100% | 同 | ✅ 一定能拿到 |
| 厂商 | `Manufacturer` 属性存在 100%，**值非空 85.6%**（7,916 空） | 值非空 **100%** | ✅ 能拿到（日更包有 ~14% 空） |
| 类别 | `subcategories.jsonlines.gz` 可还原大类/子类 | 同 | ✅ |
| 封装 | `Package` 属性 **100% 非空**（如 `MSOP-10-EP`） | **100% 非空** | ✅ |
| 引脚数 | `Number of Pins` 属性**值全空（0 条）** | 同样 **0 条** | ⚠️ 需解析：从封装串（`LQFP48`/`SOP8L`）或描述正则提取，拿不到就标缺失 |
| 工作电压 | 任一含 voltage 属性命中 32,408（58.8%） | 255,301（45.0%） | ⚠️ 部分；属性名按类目分裂（实测 100+ 种：`Supply Voltage`/`Voltage - Supply`/`Dropout voltage`…），需按类目映射，兜底用描述里的 `2.5V~5.5V` |
| 温度范围 | `Operating Temperature` 值非空 37,235（67.6%） | 该属性名匹配 **0 条**（两包属性命名规范不同，全量包用小写风格） | ⚠️ 部分；描述里普遍含 `-40℃~+85℃`（23,735 行描述含 ℃/封装串） |
| 库存 | `stock` 数值 100%；`stock>0` 55,123 | 100%；`stock>0` 560,747、`stock=0` 6,512 | ✅ |
| 价格 | `price` 阶梯数组 100%（`{qFrom,qTo,price}`） | 100% | ✅（币种未验证） |
| 交期 | **无此字段** | **无此字段** | ❌ 只能模拟/标缺失 |
| 描述 | `description` 61.1% | 80.7% | ⚠️ 部分 |
| Datasheet | `datasheet` URL 96.6% | 92.3% | ✅（少数为厂商 PDF 直链） |
| 图片/页链 | 映射表有 `img`/`url`，样本中均为 `null` | 同 | ❌ 未确认，按缺失处理 |

**两包差异提醒**：属性命名规范不同（dougy83 fork 做了归一化，sleemanj 包为旧版小写名），切换数据源会打断属性名映射；日更包只覆盖 419 个子类/55k 行，全量包覆盖 1,281 个子类/567k 行。

### 2.3 `jlcparts-sample-subcat1.csv` 是怎么来的

由本机脚本对**下载落地的 tar** 解包后生成（非手工数据）：取 `subcategories.jsonlines.gz` 下标 1 = 「Audio Amplifiers / Amplifiers and Comparators」，把该子类前 20 条记录的 `attrsIdx` 逐条在 `attributes-lut` 中解出 `Package / Number of Pins / Supply Voltage / Operating Temperature / Manufacturer`（值取 `values[primary][0]`），再拼接原字段。**21 行（1 行表头 + 20 行数据）**，列为：
`lcsc, mfr, manufacturer, package, pins, supply_voltage, operating_temperature, stock, price_tiers, datasheet_url, description`
示例首行：`C6595379 / MP1720DH-216-LF-Z / (厂商空) / MSOP-10-EP / (pins 空) / 5.5 / -40 / 19 / [{...阶梯价...}] / https://jlcpcb.com/api/file/...`。
`data/samples/jlcparts-all.jsonlines.tar` 一行说明：**2026-10-05 由 `https://dougy83.github.io/jlcparts/data/all.jsonlines.tar` 直接下载的原始数据库（未改动）**。

### 2.4 `chips_seed.csv` 的来源（不是我产的）

`data/samples/chips_seed.csv`（90 行 = 1 表头 + 89 行 × 15 列）**不是本任务产出**，是队友建的**手造种子数据**（模拟数据）。证据：字段 `lead_time_days`、`lifecycle` 在上表中两个 jlcparts 数据库里**均不存在**；`STM32F103C8T6/GD32F103C8T6/CH32F103C8T6` 的厂商、库存、价格、交期为整数字面值，属人工填写。**只能当 mock/demo 数据用，不得声称来自真实数据源。**

## 3. 推荐数据路径（1 天内可跑通）

**主路径（当天可跑，命令见 §2）**：下载 `https://dougy83.github.io/jlcparts/data/all.jsonlines.tar`（5.17 MB，日更）→ `tar -xf` → 读 `subcategories.jsonlines.gz` 建类目表 → 读 `attributes-lut.jsonlines.gz` 建属性表 → 逐条 `components-*.jsonlines.gz` 解析。**落地字段**：型号、厂商、类别、封装、库存、价格、描述、Datasheet = 真实可拿；**工作电压/温度**按类目属性名映射（58.8% / 67.6%），余量从 `description` 正则补（`-40℃~+85℃`、`2.5V~5.5V`）；**引脚数**从封装串解析；**交期、图片、部分厂商**标 `missing` 或走模拟。
**若需要全量覆盖**（567k 行，1,281 子类）：换用 `https://sleemanj.github.io/jlcparts/data/all.jsonlines.tar`（47.6 MB），代价是快照停在 2026-04-01、且属性名映射要重写。

**字段可得性一句话**：一定拿到 = lcsc/mfr 型号、类别、封装(Package)、库存、价格阶梯、Datasheet(≈93%)；需解析或部分 = 厂商(85–100%)、电压、温度、描述；需模拟/标缺失 = **交期(lead time)**、引脚数（部分）、图片/商品页。

## 4. Key / ToS / 频率限制

| 项 | 实测/证据 | 风险 |
|---|---|---|
| jlcparts 两个 Pages tar | 无 Key、无登录、`Accept-Ranges: bytes` 支持 206；实测 5 MB 与 47.6 MB 均一次下完 | 低；建议本地缓存 + 每日最多拉 1 次，别高频刷 Pages |
| GitHub API | 匿名额度 `x-ratelimit-limit=60`/小时（实测响应头） | 低，仅用于审计，不进生产 |
| `zhr1008/szlcsc-mcp` | API 404，**无法回答是否需要 Key/限频/免费** | 未验证，不要写进方案 |
| `SourceParts/parts-mcp` | 本地 stdio 需 `SOURCE_PARTS_API_KEY`（`SOURCE_PARTS_API_URL=https://api.source.parts/v1`）；托管 `https://mcp.source.parts/` 走 OAuth 无需 key；**免费额度未验证**（未注册）；`find_alternatives` 的输入/输出 schema **未验证** | 需注册/Key；比赛前先确认条款 |
| LCSC 内部 API | `LCSC-API.md` 明说需 **CSRF token + cookies**，属非公开接口 | 中高：ToS/反爬风险，不建议作为主路径 |
| 数据合规 | jlcparts 数据源自嘉立创/LCSC 公开目录，仓库 LICENSE 为 MIT | 竞赛 demo 可用，商用需自行评估上游条款 |

## 5. 兜底数据源（2–3 个）

1. **同族全量快照（已实测，最稳）**：`https://sleemanj.github.io/jlcparts/data/all.jsonlines.tar` — 567k 行、1,281 子类，无 Key；缺点是 2026-04-01 快照、属性名旧规范。
2. **自建增量**：用 `sleemanj/jlcparts` 仓库自带 Python 抓取脚本（`jlcparts/jlcpcb.py`、`lcsc.py`）自己生成 jsonlines — 无 Key，但抓取耗时且需遵守上游 robots/条款（**本机未实测运行**）。
3. **KiCad 官方符号库 / TI・ST 官方交叉参考表**：KiCad 符号库提供封装与引脚数（可从 GitLab/GitHub 拉取）；TI/ST 官网有 Pin-to-Pin/交叉参考页 — **本地均未实测**，标注「未验证」。
4. **商用 API（均需注册 Key，未验证额度）**：Nexar/Octopart、Mouser、DigiKey 均有免费开发者额度，但需审核与 Key，15 天赛程内不适合作为唯一数据源。

## 6. 未验证清单（禁止在方案里当事实引用）

- `zhr1008/szlcsc-mcp` 的一切（仓库 404）——包括工具名、鉴权、限频、免费与否。
- `parts-mcp` 的 `find_alternatives` 请求/响应字段、免费额度、`source.parts` 定价。
- LCSC `lcsc.com/api/*` 的实际返回结构（仅读到文档描述，未发请求）。
- 价格币种、日更包的更新触发机制、日更包为何只覆盖 55k 行（观察到「419 子类 vs 1,281 子类」，原因未确认）。
- KiCad 符号库、TI/ST 交叉表、Nexar/Mouser/DigiKey 的可获取性。
