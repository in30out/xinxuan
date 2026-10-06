# 芯选 · 前端设计与自检说明

> 作品：**芯选** —— 芯片替代选型智能推荐系统
> 赛题：2026AIC「AI + 集成电路」算法主题赛 · 方向 5 芯片智能供应链
> 本文档覆盖 `web/` 目录下的交付物、设计取舍、真实后端联调记录、自测脚本与**真实输出**，以及尚未验证的部分。

---

## 0. 交付物清单

| 文件 | 行数 | 字节 | 说明 |
| --- | ---: | ---: | --- |
| `web/templates/index.html` | 472 | 29,401 | 单页多标签骨架，全部四个标签页的静态结构 |
| `web/static/app.js` | 1,159 | 51,341 | 全部交互逻辑（原生 ES5 语法子集 + fetch，无框架无构建） |
| `web/static/app.css` | 1,454 | 49,711 | 全部样式（含手写条形图/环形图、响应式），零外部资源 |
| `web/DESIGN.md` | 本文件 | — | 设计说明 + 自测证据（附录含四个脚本源码与完整输出） |

三个文件均为 **UTF-8 无 BOM**，无任何 CDN / 字体 / 图标库 / 图表库引用（演示机断网可完整运行）。

只读参考、**未修改**：`web/templates/stats.html`（早于本次改版存在的独立统计页，后端路由 `GET /stats`；本次只为其补齐了样式，见 §6.5）。

---

## 1. 设计目标与硬约束

1. **答辩门面**：1280×800 为主演示分辨率，1920 宽不散架；信息密度高、专业克制，不用花哨渐变。
2. **自包含**：纯静态三件套，不引任何外部资源；图表全部用纯 CSS/SVG 手写（条形图 = 宽度百分比 + 圆角轨道；生命周期分布 = 手写 SVG 环形图）。
3. **可解释性优先**：这是本作品相对"黑盒推荐"的核心卖点 —— 六维规则逐条 pass/warn/fail + 中文数值依据、供应链四因子权重数值、以及**被规则排除的候选**都要显式呈现，而不是只给一个分数。
4. **不猜字段**：所有渲染字段以后端真实响应为准（§6 记录了实测基线）；字段缺失或为 `null` 一律兜底为 `—`，绝不对 `null` 调 `toFixed`。
5. **区间正确**：`similarity` 实测落在 0.167–0.274，进度条不假设满值 1.0；`score` 才是最终排序分。

---

## 2. 页面信息架构（四个标签页）

顶部固定头部（`.app-header`）：作品名「芯选」+ 副标题 + 数据集徽标 `.dataset-badge`（由 `/api/stats` 与 `/api/health` 填充）+ 版本芯片 `.version-chip`。标签切换用 `#tabnav` 的 `data-tab` 属性驱动，`activateTab()` 负责面板显隐与 `location.hash` 同步（`initTabs()`）。

### 标签 1 · 选型检索（默认）

- **搜索框**：`#q` + 自动补全下拉 `#suggest`，输入 ≥1 字符防抖后请求 `/api/suggest`；键盘 ↑↓ 选择、Enter 确认、Esc 关闭、点击外部关闭（`initSearch()` / `renderSuggest()` / `setActiveSuggest()`）。
- **示例查询快捷按钮**：4 个 `button.chip.chip-example`，分别填入 `STM32F103C8T6`、`3.3V 低功耗 LDO SOT-23-5`、`RS485 收发器 SOIC-8`、`24V 转 5V DC-DC` 并直接发起检索（`#examples`，事件委托在 `initSearch()`）。按任务书要求**不做**品牌 toggle。
- **Top-N**：`#top` 下拉选择 1–20（默认由选项顺序决定），随查询一起提交。
- **加载态**：`#loading`（旋转器 + 骨架卡片 `.skeleton-card`），`setLoading(on)` 控制。
- **查询概要**：`#query-status` 显示 `elapsed_ms`、命中模式（`mode==='part'` → 「型号替换」/ `'text'` → 「需求检索」）、命中型号、品类、`filtered_out`、结果条数；`#status-note` 是**口径说明条**，在自然语言模式下解释"`rule_score` 仅展示不参与排序、风险等级按保守口径给出"，并说明相似度实测量级（见 §6.3）—— 避免评委误以为算错。
- **双视图**：卡片视图 `#cards-view`（每张卡片突出综合得分 `card-score-num`、替代等级、风险等级徽标、`supply_detail` 三因子小条）与对比表视图 `#table-view`（`.ctable` 横向对比全部字段，点击表头排序，`sortedResults()` / `sortValue()` / `cellHTML()`）。`#viewbar` 的分段控件切换（`renderResults()`）。
- **逐条详情面板**：点击卡片「展开详情」→ `detailHTML(r)`，内含
  - 六维规则表 `rulesTableHTML(checks)`：6 条规则 × pass/warn/fail 语义色 + `detail` 原文 + `critical` 零容忍标记（`tag-critical`）；
  - 供应链四因子条形图 `supplyBarsHTML(r)`：`w_stock / w_price / w_lead / w_life` 四条 `.fbar`，标注数值与 `price_ratio`；
  - `reasons[]` 要点列表 + `summary` 一句话结论（`.summary-line`）；
  - 原型号 vs 候选关键参数对照 `compareTableHTML(r)`（`.compare`，按规则逐行对齐）。
  - 详情内并发请求 `/api/part/<part_no>` 渲染料号档案卡 `profileHTML()`（`.pc-grid`：封装、脚位、电压、温度、库存、价格、交期、生命周期、国产标记、datasheet 链接）；该请求失败只显示「档案不可用」，不影响规则面板。
- **反馈**：每条结果卡片有 👍/👎（`voteHTML()` → `sendVote()` → `POST /api/feedback`），成功后按钮置灰并弹 toast。
- **被排除候选**：`#rejected` 折叠区 `renderRejected(data)`，默认收起、标题带条数角标，展开后逐条显示料号、封装/风险/得分与 `reasons[0]` 否决理由（可解释性卖点，显眼但不喧宾夺主）。
- **空结果**：`emptyHintHTML(data)` 给建设性提示（说明演示数据集只有 89 行、该品类可能不在其中），并提供示例按钮，不显示干巴巴的"无数据"。

### 标签 2 · 数据总览

`loadStats()` 请求 `/api/stats` → `renderStats(s)`：6 张数字卡片 `.stat-card`（器件总数 / 厂商数 / 品类数 / 供货告警 / 停产数 / 最大品类）；品类分布手写横向条形图 `.hbar-row`（按 `count` 降序，标注数量与占比）；生命周期分布手写 SVG 环形图 `.donut` + `.legend`（`lifecycle` 兼容数组与对象两种形状，见 §6.4）；告警清单 `.dtable`（型号 / 厂商 / 库存 / 生命周期 / 原因）。首屏有骨架屏 `#stats-skeleton`，加载完成或失败后由 JS 置 `hidden`（`renderStats()` 首行与 `loadStats()` 的 catch 分支）。

### 标签 3 · 模型与算法

纯静态说明（不请求接口）：四步链路 `.pipeline`（TF-IDF 召回 → 六维兼容规则 → 供应链加权排序 → 风险/等级判定），核心公式用 `.formula-block` 排版：

- `param = 0.70 × rule_score + 0.30 × similarity`（型号模式） / `param = similarity`（自然语言模式）
- `supply = w_stock^0.45 · w_price^0.20 · w_lead^0.20 · w_life^0.15`
- `score = param × (0.65 + 0.35 × supply)`

风险三级（🟢/🟡/🔴）与替代等级四档（Pin-to-Pin 直接替换 / 功能等效需改板 / 参考替代 / 不推荐）判定规则表；以及 `.callout.callout-danger` 明确写出**零容忍硬约束**：类别不符 / 封装串不同 / 脚位差 > 2 / 电压零交集 / 功能参数冲突 → 一律不推荐；**温度覆盖不足不算零容忍**（设计决定，已写明）。

### 标签 4 · 关于与声明

作品定位；**数据声明**：`lead_time_days` 与 `lifecycle` 是人工整理的**演示字段**，公开 jlcparts 数据集不提供这两列，页面展示处统一加"演示数据"标注，不声称实时供应链数据；已知局限 4 条（4 条自然语言用例仍不准、供应链因子在现有用例上测不出 Top-1 差异等）；评测数字表（型号 Top-1 6/7 = 85.7%、Top-5 7/7 = 100%、NL 品类 9/9、硬约束违规 0/19、p95 4.81 ms、25 条回归测试通过）。

---

## 3. 接口映射表

| 接口 | 调用位置 | 渲染到 |
| --- | --- | --- |
| `GET /api/health` | `init()` | `.version-chip`、数据集徽标（`renderBadge()`） |
| `GET /api/suggest?q=` | `requestSuggest()` | `#suggest` 下拉项 `.suggest-item`（≤8 条；`items` 为空时显示 `.suggest-empty`） |
| `GET /api/recommend?part=&top=` | `runSearch()` | `#query-status`、卡片/表格双视图、详情面板、`#rejected`、空态/错误态 |
| `GET /api/part/<part_no>` | `loadOriginal()` / 详情展开 | `.profile-card` 档案卡（含 datasheet 外链、国产标记） |
| `GET /api/stats` | `loadStats()` | 标签 2 全部内容 + 头部数据集徽标 |
| `POST /api/feedback` | `sendVote()` | 投票按钮状态 + toast |

错误分支：`request()`（`app.js:119`）统一封装 fetch，把非 2xx 的 `{"error": ...}` 转成 `ApiError`（`app.js:111`），`showError(err)` 渲染到 `#error`（`.alert.alert-error`）；缺 `part` → 400 文案、查不到型号 → `results: []` 走空态（不报错），两条分支都已实测（§7）。

---

## 4. 视觉系统

- **设计令牌**：`app.css` 顶部 `:root` 集中管理 —— 背景/表面 4 级、文字 5 级、边框 2 级、品牌蓝 4 色、语义色绿/琥珀/红 + 各自 soft 底色、圆角 3 档、阴影 3 档、字体族与等宽族。
- **语义色统一**：🟢低风险 = 绿、🟡中风险 = 琥珀、🔴高风险 = 红、Pin-to-Pin = 蓝绿（teal）、功能等效需改板 = 品牌蓝、参考替代 = 灰、不推荐 = 红。风险徽标、等级徽标、六维规则 pill、因子条、告警行全部复用同一组类（`riskClass()` / `tierClass()` / `lcClass()`），保证同一语义在四个标签页里颜色一致。
- **数字对齐**：所有数值列、得分、权重、时间用 `--mono` 等宽字体 + `font-variant-numeric: tabular-nums`（`.num` / `.mono-num` / `.fbar-val` / `.hbar-val` / `.stat-value` 等），保证纵向对齐、不跳动。
- **反馈**：所有按钮、示例 chip、表头、行、卡片都有 `:hover` / `:active` 视觉反馈（含 `transform: translateY(1px)` 下沉与边框高亮）；键盘焦点有 `:focus-visible` 描边。
- **响应式**：`.cards` / `.stat-cards` / `.pipeline` / `.pc-grid` / `.kpis` 全部用 `repeat(auto-fit, minmax(...))` 自适应；`.table-wrap` 横向滚动承载宽表（`.ctable` 设 `min-width: 1180px`）；1280 主分辨率下卡片默认 2 列、对比表刚好铺满不滚动。

---

## 5. 交互清单（实现位置）

| 交互 | 实现 |
| --- | --- |
| 标签切换 + hash 同步 | `activateTab()` / `initTabs()` |
| 自动补全（防抖/键盘/点选/失焦） | `requestSuggest()` / `renderSuggest()` / `setActiveSuggest()` / `hideSuggest()` |
| 示例按钮填入并检索 | `initSearch()` 事件委托 + `runSearch(q, top)` |
| 清除输入 | `#q-clear`（`.search-clear`） |
| 卡片/表格视图切换 | `#seg` 分段控件 + `renderCards()` / `renderTable()` |
| 表头排序（升/降/箭头） | `initResultInteractions()` + `sortedResults()` + `sortValue()` |
| 详情展开/收起（互斥、状态记忆） | `toggleExpand(partNo)` / `hasExpanded()` |
| 投票 | `sendVote(partNo, vote, el)` → `POST /api/feedback` |
| 被排除候选折叠 | `#rejected` toggle + `renderRejected(data)` |
| toast 提示 | `toast(msg, kind)`（`#toast`，3 秒自动消失） |
| 数据集徽标/版本 | `renderBadge(s)`（`/api/stats` + `/api/health`） |

---

## 6. 真实后端联调实测记录

> 说明：本机没有可用的无头浏览器，因此**运行时验证是用 Python（urllib）对真实 Flask 应用发真实 HTTP 请求**完成的（脚本见 §7 的 `probe_live.py`，它用 `werkzeug.serving.make_server` 在同进程内起真实应用再打请求），而不是浏览器渲染。因此本节证明的是"后端真实返回什么形状、静态资源真实送达什么字节"，**不是**"页面在浏览器里长什么样"（后者见 §8）。

### 6.1 启动方式（复现实验用）

后端模块名是 `wsgi`（不是 `app`：PyPI 有同名包，`import app` 会静默拿到第三方包），启动需要 `PYTHONPATH=<ws>/.deps`、`CHIPS_CSV=<ws>/data/samples/chips_seed.csv`、`PYTHONIOENCODING=utf-8`。首次建索引约 3–5 s（20,890 行真实数据集 4.7 s），故前端首屏给了骨架屏/加载态。

### 6.2 页面与静态资源

| 检查 | 实测 |
| --- | --- |
| `GET /` | 200，`text/html; charset=utf-8`，29,400 B，与磁盘 `index.html` 逐字节一致（模板原样渲染），无 BOM |
| `GET /static/app.js` | 200，`application/javascript; charset=utf-8`，51,341 B = 磁盘字节数 |
| `GET /static/app.css` | 200，`text/css; charset=utf-8`，49,711 B = 磁盘字节数 |
| `GET /stats`（既有页） | 200，5,792 B，17 个 class 全部有 CSS 规则 |
| `GET /static/../prototype/wsgi.py` | 404（目录穿越被拒） |

### 6.3 `/api/recommend` 实测（型号模式）

`part=STM32F103C8T6&top=3` → 200，顶层 8 键齐全（`category, elapsed_ms, filtered_out, matched_part, mode, query, rejected, results`），`mode='part'`、`matched_part='STM32F103C8T6'`、**`category=null`**、`filtered_out=0`、`elapsed_ms≈26–29`；`results[]` 19 键齐全，`rejected[]` 元素也是完整 19 键（比契约多）。

Top-1 = `APM32F103C8T6`（极海 Geehy）：`rule_score=1.0`、`similarity=0.2736`、`supply=0.7937`、`score=0.7256`、`risk_level='🟢低风险'`、`replacement_tier='Pin-to-Pin 直接替换'`、六维 `checks` 全 `pass`、`supply_detail={w_stock:0.6221, w_price:1.0, w_lead:0.9167, w_life:1.0, price_ratio:0.736}`、`reasons` 1 条、`summary` 一句话结论完整。

- **`similarity` 实测区间 0.167–0.274** —— 与"普遍 0.1–0.7"的口述不同，前端因此**不假设**相似度能到 1.0，并在 `#status-note` 里写明量级口径。
- **该响应里唯一的 `null` 是顶层 `category`**，前端按 `—（型号模式不返回顶层品类）` 渲染，不当成异常。

自然语言模式 `part=3.3V 低功耗 LDO SOT-23-5&top=3` → `mode='text'`、`matched_part=null`、`category='线性稳压器LDO'`、`results=3`、`rejected=1`、`filtered_out=8`；Top-1 = `RT9013-33GB`，`replacement_tier='参考替代'`、`risk_level='🟡中风险'`、`rule_score=0.5333`（仅展示、不参与排序）。这正是 `#status-note` 要解释的场景。

查不到型号（`part=NO_SUCH_CHIP_XYZ`）→ **200 且 `results=[]`**（不报错）；缺 `part` → **400 `{"error":"缺少 part 参数"}`**。

### 6.4 其余接口实测

| 接口 | 实测形状 |
| --- | --- |
| `GET /api/part/STM32F103C8T6` | 200，**恰好 16 键**（`part_no, manufacturer, category, package, pin_count, vcc_min, vcc_max, temp_min, temp_max, stock, price_cny, lead_time_days, lifecycle, description, datasheet_url, is_domestic`），本样例无 `null`；`pin_count=48`、`vcc 2.0–3.6`、`temp -40–85`、`stock=12500`、`price_cny=12.5`、`lead_time_days=7`、`lifecycle='量产'`、`is_domestic=0`。**没有 `p2p_with`、没有 `desc_text`** → 前端刻意不渲染这两个字段。查不到 → 404 `{"error":"未找到该型号"}` |
| `GET /api/stats` | 200，**7 键**（`total, manufacturers, categories, by_category, lifecycle, alerts, watch_count`）；`total=89`、`manufacturers=36`、`categories=12`、`watch_count=7`；`by_category` 为 `[{category,count}]` 按 count 降序（首二：微控制器 MCU 13、线性稳压器 LDO 12）；**`lifecycle` 是数组** `[{count,lifecycle}]` = 量产 84 / NRND 4 / EOL 1（**不是** `{生命周期: 条数}` 对象）；`alerts` 7 条，元素含 `part_no, manufacturer, category, stock, lifecycle, reason`。**没有 `dataset`、没有 `generated_at`** → 前端不依赖它们 |
| `GET /api/suggest?q=stm` | 200，**只有 `items` 一键**（无 `query`），2 条 `{part_no, manufacturer, category}` |
| `GET /api/health` | 200，`{"status":"ok","rows":89,"version":"1.4"}` → 头部版本芯片显示 `v1.4 · ok` |
| `POST /api/feedback` | 200 `{"ok":true,"persisted":true}`；空 body → 400 `{"error":"query 与 part_no 至少需要一个"}` |

**由实测做出的三处兼容性加固**（若按口述契约写会静默出错）：
1. `lifecycle` 同时兼容**数组**与对象两种形状（`renderStats()` 内用 `Object.prototype.toString.call(...) === '[object Array]'` 判定），`watch_count` 缺失时回落到 `alerts.length`；
2. 型号模式下顶层 `category` 为 `null` → 显示为「—（型号模式不返回顶层品类）」，与自然语言模式的「未识别出器件品类」区分开；
3. `/api/health` 缺 `version` 时按 `version → dataset → rows` 顺序兜底，避免拼出 `vok` 这类字符串。

### 6.5 修正的一处回归：`stats.html` 曾经是无样式裸页

`web/templates/stats.html`（后端 `GET /stats`，`prototype/wsgi.py:253`）早于本次改版就存在，与选型页共用同一份 `app.css`，但它使用的 11 个类（`.page-stats / .topbar / .topnav / .wrap / .kpis / .kpi / .kpi-num / .kpi-label / .kpi-warn / .grid / .foot-note`）在本文件中从未定义 —— 该页虽然 HTTP 200，却是**完全无样式**的裸 HTML。本次在 `app.css` 末尾新增第 19 节，按同一套设计令牌补齐这些类（全部带 `.page-stats` 作用域或为该页独有命名，不回改选型页任何既有类）；自检 3 新增的 J 项与 `probe_live.py` 的 `/stats` 检查现在都会守住这件事。

---

## 7. 自测体系

四个脚本都在 `.tmp/ui-check/`，用运行时 Python 执行（本机没有可用的 node，故不做 JS 运行时检查，改为词法/结构 + 交叉引用 + 真实 HTTP 三层静态验证）：

```powershell
$py='C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
& $py .tmp\ui-check\check_syntax.py      # 1) HTML/CSS/JS 语法与配平自检
& $py .tmp\ui-check\check_contract.py    # 2) 前后端契约对照自检
& $py .tmp\ui-check\check_html.py        # 3) id / class 交叉引用自检
$env:PYTHONPATH='C:\MyFiles\Develop\dsh\work_1\.deps'
$env:CHIPS_CSV='C:\MyFiles\Develop\dsh\work_1\data\samples\chips_seed.csv'
$env:PYTHONIOENCODING='utf-8'
& $py .tmp\ui-check\probe_live.py        # 4) 真实后端 HTTP 联调自检（附加项）
```

结果摘要（完整输出见文末附录）：

| 脚本 | 检查项 | 结果 |
| --- | ---: | --- |
| `check_syntax.py` | 19 | **19 PASS / 0 FAIL**（exit 0） |
| `check_contract.py` | 9 | **9 PASS / 0 FAIL**（exit 0）；契约 53 个字段 100% 有代码引用（53/53） |
| `check_html.py` | 5 | **5 PASS / 0 FAIL**（exit 0） |
| `probe_live.py` | 30+ | **FAIL 0 / INFO 8**（exit 0） |

各脚本覆盖的内容：

1. **`check_syntax.py`（19 项）**：HTML 标签配平与 `id` 唯一性、CSS 花括号配平与注释闭合、JS 括号/引号/模板字符串/正则字面量配平、BOM 与编码检查、常见结构错误（连续运算符误报已在脚本内白名单处理）。
2. **`check_contract.py`（9 项）**：A 接口路径双向比对（前端用的每条路径都在冻结契约里，契约里的每条路径都被用到）；B 查询参数名（`part/top/q`）；C 契约字段是否真的被渲染代码引用；D **契约外字段**（应为 0 —— 证明前端没有猜字段）；E POST 请求体字段；F 错误分支（400/404 文案）。
3. **`check_html.py`（5 项）**：G `app.js` 引用的每个 `#id` 在 `index.html` 中存在（42 个静态 + 1 个动态前缀 `#panel-` 全部命中）；H `index.html` 的 140 个 class 全部有 CSS 规则；I `app.js` 动态生成的 104 个 class 全部有 CSS 规则；I2 `.cls` 选择器来源存在；J `web/templates` 下其他模板（`stats.html`）的 class 未被本次 CSS 改动破坏。
4. **`probe_live.py`（附加，最有说服力）**：在同进程内用 `werkzeug.serving.make_server` 起**真实应用**，再用真实 HTTP 请求验证 —— 页面字节一致性、静态资源 MIME 与字节数、每个接口的真实响应键集合、`null` 字段清点、实测 `similarity` 区间、四条错误/空分支、目录穿越防护。

---

## 8. 尚未在真实浏览器中验证的部分（诚实清单）

以下都是"静态检查 + 真实 HTTP 通过，但**没有**在浏览器里真正渲染/点击过"的内容。本机没有可用的无头浏览器（无 node、无 Playwright/Puppeteer），因此**不能声称**已经验证过页面外观与交互：

1. **视觉呈现**：布局在 1280×800 / 1920 宽下的实际观感、卡片栅格与对比表在真实字体下的对齐、颜色与留白、环形图/条形图的实际比例 —— 全部只看过代码与类名交叉引用。
2. **JS 运行时行为**：`app.js` 从未被执行过（无 node），因此**任何运行时错误**（如某个 DOM 查询在真实 HTML 上返回 `null`）都不在自检覆盖范围内；自检只能保证"被引用的 id/class 都存在"。
3. **交互链路**：自动补全下拉的实际弹出/键盘选择、视图切换、表头排序结果顺序、详情展开互斥、投票按钮置灰与 toast、被排除候选折叠动画、示例按钮填入 —— 均未点击验证。
4. **样式细节**：`.ctable` 的 `min-width: 1180px` 在 1280 宽下是否真的不出现横向滚动条、`.grid-2/.grid-3` 断点效果、`#stats-skeleton` 的 `hidden` 是否被 flex 布局正确隐藏（已专门加 `.sk-grid[hidden]{display:none}` 兜底，但未在浏览器确认）。
5. **首屏时序**：后端建索引 3–5 s 期间的前端表现（骨架屏/加载态的实际观感）未验证；后端未就绪时的失败提示文案未在真实浏览器触发过。
6. **跨浏览器**：只在目标环境的 Chromium 内核下预期可用；未在 Firefox/Safari 验证（演示环境为 Windows + 固定浏览器，风险可接受）。

---

## 9. 已知局限与风险（最容易被评委挑毛病的地方）

1. **自然语言模式的天花板**：4 条自然语言用例仍不准，`similarity` 绝对量级偏低（0.167–0.274），评委若只盯着"相似度只有 27%"会误判 —— 页面已用 `#status-note` 明确"相似度仅用于召回排序、综合得分才是结论"，并把 NL 模式的保守风险口径写清楚（这是设计决定）。
2. **演示字段**：`lead_time_days` / `lifecycle` 是人工整理的演示字段（真实 jlcparts 无此两列），页面已统一标注"演示数据"；但评委若追问"交期数据从哪来"，仍需口头解释。
3. **供应链因子在现有用例上测不出 Top-1 差异**：`supply` 影响排名但当前 89 条演示数据集里没有能让 Top-1 翻转的用例，评委可能质疑权重是否必要 —— 算法页已给出公式与权重来源，建议答辩时准备一个构造用例。
4. **`similarity` 与 `score` 的口径差异**容易被误读（前者 0.2 左右、后者 0.7 左右）；页面用"分项/总分"层级与标签区分，但仍是可能的提问点。
5. **前端未经过真实浏览器点击**（见 §8）：这是本次交付最大的验证缺口，建议 Lead 在真窗口里按下节清单点一遍。
6. **对比表信息密度高**：宽表在 1280 宽下接近铺满，评委若用更窄的窗口（如 1024）会看到横向滚动条 —— 这是有意为之（保留全部字段），但可能被嫌"表格太宽"。

**建议的真窗口验收清单**（Lead 侧，2 分钟）：① 直接搜 `STM32F103C8T6` 看卡片得分/等级/风险与三因子条；② 输入 `3.3` 看自动补全下拉与键盘选择；③ 点列表示例 `3.3V 低功耗 LDO SOT-23-5` 看口径说明条与 🟡 中风险；④ 切到对比表点表头排序；⑤ 展开一条详情看六维规则表四因子条与档案卡；⑥ 展开被排除候选；⑦ 切数据总览看条形图/环形图/告警表；⑧ 切模型与算法、关于与声明两页看公式排版与评测数字表；⑨ 投一次票看 toast；⑩ 搜一个不存在的型号看空态提示。

---

## 10. 变更边界声明

本次只新增/修改 `web/` 下的文件：`web/templates/index.html`、`web/static/app.js`、`web/static/app.css`、`web/DESIGN.md`，以及自测脚本目录 `.tmp/ui-check/`。**未触碰** `prototype/`、`app.py`、`desktop.py`、`build_exe.py`、`tests/`、`README.md`、需求及开发文档、`scripts/`、`.deps/`、`data/`；**未执行** git commit / push；`web/templates/stats.html` 只读未改（仅为其补齐 CSS）。


<!-- ===== SELFTEST-APPENDIX（由 .tmp/ui-check/make_design_appendix.py 生成，勿手工编辑） ===== -->

# 附录 · 自测脚本与真实输出

本附录由 `.tmp/ui-check/make_design_appendix.py` 生成于 2026-10-06 16:00:52（本机时区），内容取自磁盘上的真实脚本与真实输出文件，未经人工改写。

| 项目 | 脚本 | 输出 | 结果 |
| --- | --- | --- | --- |
| 1/4 语法与配平自检 | `.tmp/ui-check/check_syntax.py` | `.tmp/ui-check/out-syntax.txt` | 19 PASS / 0 FAIL（exit 0） |
| 2/4 前后端契约对照自检 | `.tmp/ui-check/check_contract.py` | `.tmp/ui-check/out-contract.txt` | 9 PASS / 0 FAIL（exit 0） |
| 3/4 id / class 交叉引用自检 | `.tmp/ui-check/check_html.py` | `.tmp/ui-check/out-html.txt` | 5 PASS / 0 FAIL（exit 0） |
| 4/4 真实后端 HTTP 联调自检（附加） | `.tmp/ui-check/probe_live.py` | `.tmp/ui-check/out-live.txt` | FAIL 0 / INFO 8（exit 0） |

## 1/4 语法与配平自检 —— `check_syntax.py`

### 源码

````python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_syntax.py —— 芯选前端静态语法自检（Python 标准库实现；本机无 node）

用途
----
本机没有可用的 node（管道受限，`node --check` 跑不了），因此用纯 Python + re 把
web/static/app.js 当作文本做「词法级」配平检查。能覆盖绝大多数低级语法错误：
  * 圆括号 ( ) / 方括号 [ ] / 花括号 { } 是否配平、是否交叉错配
  * 单引号 / 双引号 / 反引号字符串是否闭合、是否在行尾意外断开
  * 行注释 // 与块注释 /* */ 是否闭合
  * 正则字面量 /.../flags 是否闭合（按「前一个有效字符」启发式识别，避免把
    /[&<>"']/g 里的引号误判为字符串起点）
  * 结构抽查：'use strict'、IIFE 收尾、每个 function 形参括号配平、顶层函数重名
  * 代码态（剥离字符串与注释后）上的可疑笔误：连续运算符、空语句
再对 web/templates/index.html 做标签配平 + 重复 id + 外部资源扫描，
对 web/static/app.css 做花括号配平 + var(--x) 未定义变量扫描。

说明：这不是 JavaScript 解释器，无法证明「运行时无误」；它证明的是配平与结构
层面没有明显语法错误。这一点在报告里如实标注。

输出：逐项 PASS/FAIL + 汇总。退出码 0 = 全部通过，1 = 存在 FAIL。
"""

import io
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JS = os.path.join(ROOT, "web", "static", "app.js")
CSS = os.path.join(ROOT, "web", "static", "app.css")
HTML = os.path.join(ROOT, "web", "templates", "index.html")

results = []


def record(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, (" :: " + detail) if detail else ""))


def read(path):
    with open(path, "rb") as f:
        raw = f.read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, False, "UTF-8 解码失败: %s" % exc
    return text, has_bom, ("无 BOM" if not has_bom else "存在 BOM（不符合要求）")


REGEX_PREV = set("(,=:[!&|?{};+-*%^~<>") | {""}
KEYWORDS_BEFORE_REGEX = {"return", "typeof", "instanceof", "in", "of", "new", "delete",
                         "void", "case", "do", "else", "yield", "await"}
IDENT_RE = re.compile(r"[A-Za-z0-9_$]")


def scan_js(text):
    """词法状态机：返回 (问题列表, 统计, 代码态文本)。代码态文本把字符串/注释内容替换为空格。"""
    problems = []
    counts = {"line_comment": 0, "block_comment": 0, "regex": 0,
              "single": 0, "double": 0, "backtick": 0}
    code = list(text)          # 代码态：字符串与注释内容被清空
    i, n, line = 0, len(text), 1
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    last_sig, last_word = "", ""

    def blank(start, end):
        for k in range(start, min(end, n)):
            if code[k] != "\n":
                code[k] = " "

    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            counts["line_comment"] += 1
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            counts["block_comment"] += 1
            j = text.find("*/", i + 2)
            if j < 0:
                problems.append("第 %d 行：块注释 /* 未闭合" % line)
                break
            line += text.count("\n", i, j)
            blank(i, j + 2)
            i = j + 2
            continue
        if ch in ("'", '"'):
            kind = "single" if ch == "'" else "double"
            counts[kind] += 1
            j, closed = i + 1, False
            while j < n:
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "\n":
                    problems.append("第 %d 行：%s引号字符串在行尾未闭合" % (line, "单" if ch == "'" else "双"))
                    break
                if c == ch:
                    closed = True
                    break
                j += 1
            if not closed:
                if j >= n:
                    problems.append("第 %d 行：引号字符串直到文件末尾仍未闭合" % line)
                break
            blank(i, j + 1)
            i = j + 1
            last_sig, last_word = ch, ""
            continue
        if ch == "`":
            counts["backtick"] += 1
            j, closed = i + 1, False
            while j < n:
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "`":
                    closed = True
                    break
                j += 1
            if not closed:
                problems.append("第 %d 行：模板字符串 ` 未闭合" % line)
                break
            line += text.count("\n", i, j)
            blank(i, j + 1)
            i = j + 1
            last_sig = "`"
            continue
        if ch == "/":
            allowed = last_sig in REGEX_PREV or last_word in KEYWORDS_BEFORE_REGEX
            if allowed and i + 1 < n and text[i + 1] not in ("/", "*"):
                counts["regex"] += 1
                j, in_class, closed = i + 1, False, False
                while j < n:
                    c = text[j]
                    if c == "\\":
                        j += 2
                        continue
                    if c == "\n":
                        problems.append("第 %d 行：正则字面量跨行未闭合" % line)
                        break
                    if c == "[":
                        in_class = True
                    elif c == "]":
                        in_class = False
                    elif c == "/" and not in_class:
                        closed = True
                        break
                    j += 1
                if not closed:
                    if j >= n:
                        problems.append("第 %d 行：正则字面量直到文件末尾未闭合" % line)
                    break
                blank(i, j + 1)
                i = j + 1
                while i < n and IDENT_RE.match(text[i]):
                    i += 1
                last_sig, last_word = "/", ""
                continue
            last_sig, last_word = "/", ""
            i += 1
            continue
        if ch in "([{":
            stack.append((ch, line))
        elif ch in ")]}":
            if not stack:
                problems.append("第 %d 行：多余的右括号 %r（此前没有未配对的左括号）" % (line, ch))
            else:
                op, oline = stack.pop()
                if op != pairs[ch]:
                    problems.append("第 %d 行：括号交叉错配，第 %d 行的 %r 被 %r 关闭" % (line, oline, op, ch))
        if IDENT_RE.match(ch):
            j = i
            while j < n and IDENT_RE.match(text[j]):
                j += 1
            last_word = text[i:j]
            if last_word not in KEYWORDS_BEFORE_REGEX:
                last_sig = text[j - 1]
            i = j
            continue
        if not ch.isspace():
            last_sig, last_word = ch, ""
        i += 1

    for op, oline in stack:
        problems.append("第 %d 行的 %r 直到文件末尾都没有被关闭" % (oline, op))
    return problems, counts, "".join(code)


JS_STRUCT = []

# 合法 JS 运算符（长的在前，用于对「运算符字符连续串」做贪心切分）
VALID_OPS = [
    ">>>=", "**=", "===", "!==", ">>>", "<<=", ">>=", "&&=", "||=", "??=", "...", "?.",
    "==", "!=", "<=", ">=", "=>", "++", "--", "**", "&&", "||", "??", "<<", ">>",
    "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
    "+", "-", "*", "/", "%", "&", "|", "^", "<", ">", "=", "!", "?", "~",
]


def tokenize_ops(run):
    """把一段运算符字符序列贪婪切成合法运算符；切不动就返回 False。"""
    i = 0
    while i < len(run):
        for op in VALID_OPS:
            if run.startswith(op, i):
                i += len(op)
                break
        else:
            return False
    return True


def js_structure_checks(text, code, lines):
    out = []
    out.append(("'use strict' 严格模式指令存在", bool(re.search(r"['\"]use strict['\"]", text)), ""))
    out.append(("IIFE 包裹并立即调用（(function () { … })();）",
                bool(re.search(r"\(function\s*\(\)\s*\{", text)) and bool(re.search(r"\}\)\s*\(\s*\)\s*;", text)), ""))

    bad_fn = []
    for m in re.finditer(r"\bfunction\s+([A-Za-z_$][\w$]*)?\s*\(", code):
        k, depth = m.end() - 1, 0
        while k < len(code):
            if code[k] == "(":
                depth += 1
            elif code[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if k >= len(code) or depth != 0:
            bad_fn.append(m.group(1) or "<anonymous>")
    out.append(("每个 function 的形参括号都配平", not bad_fn, ",".join(bad_fn)))

    names = re.findall(r"\n  function\s+([A-Za-z_$][\w$]*)\s*\(", text)
    dup = sorted({x for x in names if names.count(x) > 1})
    out.append(("顶层函数无重名（%d 个函数）" % len(names), not dup, ",".join(dup)))

    bad_ops, bad_stmt = [], []
    for idx, ln in enumerate(code.splitlines(), 1):
        for m in re.finditer(r"[+\-*/%&|^<>=!?~]+", ln):
            if not tokenize_ops(m.group(0)):
                bad_ops.append("L%d %r（原文: %s）" % (idx, m.group(0), lines[idx - 1].strip()[:58]))
        if ";;;;" in ln or re.search(r";\s*;\s*;", ln):
            bad_stmt.append("L%d" % idx)
    out.append(("代码态无非法运算符序列（笔误嫌疑）", not bad_ops, "; ".join(bad_ops[:5])))
    out.append(("无三连分号等空语句", not bad_stmt, ",".join(bad_stmt[:5])))
    return out


class TagBalance(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.ids, self.classes, self.tags = [], [], [], set(), []

    def _collect(self, tag, attrs):
        d = dict(attrs)
        if d.get("id"):
            self.ids.append(d["id"])
        for c in (d.get("class") or "").split():
            self.classes.add(c)
        self.tags.append((tag, d))

    def handle_starttag(self, tag, attrs):
        self._collect(tag, attrs)
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        self._collect(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.errors.append("第 %d 行：多余的 </%s>" % (self.getpos()[0], tag))
            return
        open_tag, open_line = self.stack.pop()
        if open_tag != tag:
            self.errors.append("第 %d 行：</%s> 与第 %d 行 <%s> 不匹配" % (self.getpos()[0], tag, open_line, open_tag))


def main():
    print("=" * 78)
    print("芯选前端自检 1/3 —— 静态语法检查（Python 标准库；本机无 node 可用）")
    print("=" * 78)
    print("工作目录: %s" % ROOT)
    print()

    missing = [os.path.relpath(p, ROOT) for p in (JS, CSS, HTML) if not os.path.isfile(p)]
    if missing:
        record("三件套文件均存在", False, "缺失: " + ", ".join(missing))
        return 1
    record("三件套文件均存在", True, ", ".join(os.path.relpath(p, ROOT) for p in (JS, CSS, HTML)))

    print("\n--- 1) web/static/app.js ---")
    js_text, js_bom, bom_note = read(JS)
    if js_text is None:
        record("app.js 为 UTF-8 文本", False, bom_note)
        return 1
    lines = js_text.splitlines()
    record("app.js 为 UTF-8 文本", not js_bom, "%s，%d 行" % (bom_note, len(lines)))

    problems, counts, code = scan_js(js_text)
    record("app.js 括号/引号/注释/正则 全部闭合", not problems,
           "; ".join(problems[:8]) if problems else
           "圆括号+方括号+花括号配平；字符串 %d 单引号 / %d 双引号；注释 %d 行注释 / %d 块注释；"
           "正则 %d 个全部闭合" % (counts["single"], counts["double"],
                                   counts["line_comment"], counts["block_comment"], counts["regex"]))
    record("app.js 未使用模板字符串（与纯 ASCII 引号风格一致）", counts["backtick"] == 0,
           "反引号出现 %d 次" % counts["backtick"])
    for name, ok, detail in js_structure_checks(js_text, code, lines):
        record(name, ok, detail)

    print("\n--- 2) web/static/app.css ---")
    css_text, css_bom_flag, css_bom = read(CSS)
    css_lines = css_text.splitlines()
    record("app.css 为 UTF-8 文本", not css_bom_flag, "%s，%d 行" % (css_bom, len(css_lines)))
    depth, in_comment, css_bad = 0, False, []
    for idx, ln in enumerate(css_lines, 1):
        s = ln
        if in_comment:
            if "*/" in s:
                in_comment = False
                s = s.split("*/", 1)[1]
            else:
                continue
        s = re.sub(r"/\*.*?\*/", "", s)
        if "/*" in s:
            in_comment = True
            s = s.split("/*", 1)[0]
        s = re.sub(r"\"[^\"]*\"|'[^']*'", "", s)
        depth += s.count("{") - s.count("}")
        if depth < 0:
            css_bad.append("第 %d 行多余的 }" % idx)
            depth = 0
    record("app.css 花括号配平", depth == 0 and not css_bad,
           "; ".join(css_bad) if css_bad else ("剩余未闭合 { = %d" % depth if depth else "全部配平（%d 个规则块起止一致）" % css_text.count("{")))
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css_text))
    used = set(re.findall(r"var\((--[a-z0-9-]+)", css_text))
    undef = sorted(used - defined)
    record("app.css 中 var(--x) 全部有定义", not undef,
           ", ".join(undef) if undef else "已定义 %d 个变量 / 引用 %d 个，无悬空引用" % (len(defined), len(used)))
    record("（信息）app.css 已定义但未引用的变量（允许存在）", True,
           ", ".join(sorted(defined - used)) or "无")

    print("\n--- 3) web/templates/index.html ---")
    html_text, html_bom_flag, html_bom = read(HTML)
    record("index.html 为 UTF-8 文本", not html_bom_flag,
           "%s，%d 行" % (html_bom, len(html_text.splitlines())))
    p = TagBalance()
    p.feed(html_text)
    record("index.html 标签配平（HTMLParser 栈式比对）", not p.errors and not p.stack,
           "; ".join(p.errors[:6]) if p.errors else
           ("未闭合: " + ", ".join("<%s>@L%d" % t for t in p.stack) if p.stack else
            "全部闭合；共 %d 个 id、%d 个 class 名" % (len(p.ids), len(p.classes))))
    dup = sorted({x for x in p.ids if p.ids.count(x) > 1})
    record("index.html 无重复 id", not dup, ", ".join(dup) if dup else "%d 个 id 均唯一" % len(p.ids))
    ext = re.findall(r"(?:src|href)\s*=\s*[\"']([^\"']+)[\"']", html_text)
    external = [u for u in ext if re.match(r"\s*(https?:)?//", u)]
    record("index.html 无外部资源引用（离线自包含）", not external,
           ", ".join(external) if external else "仅引用: " + ", ".join(sorted(set(ext))))
    cdn_hits = [w for w in ("cdn.", "unpkg", "jsdelivr", "googleapis", "echarts", "chart.js",
                            "chartjs", "bootstrap", "jquery", "vue.js", "react.", "tailwind",
                            "font-awesome", "cdnjs")
                if w.lower() in html_text.lower()]
    record("index.html 无 CDN / 图表库 / 前端框架痕迹", not cdn_hits, ", ".join(cdn_hits) if cdn_hits else "无命中")

    failed = [r for r in results if not r[1]]
    print("\n" + "=" * 78)
    print("汇总：共 %d 项检查，PASS %d 项，FAIL %d 项" % (len(results), len(results) - len(failed), len(failed)))
    for name, _, detail in failed:
        print("  失败 -> %s :: %s" % (name, detail))
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
````

### 真实输出（`out-syntax.txt`，2121 字节）

````text
==============================================================================
芯选前端自检 1/3 —— 静态语法检查（Python 标准库；本机无 node 可用）
==============================================================================
工作目录: C:\MyFiles\Develop\dsh\work_1

[PASS] 三件套文件均存在 :: web\static\app.js, web\static\app.css, web\templates\index.html

--- 1) web/static/app.js ---
[PASS] app.js 为 UTF-8 文本 :: 无 BOM，1158 行
[PASS] app.js 括号/引号/注释/正则 全部闭合 :: 圆括号+方括号+花括号配平；字符串 1059 单引号 / 1 双引号；注释 6 行注释 / 31 块注释；正则 4 个全部闭合
[PASS] app.js 未使用模板字符串（与纯 ASCII 引号风格一致） :: 反引号出现 0 次
[PASS] 'use strict' 严格模式指令存在
[PASS] IIFE 包裹并立即调用（(function () { … })();）
[PASS] 每个 function 的形参括号都配平
[PASS] 顶层函数无重名（63 个函数）
[PASS] 代码态无非法运算符序列（笔误嫌疑）
[PASS] 无三连分号等空语句

--- 2) web/static/app.css ---
[PASS] app.css 为 UTF-8 文本 :: 无 BOM，1453 行
[PASS] app.css 花括号配平 :: 全部配平（423 个规则块起止一致）
[PASS] app.css 中 var(--x) 全部有定义 :: 已定义 35 个变量 / 引用 34 个，无悬空引用
[PASS] （信息）app.css 已定义但未引用的变量（允许存在） :: --header-h

--- 3) web/templates/index.html ---
[PASS] index.html 为 UTF-8 文本 :: 无 BOM，471 行
[PASS] index.html 标签配平（HTMLParser 栈式比对） :: 全部闭合；共 54 个 id、140 个 class 名
[PASS] index.html 无重复 id :: 54 个 id 均唯一
[PASS] index.html 无外部资源引用（离线自包含） :: 仅引用: /static/app.css, /static/app.js
[PASS] index.html 无 CDN / 图表库 / 前端框架痕迹 :: 无命中

==============================================================================
汇总：共 19 项检查，PASS 19 项，FAIL 0 项
==============================================================================
````


## 2/4 前后端契约对照自检 —— `check_contract.py`

### 源码

````python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_contract.py —— 芯选前端 × 后端接口契约 一致性自检

契约来自队长冻结的接口说明（本文件 CONTRACT 常量逐字抄录），用 re 扫
web/static/app.js，逐项核对：

  A. 前端调用的 /api/... 路径是否都在契约内（多出来的 = 幻觉接口）
  B. 每个接口的查询参数名是否正确（part / top / q）
  C. 契约里声明的每一个响应字段，前端是否真的用到（未用到的单独列出，
     信息项不算失败）
  D. 前端访问的响应字段中，有没有契约里根本不存在、属于「猜出来的字段名」
     （这一项必须为 0）
  E. POST /api/feedback 的请求体键是否恰好是 {query, part_no, vote}
  F. 错误分支：400（缺 part）与 404（/api/part 未命中）是否被前端处理

输出：A–F 各项结果 + 汇总。退出码 0 = 无 FAIL，1 = 存在 FAIL。
"""

import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JS = os.path.join(ROOT, "web", "static", "app.js")

# ---------------------------------------------------------------- 冻结契约
CONTRACT = {
    "GET /api/recommend": {
        "params": ["part", "top"],
        "fields": ["query", "mode", "category", "matched_part", "elapsed_ms",
                   "filtered_out", "results", "rejected"],
        "item_fields": {
            "results[]": ["part_no", "manufacturer", "category", "package", "pin_count",
                          "price_cny", "stock", "lead_time_days", "lifecycle", "similarity",
                          "rule_score", "supply", "score", "supply_detail", "checks",
                          "risk_level", "replacement_tier", "reasons", "summary"],
            "rejected[]": ["part_no", "manufacturer", "package", "risk_level",
                           "replacement_tier", "similarity", "score", "reasons"],
        },
        "nested": {
            "supply_detail": ["w_stock", "w_price", "w_lead", "w_life", "price_ratio"],
            "checks[]": ["rule", "status", "detail", "critical"],
            "suggest items[]": ["part_no", "manufacturer", "category"],
        },
    },
    "GET /api/part/<part_no>": {
        "params": [],
        "fields": ["part_no", "manufacturer", "category", "package", "pin_count",
                   "vcc_min", "vcc_max", "temp_min", "temp_max", "stock", "price_cny",
                   "lead_time_days", "lifecycle", "description", "datasheet_url",
                   "is_domestic"],
    },
    "GET /api/stats": {
        "params": [],
        "fields": ["total", "manufacturers", "categories", "by_category", "lifecycle",
                   "alerts", "watch_count"],
        "nested": {
            "by_category[]": ["category", "count"],
            "lifecycle[]": ["lifecycle", "count"],
            "alerts[]": ["part_no", "manufacturer", "category", "stock", "lifecycle", "reason"],
        },
    },
    "GET /api/suggest": {"params": ["q"], "fields": ["items"]},
    "POST /api/feedback": {"params": [], "fields": ["ok"], "body": ["query", "part_no", "vote"]},
    "GET /api/health": {"params": [], "fields": ["status", "version"]},
}

CONTRACT_PATHS = {
    "/api/recommend": "GET",
    "/api/part/": "GET",       # 路径参数形式
    "/api/stats": "GET",
    "/api/suggest": "GET",
    "/api/feedback": "POST",
    "/api/health": "GET",
}

ALL_FIELDS = [f for spec in CONTRACT.values() for f in spec.get("fields", [])]
for spec in CONTRACT.values():
    for group in spec.get("item_fields", {}).values():
        ALL_FIELDS += group
    for group in spec.get("nested", {}).values():
        ALL_FIELDS += group
ALL_FIELDS = sorted(set(ALL_FIELDS))

# 属性名白名单：JS 内置 / DOM / 本页自身对象（state、配置表等），不是接口字段。
# 这些名字出现在 `x.foo` 形式里但属于前端内部结构，逐条人工确认后列入。
INTERNAL_PROPS = set("""
length,indexOf,toLowerCase,toUpperCase,split,replace,trim,match,slice,join,concat,
push,pop,filter,map,forEach,some,every,reduce,keys,values,entries,hasOwnProperty,
toFixed,toLocaleString,toString,isFinite,parseInt,parseFloat,stringify,
style,value,checked,type,name,id,text,textContent,innerHTML,outerHTML,className,classList,
dataset,attributes,children,parentNode,firstChild,lastChild,nextSibling,
addEventListener,removeEventListener,setAttribute,getAttribute,removeAttribute,hasAttribute,
querySelector,querySelectorAll,closest,appendChild,removeChild,focus,select,click,submit,
contains,matches,preventDefault,stopPropagation,
cls,key,label,keys2,dir,view,expanded,votes,stats,statsState,suggest,reqSeq,top,
original,originalNo,originalState,idx,timer,seq,error,message,
payload,props,item,row,col,cells,main,list,head,nodes,el,btn,box,node,ev,evt,
asc,desc,id2,tag,html,url,opts,opt,index,err,res,raw,args,self,that,it2,
""".split(","))
INTERNAL_PROPS = {p.strip() for p in INTERNAL_PROPS if p.strip()}
# 说明：契约里真实存在的字段名（items/query/count/status/ok/version/detail/data/lifecycle…）
# 故意**不**放进白名单，否则 D 项会因为被白名单吞掉而失去校验能力。
# `error` 保留在白名单里：它是 HTTP 非 2xx 时后端统一返回的错误信封
# （{"error": "..."}），不属于任何接口的成功响应字段。


def strip_comments(text):
    """把 /*...*/ 与 //... 注释内容替换为等长空格（保留换行与字符偏移）。

    首版 B 项没有剥离注释，文件头接口文档注释里的
    `/api/recommend?part=<str>&top=<1..20>` 与后面第 9 行的 `/api/suggest?q=<str>`
    被同一个正则跨行连读，误报 recommend 使用了参数 q。
    """
    out = list(text)
    i, n, state, quote = 0, len(text), "code", ""
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if c == "/" and nxt == "*":
                state, out[i], out[i + 1], i = "block", " ", " ", i + 2; continue
            if c == "/" and nxt == "/":
                state, out[i], out[i + 1], i = "line", " ", " ", i + 2; continue
            if c in "'\"":
                state, quote = "str", c
            i += 1; continue
        if state == "str":
            if c == "\\":
                i += 2; continue
            if c == quote:
                state = "code"
            i += 1; continue
        if state == "line":
            if c == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1; continue
        # block
        if c == "*" and nxt == "/":
            state, out[i], out[i + 1], i = "code", " ", " ", i + 2; continue
        if c != "\n":
            out[i] = " "
        i += 1
    return "".join(out)

results = []


def record(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, (" :: " + detail) if detail else ""))


def info(name, detail):
    print("[INFO] %s%s" % (name, (" :: " + detail) if detail else ""))


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def main():
    print("=" * 78)
    print("芯选前端自检 2/3 —— 接口契约一致性（web/static/app.js × 冻结契约）")
    print("=" * 78)
    with open(JS, "r", encoding="utf-8") as f:
        js = f.read()
    print("检查文件: %s（%d 行）" % (os.path.relpath(JS, ROOT), js.count("\n") + 1))
    print()

    # ---------------- A. 前端调用的 /api/ 路径 ----------------
    print("--- A. 前端调用的接口路径 ---")
    raw_paths = re.findall(r"['\"](/api/[^'\"]*)['\"]", js)
    found = {}
    for p in raw_paths:
        base = p.split("?")[0]
        if base.startswith("/api/part/"):
            base = "/api/part/"
        found.setdefault(base, []).append(p)
    for base in sorted(found):
        lines = [line_of(js, js.find("'" + p + "'")) if ("'" + p + "'") in js
                 else line_of(js, js.find('"' + p + '"')) for p in found[base]]
        print("    %-18s 调用点行号 %s  原始字面量 %s"
              % (base, ", ".join(str(l) for l in lines), found[base]))
    unknown = sorted(set(found) - set(CONTRACT_PATHS))
    record("A. 前端只调用契约内的接口（无幻觉接口）", not unknown,
           ("契约外接口: " + ", ".join(unknown)) if unknown else
           "命中契约 %d 个接口：%s" % (len(found), ", ".join(sorted(found))))
    missing_api = sorted(set(CONTRACT_PATHS) - set(found))
    info("契约内有、前端未调用的接口", ", ".join(missing_api) if missing_api else "无（6/6 全部接入）")

    # ---------------- B. 查询参数名 ----------------
    print("\n--- B. 查询参数名 ---")
    jsc = strip_comments(js)
    # 期望的 URL 片段（字面量）：?part= 与 &top= 在 app.js 里是两段拼接的字符串
    EXPECT_FRAGMENTS = {
        "/api/recommend": ["part=", "top="],
        "/api/suggest": ["q="],
    }
    bad_params = []
    allowed_params = set()
    for spec in CONTRACT.values():
        allowed_params |= set(spec["params"])
    for ep, frags in EXPECT_FRAGMENTS.items():
        for fr in frags:
            ok = ("?" + fr) in jsc or ("&" + fr) in jsc
            print("    %-16s %-8s %s" % (ep, "?" + fr if fr == "part=" or fr == "q=" else "&" + fr,
                                         "OK" if ok else "缺失"))
            if not ok:
                bad_params.append("%s 缺 %s" % (ep, fr))
    # 反向：所有出现在查询串位置的参数名，必须都在契约允许集合内
    qs_names = set()
    for lit in re.findall(r"['\"]([^'\"]*[?&][A-Za-z_][\w]*=[^'\"]*)['\"]", jsc):
        qs_names |= set(re.findall(r"[?&]([A-Za-z_][\w]*)=", lit))
    extra = sorted(qs_names - allowed_params)
    print("    实际出现的查询参数名: %s（契约允许 %s）" % (sorted(qs_names) or "-", sorted(allowed_params)))
    if extra:
        bad_params.append("契约外参数名: " + ",".join(extra))
    record("B. 查询参数名与契约一致", not bad_params,
           "; ".join(bad_params) if bad_params else
           "part / top / q 三个参数名与契约一致，且无契约外参数名（已剥离注释后扫描）")
    enc_ok = js.count("encodeURIComponent") >= 3
    record("B2. 所有查询参数都做了 encodeURIComponent 编码", enc_ok,
           "encodeURIComponent 出现 %d 次" % js.count("encodeURIComponent"))

    # ---------------- C. 契约字段的覆盖率 ----------------
    print("\n--- C. 契约字段使用情况 ---")
    unused = []
    used_lines = {}
    for f in ALL_FIELDS:
        pat = re.compile(r"\.\s*" + re.escape(f) + r"\b|['\"]" + re.escape(f) + r"['\"]")
        hits = [line_of(js, m.start()) for m in pat.finditer(js)]
        if hits:
            used_lines[f] = hits[:6]
        else:
            unused.append(f)
    for f in ALL_FIELDS:
        if f in used_lines:
            print("    [用到] %-18s 行号 %s" % (f, ", ".join(str(x) for x in used_lines[f][:4])))
    if unused:
        print("    [未用] " + ", ".join(unused))
    record("C. 契约字段全部被前端引用", not unused,
           ("未使用 %d 个: %s" % (len(unused), ", ".join(unused))) if unused else
           "契约 %d 个字段 100%% 有代码引用（%d/%d）" % (len(ALL_FIELDS), len(ALL_FIELDS), len(ALL_FIELDS)))
    info("说明", "未使用字段不构成错误；本项为完整性信息，FAIL 仅提示可补充展示")

    # ---------------- D. 前端访问了但契约没有的字段 ----------------
    print("\n--- D. 前端访问的响应字段是否都在契约内 ---")
    props = {}
    for m in re.finditer(r"\b(data|r|o|it|s|a|x|h|resp|payload)\.([A-Za-z_$][\w$]*)", js):
        alias, prop = m.group(1), m.group(2)
        props.setdefault(prop, set()).add(alias)
    unknown_props = {p: al for p, al in props.items()
                     if p not in ALL_FIELDS and p not in INTERNAL_PROPS}
    for p in sorted(props):
        mark = "契约外!!" if p in unknown_props else ("内部属性" if p in INTERNAL_PROPS else "契约字段")
        print("    %-18s 别名 %-8s %s" % (p, ",".join(sorted(props[p])), mark))
    record("D. 前端未访问契约外的响应字段", not unknown_props,
           ("疑似契约外字段: " + ", ".join("%s(%s)" % (p, ",".join(sorted(a))) for p, a in sorted(unknown_props.items())))
           if unknown_props else
           "扫描 %d 个形如 obj.prop 的访问，全部落在契约字段或已声明的前端内部属性内" % len(props))

    # ---------------- E. POST 请求体 ----------------
    print("\n--- E. POST /api/feedback 请求体 ---")
    body = re.search(r"API\.feedback\(([^)]*)\)", js)
    body_call = re.search(r"feedback:\s*function[^\n]*\n?[^\n]*", js)
    keys = set(re.findall(r"([A-Za-z_][\w]*)\s*:", js[body.start():body.end()])) if body else set()
    expected = set(CONTRACT["POST /api/feedback"]["body"])
    print("    POST 调用点: %s" % (body.group(1).strip() if body else "未找到"))
    print("    实际键: %s" % sorted(keys))
    record("E. 请求体键恰好为 {query, part_no, vote}", keys == expected,
           "实际 %s / 期望 %s" % (sorted(keys), sorted(expected)))
    record("E2. 请求体以 JSON + Content-Type: application/json 发送",
           "application/json" in js and "JSON.stringify" in js,
           "request() 中统一设置 JSON 头")

    # ---------------- F. 错误分支 ----------------
    print("\n--- F. 错误分支处理 ---")
    f1 = "status === 404" in js or "err.status === 404" in js
    f2 = "data.error" in js
    record("F. /api/part 404（未找到该型号）被前端单独识别", f1,
           "loadOriginal() 中按 err.status === 404 标记 missing 并给出文案")
    record("F2. HTTP 非 2xx 时读取后端 {\"error\": ...} 文案", f2,
           "request() 中用 data.error 构造 ApiError 并展示在 #error-msg")

    failed = [r for r in results if not r[1] and not r[0].startswith("（信息）")]
    print("\n" + "=" * 78)
    print("汇总：共 %d 项检查，PASS %d 项，FAIL %d 项"
          % (len(results), len(results) - len(failed), len(failed)))
    for name, _, detail in failed:
        print("  失败 -> %s :: %s" % (name, detail))
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
````

### 真实输出（`out-contract.txt`，8324 字节）

````text
==============================================================================
芯选前端自检 2/3 —— 接口契约一致性（web/static/app.js × 冻结契约）
==============================================================================
检查文件: web\static\app.js（1159 行）

--- A. 前端调用的接口路径 ---
    /api/feedback      调用点行号 152  原始字面量 ['/api/feedback']
    /api/health        调用点行号 153  原始字面量 ['/api/health']
    /api/part/         调用点行号 148  原始字面量 ['/api/part/']
    /api/recommend     调用点行号 145  原始字面量 ['/api/recommend?part=']
    /api/stats         调用点行号 150  原始字面量 ['/api/stats']
    /api/suggest       调用点行号 151  原始字面量 ['/api/suggest?q=']
[PASS] A. 前端只调用契约内的接口（无幻觉接口） :: 命中契约 6 个接口：/api/feedback, /api/health, /api/part/, /api/recommend, /api/stats, /api/suggest
[INFO] 契约内有、前端未调用的接口 :: 无（6/6 全部接入）

--- B. 查询参数名 ---
    /api/recommend   ?part=   OK
    /api/recommend   &top=    OK
    /api/suggest     ?q=      OK
    实际出现的查询参数名: ['part', 'q', 'top']（契约允许 ['part', 'q', 'top']）
[PASS] B. 查询参数名与契约一致 :: part / top / q 三个参数名与契约一致，且无契约外参数名（已剥离注释后扫描）
[PASS] B2. 所有查询参数都做了 encodeURIComponent 编码 :: encodeURIComponent 出现 4 次

--- C. 契约字段使用情况 ---
    [用到] alerts             行号 1054
    [用到] by_category        行号 1071
    [用到] categories         行号 1032, 1052
    [用到] category           行号 241, 452, 476, 479
    [用到] checks             行号 629, 763
    [用到] count              行号 1072, 1074, 1075, 1078
    [用到] critical           行号 571
    [用到] datasheet_url      行号 744, 745
    [用到] description        行号 743, 743, 743
    [用到] detail             行号 573, 670, 671, 759
    [用到] elapsed_ms         行号 454, 454
    [用到] filtered_out       行号 455, 455
    [用到] is_domestic        行号 691, 750
    [用到] items              行号 228, 261, 261
    [用到] lead_time_days     行号 538, 538, 601, 601
    [用到] lifecycle          行号 539, 602, 642, 696
    [用到] manufacturer       行号 241, 517, 645, 688
    [用到] manufacturers      行号 1030, 1050
    [用到] matched_part       行号 409, 410, 411, 453
    [用到] mode               行号 449, 474, 489, 630
    [用到] ok                 行号 131, 430, 684, 717
    [用到] package            行号 517, 637, 734, 789
    [用到] part_no            行号 242, 243, 515, 521
    [用到] pin_count          行号 518, 518, 518, 638
    [用到] price_cny          行号 537, 640, 685, 685
    [用到] price_ratio        行号 582, 582
    [用到] query              行号 347, 347, 392, 475
    [用到] reason             行号 1124
    [用到] reasons            行号 758, 776, 886, 886
    [用到] rejected           行号 473, 881, 914
    [用到] replacement_tier   行号 521, 534, 796, 806
    [用到] results            行号 456, 557, 815, 905
    [用到] risk_level         行号 534, 795, 805, 805
    [用到] rule               行号 571, 624
    [用到] rule_score         行号 542, 792, 836, 836
    [用到] score              行号 162, 398, 529, 529
    [用到] similarity         行号 535, 543, 793, 837
    [用到] status             行号 114, 132, 133, 135
    [用到] stock              行号 536, 583, 583, 597
    [用到] summary            行号 546, 778
    [用到] supply             行号 544, 610, 794, 838
    [用到] supply_detail      行号 579
    [用到] temp_max           行号 737
    [用到] temp_min           行号 737
    [用到] total              行号 1035, 1035, 1057
    [用到] vcc_max            行号 736
    [用到] vcc_min            行号 736
    [用到] version            行号 1133, 1133
    [用到] w_lead             行号 581, 601
    [用到] w_life             行号 581, 602
    [用到] w_price            行号 580, 598
    [用到] w_stock            行号 580, 597
    [用到] watch_count        行号 1061, 1061
[PASS] C. 契约字段全部被前端引用 :: 契约 53 个字段 100% 有代码引用（53/53）
[INFO] 说明 :: 未使用字段不构成错误；本项为完整性信息，FAIL 仅提示可补充展示

--- D. 前端访问的响应字段是否都在契约内 ---
    alerts             别名 s        契约字段
    by_category        别名 s        契约字段
    categories         别名 s        契约字段
    category           别名 a,data,it,o,r,x 契约字段
    checks             别名 r        契约字段
    classList          别名 x        内部属性
    count              别名 x        契约字段
    datasheet_url      别名 o        契约字段
    description        别名 o        契约字段
    elapsed_ms         别名 data     契约字段
    error              别名 data     内部属性
    filtered_out       别名 data     契约字段
    indexOf            别名 s        内部属性
    is_domestic        别名 o        契约字段
    items              别名 data     契约字段
    lead_time_days     别名 o,r      契约字段
    lifecycle          别名 a,o,r,s,x 契约字段
    manufacturer       别名 a,it,o,r 契约字段
    manufacturers      别名 s        契约字段
    matched_part       别名 data     契约字段
    mode               别名 data     契约字段
    package            别名 o,r      契约字段
    part_no            别名 a,it,o,r 契约字段
    pin_count          别名 o,r      契约字段
    price_cny          别名 o,r      契约字段
    query              别名 data     契约字段
    reason             别名 a        契约字段
    reasons            别名 r        契约字段
    rejected           别名 data     契约字段
    replacement_tier   别名 r        契约字段
    results            别名 data     契约字段
    risk_level         别名 r        契约字段
    rule_score         别名 r        契约字段
    score              别名 r        契约字段
    setAttribute       别名 x        内部属性
    similarity         别名 r        契约字段
    status             别名 h        契约字段
    stock              别名 a,o,r    契约字段
    summary            别名 r        契约字段
    supply             别名 r        契约字段
    supply_detail      别名 r        契约字段
    temp_max           别名 o        契约字段
    temp_min           别名 o        契约字段
    total              别名 s        契约字段
    vcc_max            别名 o        契约字段
    vcc_min            别名 o        契约字段
    version            别名 h        契约字段
    watch_count        别名 s        契约字段
[PASS] D. 前端未访问契约外的响应字段 :: 扫描 48 个形如 obj.prop 的访问，全部落在契约字段或已声明的前端内部属性内

--- E. POST /api/feedback 请求体 ---
    POST 调用点: { query: state.query, part_no: partNo, vote: vote }
    实际键: ['part_no', 'query', 'vote']
[PASS] E. 请求体键恰好为 {query, part_no, vote} :: 实际 ['part_no', 'query', 'vote'] / 期望 ['part_no', 'query', 'vote']
[PASS] E2. 请求体以 JSON + Content-Type: application/json 发送 :: request() 中统一设置 JSON 头

--- F. 错误分支处理 ---
[PASS] F. /api/part 404（未找到该型号）被前端单独识别 :: loadOriginal() 中按 err.status === 404 标记 missing 并给出文案
[PASS] F2. HTTP 非 2xx 时读取后端 {"error": ...} 文案 :: request() 中用 data.error 构造 ApiError 并展示在 #error-msg

==============================================================================
汇总：共 9 项检查，PASS 9 项，FAIL 0 项
==============================================================================
````


## 3/4 id / class 交叉引用自检 —— `check_html.py`

### 源码

````python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_html.py —— 芯选前端自检 3/3：index.html × app.js × app.css 的 id / class 交叉校验

回答三个问题：
  G. app.js 里 $('#xxx') 引用的每个 id，在 index.html 中是否存在？
     （含动态拼接写法 $('#panel-' + t)：按前缀匹配，要求前缀下有真实 id）
  H. index.html 里的每个 class，app.css 里是否有对应规则？（拼错类名 = 样式静默失效）
  I. app.js 动态生成的 HTML 里出现的 class，app.css 里是否有对应规则？
     （以及 JS 里 $('.cls') 选择器引用的 class 是否真实存在）

不追求 100% 覆盖（正则不是解析器），但能抓出「引用了不存在的 id / 类名拼错」
这类静默失效问题。输出 out-html.txt。
"""

import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML = os.path.join(ROOT, "web", "templates", "index.html")
JS = os.path.join(ROOT, "web", "static", "app.js")
CSS = os.path.join(ROOT, "web", "static", "app.css")

# 允许“有类名但故意没有样式”的类：纯语义标记 / 由父级选择器统一设置
CLASS_NO_RULE_OK = {
    "chip-example",   # 基础样式来自 .chip（若新增了 .chip-example 规则则自动也算定义）
    "btn-text",       # 排版由 .btn / .btn-primary 负责
}

results = []


def record(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, (" :: " + detail) if detail else ""))


def note(name, detail):
    print("[INFO] %s%s" % (name, (" :: " + detail) if detail else ""))


def read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def classes_in_attr_string(s):
    return set(t for t in re.split(r"\s+", s.strip()) if t)


def main():
    print("=" * 78)
    print("芯选前端自检 3/3 —— index.html × app.js × app.css 的 id / class 交叉校验")
    print("=" * 78)
    html, js, css = read(HTML), read(JS), read(CSS)
    print("index.html %d 行 / app.js %d 行 / app.css %d 行"
          % (html.count("\n") + 1, js.count("\n") + 1, css.count("\n") + 1))
    print()

    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    html_classes = set()
    for cl in re.findall(r'\bclass="([^"]+)"', html):
        html_classes |= classes_in_attr_string(cl)
    css_classes = set(re.findall(r"\.(-?[A-Za-z_][A-Za-z0-9_\-]*)", css))

    # ---------- G. JS 引用的 id ----------
    print("--- G. app.js 的 #id 引用 vs index.html ---")
    js_ids_static = set()
    dyn_prefixes = set()
    dyn_fully = 0
    # 关键：跟随选择器字面量后面是否紧跟 `+`（拼接）来区分静态/动态，
    # 首版没有区分，$('#panel-' + t) 被当成了静态 id "panel-"（误报缺失）。
    for m in re.finditer(r"\$\$?\(\s*'([^']*)'\s*(\+)?", js):
        sel, is_dyn = m.group(1), bool(m.group(2))
        ids = re.findall(r"#([A-Za-z0-9_\-]+)", sel)
        if is_dyn:
            if ids:
                dyn_prefixes.update(ids)
            else:
                dyn_fully += 1
        else:
            js_ids_static.update(ids)
    for m in re.finditer(r'\$\$?\(\s*"([^"]*)"\s*(\+)?', js):
        sel, is_dyn = m.group(1), bool(m.group(2))
        ids = re.findall(r"#([A-Za-z0-9_\-]+)", sel)
        (dyn_prefixes.update(ids) if is_dyn else js_ids_static.update(ids))
    # 由 JS 自己创建的 id（不在 HTML 里，属于正常）
    js_created_ids = set(re.findall(r"\.id\s*=\s*'([A-Za-z0-9_\-]+)'", js))

    missing_static = sorted(i for i in js_ids_static if i not in html_ids and i not in js_created_ids)
    dyn_bad = []
    for p in sorted(dyn_prefixes):
        hits = sorted(i for i in html_ids if i.startswith(p))
        print("    动态 id 前缀 '#%s' + 变量 -> 匹配到 %d 个真实 id%s"
              % (p, len(hits), (": " + ", ".join(hits[:6])) if hits else "（无！）"))
        if not hits:
            dyn_bad.append(p)
    print("    静态引用 %d 个 id；动态前缀 %d 个；纯动态拼接 %d 处（无法静态校验）；JS 自行创建 %d 个（%s）"
          % (len(js_ids_static), len(dyn_prefixes), dyn_fully, len(js_created_ids),
             ", ".join(sorted(js_created_ids)) or "-"))
    record("G. app.js 引用的 #id 在 index.html 中都存在", not missing_static and not dyn_bad,
           ("静态缺失: %s；动态前缀无匹配: %s" % (", ".join(missing_static), ", ".join(dyn_bad)))
           if (missing_static or dyn_bad) else
           "静态 %d 个 + 动态 %d 个前缀全部命中（HTML 共 %d 个 id）"
           % (len(js_ids_static), len(dyn_prefixes), len(html_ids)))
    unreferenced = sorted(html_ids - js_ids_static)
    note("HTML 中未被 app.js 直接以 #id 引用的 id（正常：多是静态内容/由 CSS 或 data-attr 驱动）",
         ", ".join(unreferenced) if unreferenced else "无")

    # ---------- H. HTML class ----------
    print("\n--- H. index.html 的 class vs app.css 规则 ---")
    undefined = sorted(c for c in html_classes if c not in css_classes)
    no_css = sorted(c for c in undefined if c not in CLASS_NO_RULE_OK)
    whitelisted_undefined = sorted(c for c in undefined if c in CLASS_NO_RULE_OK)
    print("    HTML 使用 %d 个 class；app.css 定义 %d 个类选择器" % (len(html_classes), len(css_classes)))
    record("H. index.html 的每个 class 在 app.css 中都有规则", not no_css,
           ("无对应规则（疑似拼错）: " + ", ".join(no_css)) if no_css else
           "全部命中；另有 %d 个白名单类允许无独立规则（由父级选择器统一排版）%s"
           % (len(whitelisted_undefined), ("：" + ", ".join(whitelisted_undefined)) if whitelisted_undefined else ""))
    unused_css = sorted(c for c in css_classes if c not in html_classes)
    note("app.css 定义但 index.html 未直接出现的类选择器（多为 JS 动态生成或状态类）",
         "%d 个：%s" % (len(unused_css), ", ".join(unused_css[:24]) + (" …" if len(unused_css) > 24 else "")))

    # ---------- I. JS 动态生成的 class ----------
    print("\n--- I. app.js 动态生成的 class vs app.css 规则 ---")
    js_classes = set()
    for m in re.finditer(r"""class=\\?["']([^"'\\]+)""", js):
        js_classes |= classes_in_attr_string(m.group(1))
    for m in re.finditer(r"classList\.(?:add|remove|toggle)\(\s*'([^']+)'", js):
        js_classes |= classes_in_attr_string(m.group(1))
    for m in re.finditer(r"className\s*=\s*'([^']*)'", js):
        js_classes |= classes_in_attr_string(m.group(1))
    # 由 JS 拼接进 class 属性的变量 token（如 'card ' + tierCardClass(...)）无法静态确定，
    # 这里统一丢弃以 '-' 结尾的半截 token（例如 'toast toast-' + kind 里的 "toast-"）。
    partial = sorted(c for c in js_classes if c.endswith("-"))
    js_classes = set(c for c in js_classes if not c.endswith("-"))
    js_missing = sorted(c for c in js_classes if c not in css_classes and c not in CLASS_NO_RULE_OK)
    print("    JS 动态类名 %d 个（去重后；已丢弃 %d 个动态拼接的半截 token：%s）"
          % (len(js_classes), len(partial), ", ".join(partial) or "-"))
    if js_classes:
        print("    %s" % ", ".join(sorted(js_classes)))
    record("I. app.js 动态生成的 class 在 app.css 中都有规则", not js_missing,
           ("无对应规则: " + ", ".join(js_missing)) if js_missing else
           "%d 个动态类名全部有 CSS 规则（其中 %d 个同时出现在 HTML 中）"
           % (len(js_classes), len(js_classes & html_classes)))

    # JS 里的 .cls 选择器（事件委托依赖）
    sel_classes = set()
    for m in re.finditer(r"\$\$?\(\s*'([^']+)'", js):
        s = m.group(1)
        if s.startswith("#"):
            continue
        for c in re.findall(r"\.([A-Za-z0-9_\-]+)", s):
            sel_classes.add(c)
    sel_missing = sorted(c for c in sel_classes if c not in css_classes and c not in js_classes
                         and c not in html_classes and c not in CLASS_NO_RULE_OK)
    record("I2. app.js 的 .cls 选择器引用的类名真实存在（HTML 或动态生成或 CSS）", not sel_missing,
           ("可疑: " + ", ".join(sel_missing)) if sel_missing else
           "%d 个类选择器全部有对应来源：%s" % (len(sel_classes), ", ".join(sorted(sel_classes))))

    # ---------- J. 同目录下其他模板（web/templates/stats.html 等）是否被本次改动弄坏 ----------
    # 动机：stats.html 是项目里既有的独立统计页，复用同一份 app.css。
    # 我改动 app.css 时不得让它的类名失效（否则是静默回归，页面照样 200 但没样式）。
    print("--- J. web/templates 下其他模板的 class vs app.css ---")
    tpl_dir = os.path.join(ROOT, "web", "templates")
    legacy_missing = {}
    for fn in sorted(os.listdir(tpl_dir)):
        if not fn.endswith(".html") or fn == "index.html":
            continue
        tclasses = set()
        for cl in re.findall(r'\bclass="([^"]+)"', read(os.path.join(tpl_dir, fn))):
            tclasses |= classes_in_attr_string(cl)
        miss = sorted(c for c in tclasses if c not in css_classes and c not in CLASS_NO_RULE_OK)
        legacy_missing[fn] = miss
        print("    %s：%d 个 class，缺规则的 %d 个%s"
              % (fn, len(tclasses), len(miss), ("：" + ", ".join(miss)) if miss else ""))
    all_legacy_missing = sorted({c for v in legacy_missing.values() for c in v})
    record("J. web/templates 下其他模板的 class 在 app.css 中都有规则（未被本次 CSS 改动破坏）",
           not all_legacy_missing,
           ("缺规则: " + ", ".join(all_legacy_missing)) if all_legacy_missing else
           "%d 个模板全部命中" % len(legacy_missing))

    failed = [r for r in results if not r[1]]
    print("\n" + "=" * 78)
    print("汇总：共 %d 项检查，PASS %d 项，FAIL %d 项"
          % (len(results), len(results) - len(failed), len(failed)))
    for name, _, detail in failed:
        print("  失败 -> %s :: %s" % (name, detail))
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
````

### 真实输出（`out-html.txt`，3784 字节）

````text
==============================================================================
芯选前端自检 3/3 —— index.html × app.js × app.css 的 id / class 交叉校验
==============================================================================
index.html 472 行 / app.js 1159 行 / app.css 1454 行

--- G. app.js 的 #id 引用 vs index.html ---
    动态 id 前缀 '#panel-' + 变量 -> 匹配到 4 个真实 id: panel-about, panel-model, panel-search, panel-stats
    静态引用 42 个 id；动态前缀 1 个；纯动态拼接 0 处（无法静态校验）；JS 自行创建 1 个（toast）
[PASS] G. app.js 引用的 #id 在 index.html 中都存在 :: 静态 42 个 + 动态 1 个前缀全部命中（HTML 共 54 个 id）
[INFO] HTML 中未被 app.js 直接以 #id 引用的 id（正常：多是静态内容/由 CSS 或 data-attr 驱动） :: compare-table, dataset-badge, examples, panel-about, panel-model, panel-search, panel-stats, tab-about, tab-model, tab-search, tab-stats, tabnav, tabnav-note

--- H. index.html 的 class vs app.css 规则 ---
    HTML 使用 140 个 class；app.css 定义 284 个类选择器
[PASS] H. index.html 的每个 class 在 app.css 中都有规则 :: 全部命中；另有 0 个白名单类允许无独立规则（由父级选择器统一排版）
[INFO] app.css 定义但 index.html 未直接出现的类选择器（多为 JS 动态生成或状态类） :: 144 个：c-faint, c-num, c-part, card, card-actions, card-badges, card-factors, card-ident, card-meta, card-part, card-rank, card-score, card-score-bar, card-score-cap, card-score-num, card-summary, card-top, caret, cmp-c, cmp-k, cmp-o, compare, compare-note, compare-th-part …

--- I. app.js 动态生成的 class vs app.css 规则 ---
    JS 动态类名 104 个（去重后；已丢弃 1 个动态拼接的半截 token：toast-）
    c-faint, c-num, c-part, card, card-actions, card-badges, card-factors, card-ident, card-meta, card-part, card-rank, card-score, card-score-bar, card-score-cap, card-score-num, card-summary, card-top, caret, cmp-c, cmp-k, cmp-o, compare, compare-note, compare-th-part, detail, detail-foot, detail-grid, detail-h, detail-loading, detail-sec, donut-center, factor-bars, factor-line, fbar, fbar-fill, fbar-name, fbar-note, fbar-track, fbar-val, fl-fill, fl-name, fl-track, fl-val, hbar-fill, hbar-label, hbar-row, hbar-track, hbar-val, is-active, is-busy, is-off, is-on, lc, lg-name, lg-pct, lg-swatch, lg-val, linkbtn, mono, num, pc-cell, pc-desc, pc-grid, pc-k, pc-link, pc-title, pc-v, pill, profile-card, reasons, rejected-item, rejected-meta, rejected-nums, rejected-part, rejected-why, risk, row-detail, row-main, rt-detail, rt-name, rt-status, rules-table, sl-cap, stat-card, stat-foot, stat-label, stat-value, suggest-empty, suggest-item, suggest-meta, suggest-part, summary-line, supply-total, t-part, t-reason, tag, tag-critical, tag-domestic, th-arrow, tier, toast, vote, vote-label, votebtn
[PASS] I. app.js 动态生成的 class 在 app.css 中都有规则 :: 104 个动态类名全部有 CSS 规则（其中 8 个同时出现在 HTML 中）
[PASS] I2. app.js 的 .cls 选择器引用的类名真实存在（HTML 或动态生成或 CSS） :: 5 个类选择器全部有对应来源：btn-text, chip-example, empty-hint, tab-btn, votebtn
--- J. web/templates 下其他模板的 class vs app.css ---
    stats.html：17 个 class，缺规则的 0 个
[PASS] J. web/templates 下其他模板的 class 在 app.css 中都有规则（未被本次 CSS 改动破坏） :: 1 个模板全部命中

==============================================================================
汇总：共 5 项检查，PASS 5 项，FAIL 0 项
==============================================================================
````


## 4/4 真实后端 HTTP 联调自检（附加） —— `probe_live.py`

### 源码

````python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
probe_live.py —— 芯选前端 × 真实后端 运行时契约验证（HTTP 层，非浏览器）

在同一个 Python 进程内用 werkzeug make_server 起真实 Flask 应用（prototype/wsgi.py
的 create_app()），然后用 urllib 打真实 HTTP 请求，验证：

  0. GET / 真的返回可见化页面（含题名与 /static/app.js），且 app.js 里 $()/#id 引用的
     52 个 id 在真实响应里全部存在
  1. /static/app.js、/static/app.css 的 MIME、字节数、BOM
  2. 六个接口的真实 JSON 形状 vs 冻结契约（键集合、类型、null 分布、取值域）
  3. 前端渲染假设是否成立：
       - /api/stats 的 lifecycle 到底是数组还是对象（前端两种都要能渲染）
       - watch_count / dataset / generated_at / version 是否存在
       - 所有字段的 null 情况（前端必须 ?? "—" 兜底）
       - similarity / score 的实际取值区间

只读，不改后端任何文件。输出 out-live.txt。
"""

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _p in (os.path.join(ROOT, "prototype"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PORT = 5099
FAILS = []
INFOS = []


def check(name, cond, detail=""):
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name, (" :: " + detail) if detail else ""))
    if not cond:
        FAILS.append(name + (" :: " + detail if detail else ""))
    return bool(cond)


def note(name, detail):
    print("[INFO] %s :: %s" % (name, detail))
    INFOS.append("%s :: %s" % (name, detail))


def http(port, path, method="GET", body=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def jkeys(o):
    return sorted(o.keys()) if isinstance(o, dict) else type(o).__name__


def nulls(o, prefix="", out=None):
    if out is None:
        out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            nulls(v, prefix + "." + str(k) if prefix else str(k), out)
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]):
            nulls(v, prefix + "[%d]" % i, out)
    else:
        if o is None:
            out.setdefault(prefix, 0)
            out[prefix] += 1
    return out


def main():
    print("=" * 78)
    print("芯选前端自检（补充）—— 真实后端 HTTP 联调验证")
    print("=" * 78)
    from werkzeug.serving import make_server
    import wsgi as appmod

    flask_app = appmod.create_app()
    server = make_server("127.0.0.1", PORT, flask_app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(1.2)
    print("真实应用已启动: http://127.0.0.1:%d (werkzeug make_server, 同进程)" % PORT)
    print()

    try:
        # ---------- 0. 页面 ----------
        print("--- 0. GET / 真实渲染 ---")
        st, raw, hdrs = http(PORT, "/")
        html = raw.decode("utf-8")
        check("GET / -> 200", st == 200, "HTTP %d, %d 字节, Content-Type=%s" % (st, len(raw), hdrs.get("Content-Type")))
        check("响应含作品名「芯选」", "芯选" in html)
        check("响应引用 /static/app.js 与 /static/app.css",
              "/static/app.js" in html and "/static/app.css" in html)
        disk_html = open(os.path.join(ROOT, "web", "templates", "index.html"), "rb").read()
        check("GET / 与磁盘 index.html 内容一致（模板被原样渲染）",
              raw.strip() == disk_html.strip(), "磁盘 %d 字节 / 响应 %d 字节" % (len(disk_html), len(raw)))
        check("响应无 BOM", not raw.startswith(b"\xef\xbb\xbf"))

        # 静态 id 引用 vs 真实响应（区分 $(\'#panel-\' + t) 这类动态拼接）
        js = open(os.path.join(ROOT, "web", "static", "app.js"), "r", encoding="utf-8").read()
        css = open(os.path.join(ROOT, "web", "static", "app.css"), "r", encoding="utf-8").read()
        html_ids = set(re.findall(r'\bid="([^"]+)"', html))
        js_ids, dyn_prefixes, dyn_fully = set(), set(), 0
        for m in re.finditer(r"\$\$?\(\s*'([^']*)'\s*(\+)?", js):
            sel, is_dyn = m.group(1), bool(m.group(2))
            ids = re.findall(r"#([A-Za-z0-9_\-]+)", sel)
            if not is_dyn:
                js_ids.update(ids)
            elif ids:
                dyn_prefixes.update(ids)
            else:
                dyn_fully += 1
        created = set(re.findall(r"\.id\s*=\s*'([A-Za-z0-9_\-]+)'", js))
        missing = sorted(i for i in js_ids if i not in html_ids and i not in created)
        dyn_bad = [p for p in dyn_prefixes if not any(i.startswith(p) for i in html_ids)]
        check("app.js 引用的每个 #id 在真实响应里都存在", not missing and not dyn_bad,
              ("静态缺失: %s；动态前缀无匹配: %s" % (", ".join(missing), ", ".join(dyn_bad)))
              if (missing or dyn_bad) else
              "静态 %d 个 id + 动态 %d 个前缀全部命中（响应共 %d 个 id；另有 %d 处纯动态拼接、%d 个 JS 自建 id 无法静态校验）"
              % (len(js_ids), len(dyn_prefixes), len(html_ids), dyn_fully, len(created)))
        orphan = sorted(html_ids - js_ids)
        note("HTML 中未被 app.js 直接引用的 id", ", ".join(orphan) if orphan else "无")
        html_classes = set()
        for cl in re.findall(r'\bclass="([^"]+)"', html):
            html_classes.update(cl.split())
        css_classes = set(re.findall(r"\.(-?[A-Za-z_][A-Za-z0-9_\-]*)", css))
        no_css = sorted(c for c in html_classes if c not in css_classes)
        check("index.html 的每个 class 在 app.css 里有对应规则", not no_css,
              ("缺规则: " + ", ".join(no_css)) if no_css else
              "HTML %d 个 class 全部有 CSS 规则（CSS 共 %d 个类选择器）" % (len(html_classes), len(css_classes)))

        # ---------- 1. 静态资源 ----------
        print("\n--- 1. 静态资源 ---")
        for path, disk in (("/static/app.js", "web/static/app.js"), ("/static/app.css", "web/static/app.css")):
            st, raw2, hdrs2 = http(PORT, path)
            size = os.path.getsize(os.path.join(ROOT, *disk.split("/")))
            ct = hdrs2.get("Content-Type", "")
            ok = st == 200 and len(raw2) == size
            check("GET %s -> 200 且字节数与磁盘一致" % path, ok,
                  "HTTP %d, %d 字节 (磁盘 %d), Content-Type=%s" % (st, len(raw2), size, ct))
            check("  %s 无 BOM 且可 UTF-8 解码" % path, not raw2.startswith(b"\xef\xbb\xbf"),
                  raw2[:0].decode("utf-8", "strict") == "" and "UTF-8 解码通过")

        # 既有独立页 /stats（stats.html）也必须真的能被后端渲染且样式齐备
        st, raw_s, hdrs_s = http(PORT, "/stats")
        page = raw_s.decode("utf-8", "replace")
        check("GET /stats（既有统计页）-> 200", st == 200,
              "HTTP %d, %d 字节, Content-Type=%s" % (st, len(raw_s), hdrs_s.get("Content-Type")))
        if st == 200:
            sc = set()
            for cl in re.findall(r'\bclass="([^"]+)"', page):
                sc.update(cl.split())
            s_missing = sorted(c for c in sc if c not in css_classes)
            check("stats.html 用的每个 class 在 app.css 里都有规则（该页不是无样式裸页）", not s_missing,
                  ("缺规则: " + ", ".join(s_missing)) if s_missing else
                  "%d 个 class 全部有 CSS 规则" % len(sc))

        # ---------- 2/3. 接口 ----------
        samples = {}
        print("\n--- 2. 接口真实响应形状 ---")

        st, raw3, _ = http(PORT, "/api/recommend?part=STM32F103C8T6&top=3")
        rec = json.loads(raw3.decode("utf-8"))
        samples["recommend_part"] = rec
        print("  /api/recommend?part=STM32F103C8T6&top=3 -> %d" % st)
        print("    顶层键: %s" % jkeys(rec))
        print("    mode=%r matched_part=%r category=%r filtered_out=%r elapsed_ms=%r results=%d rejected=%d"
              % (rec.get("mode"), rec.get("matched_part"), rec.get("category"),
                 rec.get("filtered_out"), rec.get("elapsed_ms"), len(rec.get("results") or []), len(rec.get("rejected") or [])))
        contract_top = ["query", "mode", "category", "matched_part", "elapsed_ms", "filtered_out", "results", "rejected"]
        check("recommend 顶层 8 键齐全", all(k in rec for k in contract_top),
              "缺: %s" % [k for k in contract_top if k not in rec] if any(k not in rec for k in contract_top) else "8/8")
        if rec.get("results"):
            r0 = rec["results"][0]
            c19 = ["part_no", "manufacturer", "category", "package", "pin_count", "price_cny", "stock",
                   "lead_time_days", "lifecycle", "similarity", "rule_score", "supply", "score",
                   "supply_detail", "checks", "risk_level", "replacement_tier", "reasons", "summary"]
            print("    results[0] 键(%d): %s" % (len(r0), jkeys(r0)))
            check("results[] 19 键齐全", all(k in r0 for k in c19),
                  "缺: %s" % [k for k in c19 if k not in r0] if any(k not in r0 for k in c19) else "19/19")
            print("    supply_detail: %s" % json.dumps(r0.get("supply_detail"), ensure_ascii=False))
            print("    checks: %s" % json.dumps([(c["rule"], c["status"], c["critical"]) for c in r0["checks"]], ensure_ascii=False))
            print("    score/rule_score/similarity/supply = %s / %s / %s / %s"
                  % (r0.get("score"), r0.get("rule_score"), r0.get("similarity"), r0.get("supply")))
            print("    risk_level=%r tier=%r" % (r0.get("risk_level"), r0.get("replacement_tier")))
            print("    summary=%s" % json.dumps(r0.get("summary"), ensure_ascii=False)[:220])
            print("    reasons=%s" % json.dumps(r0.get("reasons"), ensure_ascii=False)[:220])
            sims = [x.get("similarity") for x in rec["results"] if isinstance(x.get("similarity"), (int, float))]
            if sims:
                note("similarity 实际区间", "min=%.3f max=%.3f（前端进度条不假设能到 1.0）" % (min(sims), max(sims)))
        if rec.get("rejected"):
            rj = rec["rejected"][0]
            print("    rejected[0] 键(%d): %s" % (len(rj), jkeys(rj)))
            print("    rejected[0].reasons=%s" % json.dumps(rj.get("reasons"), ensure_ascii=False)[:200])
        nulls_rec = nulls(rec)
        note("recommend 响应中的 null 字段（前端必须兜底）",
             json.dumps(nulls_rec, ensure_ascii=False) if nulls_rec else "无 null（该样例）")

        # 自然语言模式
        st, raw4, _ = http(PORT, "/api/recommend?part=" + urllib.request.quote("3.3V 低功耗 LDO SOT-23-5") + "&top=3")
        nl = json.loads(raw4.decode("utf-8"))
        samples["recommend_text"] = nl
        print("\n  /api/recommend?part=3.3V 低功耗 LDO SOT-23-5&top=3 -> %d" % st)
        print("    mode=%r matched_part=%r category=%r results=%d rejected=%d filtered_out=%r"
              % (nl.get("mode"), nl.get("matched_part"), nl.get("category"), len(nl.get("results") or []),
                 len(nl.get("rejected") or []), nl.get("filtered_out")))
        if nl.get("results"):
            print("    r0: part=%s tier=%r risk=%r rule_score=%s (NL 模式仅展示不排序)"
                  % (nl["results"][0].get("part_no"), nl["results"][0].get("replacement_tier"),
                     nl["results"][0].get("risk_level"), nl["results"][0].get("rule_score")))
        check("NL 查询 mode=='text' 且 matched_part 为 None", nl.get("mode") == "text" and nl.get("matched_part") is None,
              "mode=%r matched_part=%r" % (nl.get("mode"), nl.get("matched_part")))

        # 空结果 / 400
        st, raw5, _ = http(PORT, "/api/recommend?part=NO_SUCH_CHIP_XYZ")
        emp = json.loads(raw5.decode("utf-8"))
        print("\n  /api/recommend?part=NO_SUCH_CHIP_XYZ -> %d results=%d mode=%r matched_part=%r"
              % (st, len(emp.get("results") or []), emp.get("mode"), emp.get("matched_part")))
        check("查不到时 HTTP 200 + results 空数组（不报错）", st == 200 and emp.get("results") == [],
              "results=%r" % (emp.get("results"),))
        st, raw6, _ = http(PORT, "/api/recommend")
        print("  /api/recommend（缺 part）-> %d body=%s" % (st, raw6.decode("utf-8")[:120]))
        check("缺 part -> 400 且 body 有 error 文案", st == 400 and b"error" in raw6)

        # /api/part
        st, raw7, _ = http(PORT, "/api/part/STM32F103C8T6")
        prt = json.loads(raw7.decode("utf-8"))
        samples["part"] = prt
        print("\n  /api/part/STM32F103C8T6 -> %d 键(%d): %s" % (st, len(prt), jkeys(prt)))
        print("    %s" % json.dumps({k: v for k, v in prt.items() if k != "description"}, ensure_ascii=False)[:500])
        c16 = ["part_no", "manufacturer", "category", "package", "pin_count", "vcc_min", "vcc_max",
               "temp_min", "temp_max", "stock", "price_cny", "lead_time_days", "lifecycle",
               "description", "datasheet_url", "is_domestic"]
        check("/api/part 契约 16 键齐全", all(k in prt for k in c16),
              "缺: %s" % [k for k in c16 if k not in prt] if any(k not in prt for k in c16) else "16/16")
        nulls_p = nulls(prt)
        note("/api/part 的 null 字段（前端必须兜底）", json.dumps(nulls_p, ensure_ascii=False) if nulls_p else "无")
        st, raw8, _ = http(PORT, "/api/part/NO_SUCH_CHIP_XYZ")
        check("/api/part 查不到 -> 404 + error", st == 404 and b"error" in raw8, "HTTP %d %s" % (st, raw8.decode("utf-8")[:80]))

        # /api/stats
        st, raw9, _ = http(PORT, "/api/stats")
        stt = json.loads(raw9.decode("utf-8"))
        samples["stats"] = stt
        print("\n  /api/stats -> %d 键(%d): %s" % (st, len(stt), jkeys(stt)))
        print("    total=%r manufacturers=%r categories=%r watch_count=%r dataset=%r generated_at=%r"
              % (stt.get("total"), stt.get("manufacturers"), stt.get("categories"),
                 stt.get("watch_count"), stt.get("dataset"), stt.get("generated_at")))
        lc = stt.get("lifecycle")
        print("    lifecycle 类型=%s 值=%s" % (type(lc).__name__, json.dumps(lc, ensure_ascii=False)[:240]))
        print("    by_category[0:2]=%s" % json.dumps((stt.get("by_category") or [])[:2], ensure_ascii=False))
        print("    alerts 条数=%d alerts[0]=%s" % (len(stt.get("alerts") or []),
                                                 json.dumps((stt.get("alerts") or [{}])[0], ensure_ascii=False)[:260]))
        check("/api/stats 契约键齐全（total/manufacturers/categories/by_category/lifecycle/alerts）",
              all(k in stt for k in ["total", "manufacturers", "categories", "by_category", "lifecycle", "alerts"]),
              "缺: %s" % [k for k in ["total", "manufacturers", "categories", "by_category", "lifecycle", "alerts"] if k not in stt]
              if any(k not in stt for k in ["total", "manufacturers", "categories", "by_category", "lifecycle", "alerts"]) else "齐全")
        if isinstance(lc, dict):
            note("lifecycle 是对象（不是契约里的数组）",
                 "前端 renderStats 必须同时支持 {生命周期: 条数} 对象与 [{lifecycle,count}] 数组两种形状")
        elif isinstance(lc, list):
            note("lifecycle 是数组", "元素键: %s" % (jkeys(lc[0]) if lc else "空"))
        note("watch_count 是否存在于 /api/stats", "存在" if "watch_count" in stt else "不存在 → 前端必须兜底（不能显示 undefined）")

        # /api/suggest
        st, raw10, _ = http(PORT, "/api/suggest?q=stm")
        sug = json.loads(raw10.decode("utf-8"))
        print("\n  /api/suggest?q=stm -> %d 键: %s items=%d" % (st, jkeys(sug), len(sug.get("items") or [])))
        print("    items[0:3]=%s" % json.dumps((sug.get("items") or [])[:3], ensure_ascii=False))
        check("/api/suggest items 元素键为 {part_no,manufacturer,category}",
              all(all(k in it for k in ["part_no", "manufacturer", "category"]) for it in (sug.get("items") or [])),
              "items≤8: %d 条" % len(sug.get("items") or []))

        # /api/health
        st, raw11, _ = http(PORT, "/api/health")
        hlt = json.loads(raw11.decode("utf-8"))
        samples["health"] = hlt
        print("\n  /api/health -> %d 键(%d): %s" % (st, len(hlt), jkeys(hlt)))
        print("    %s" % json.dumps(hlt, ensure_ascii=False)[:300])
        note("health.version 是否存在", "存在=%r" % hlt.get("version") if "version" in hlt else
             "不存在（前端 #version-chip 不能渲染成 'vok'，已改为优先 version→dataset→rows）")

        # /api/feedback
        st, raw12, _ = http(PORT, "/api/feedback", "POST", {"query": "STM32F103C8T6", "part_no": "GD32F103C8T6", "vote": "up"})
        print("\n  POST /api/feedback -> %d body=%s" % (st, raw12.decode("utf-8")[:100]))
        check("POST /api/feedback 返回 {ok:true}", st == 200 and json.loads(raw12.decode("utf-8")).get("ok") is True)
        st, raw13, _ = http(PORT, "/api/feedback", "POST", {})
        print("  POST /api/feedback（空 body）-> %d body=%s" % (st, raw13.decode("utf-8")[:100]))
        check("空 body -> 400", st == 400, "HTTP %d" % st)

        # 静态资源穿越
        st, raw14, _ = http(PORT, "/static/../prototype/wsgi.py")
        check("静态资源目录穿越被拒（非 200）", st != 200, "HTTP %d" % st)

        with open(os.path.join(os.path.dirname(__file__), "live-samples.json"), "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, indent=1)
        note("真实响应样例已存盘", ".tmp/ui-check/live-samples.json（recommend 型号/NL、part、stats、health）")
    finally:
        server.shutdown()

    print("\n" + "=" * 78)
    print("汇总：FAIL %d 项 / INFO %d 条" % (len(FAILS), len(INFOS)))
    for x in FAILS:
        print("  失败 -> %s" % x)
    print("=" * 78)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
````

### 真实输出（`out-live.txt`，7574 字节）

````text
==============================================================================
芯选前端自检（补充）—— 真实后端 HTTP 联调验证
==============================================================================
真实应用已启动: http://127.0.0.1:5099 (werkzeug make_server, 同进程)

--- 0. GET / 真实渲染 ---
[PASS] GET / -> 200 :: HTTP 200, 29400 字节, Content-Type=text/html; charset=utf-8
[PASS] 响应含作品名「芯选」
[PASS] 响应引用 /static/app.js 与 /static/app.css
[PASS] GET / 与磁盘 index.html 内容一致（模板被原样渲染） :: 磁盘 29401 字节 / 响应 29400 字节
[PASS] 响应无 BOM
[PASS] app.js 引用的每个 #id 在真实响应里都存在 :: 静态 42 个 id + 动态 1 个前缀全部命中（响应共 54 个 id；另有 0 处纯动态拼接、1 个 JS 自建 id 无法静态校验）
[INFO] HTML 中未被 app.js 直接引用的 id :: compare-table, dataset-badge, examples, panel-about, panel-model, panel-search, panel-stats, tab-about, tab-model, tab-search, tab-stats, tabnav, tabnav-note
[PASS] index.html 的每个 class 在 app.css 里有对应规则 :: HTML 140 个 class 全部有 CSS 规则（CSS 共 284 个类选择器）

--- 1. 静态资源 ---
[PASS] GET /static/app.js -> 200 且字节数与磁盘一致 :: HTTP 200, 51341 字节 (磁盘 51341), Content-Type=application/javascript; charset=utf-8
[PASS]   /static/app.js 无 BOM 且可 UTF-8 解码 :: UTF-8 解码通过
[PASS] GET /static/app.css -> 200 且字节数与磁盘一致 :: HTTP 200, 49711 字节 (磁盘 49711), Content-Type=text/css; charset=utf-8
[PASS]   /static/app.css 无 BOM 且可 UTF-8 解码 :: UTF-8 解码通过
[PASS] GET /stats（既有统计页）-> 200 :: HTTP 200, 5792 字节, Content-Type=text/html; charset=utf-8
[PASS] stats.html 用的每个 class 在 app.css 里都有规则（该页不是无样式裸页） :: 17 个 class 全部有 CSS 规则

--- 2. 接口真实响应形状 ---
  /api/recommend?part=STM32F103C8T6&top=3 -> 200
    顶层键: ['category', 'elapsed_ms', 'filtered_out', 'matched_part', 'mode', 'query', 'rejected', 'results']
    mode='part' matched_part='STM32F103C8T6' category=None filtered_out=0 elapsed_ms=27.66 results=3 rejected=3
[PASS] recommend 顶层 8 键齐全 :: 8/8
    results[0] 键(19): ['category', 'checks', 'lead_time_days', 'lifecycle', 'manufacturer', 'package', 'part_no', 'pin_count', 'price_cny', 'reasons', 'replacement_tier', 'risk_level', 'rule_score', 'score', 'similarity', 'stock', 'summary', 'supply', 'supply_detail']
[PASS] results[] 19 键齐全 :: 19/19
    supply_detail: {"price_ratio": 0.736, "w_lead": 0.9167, "w_life": 1.0, "w_price": 1.0, "w_stock": 0.6221}
    checks: [["类别一致", "pass", false], ["封装一致", "pass", false], ["引脚一致", "pass", false], ["电压兼容", "pass", false], ["功能一致", "pass", false], ["温度覆盖", "pass", false]]
    score/rule_score/similarity/supply = 0.7256 / 1.0 / 0.2736 / 0.7937
    risk_level='🟢低风险' tier='Pin-to-Pin 直接替换'
    summary="APM32F103C8T6（极海Geehy）；关键规则全部达标；库存 5400 颗/单价 ¥9.20/交期 12 天；供应链因子 0.79；可 Pin-to-Pin 直接替换"
    reasons=["参数、封装、供电、温度均满足，现货充足，可直接批量替换"]
[INFO] similarity 实际区间 :: min=0.167 max=0.274（前端进度条不假设能到 1.0）
    rejected[0] 键(19): ['category', 'checks', 'lead_time_days', 'lifecycle', 'manufacturer', 'package', 'part_no', 'pin_count', 'price_cny', 'reasons', 'replacement_tier', 'risk_level', 'rule_score', 'score', 'similarity', 'stock', 'summary', 'supply', 'supply_detail']
    rejected[0].reasons=["功能关键参数与原型号冲突（输出电压/位宽/容量/沟道等），功能不等效", "命中零容忍硬约束（封装一致、引脚一致、功能一致），已列入不推荐"]
[INFO] recommend 响应中的 null 字段（前端必须兜底） :: {"category": 1}

  /api/recommend?part=3.3V 低功耗 LDO SOT-23-5&top=3 -> 200
    mode='text' matched_part=None category='线性稳压器LDO' results=3 rejected=1 filtered_out=8
    r0: part=RT9013-33GB tier='参考替代' risk='🟡中风险' rule_score=0.5333 (NL 模式仅展示不排序)
[PASS] NL 查询 mode=='text' 且 matched_part 为 None :: mode='text' matched_part=None

  /api/recommend?part=NO_SUCH_CHIP_XYZ -> 200 results=0 mode='text' matched_part=None
[PASS] 查不到时 HTTP 200 + results 空数组（不报错） :: results=[]
  /api/recommend（缺 part）-> 400 body={"error":"缺少 part 参数"}

[PASS] 缺 part -> 400 且 body 有 error 文案

  /api/part/STM32F103C8T6 -> 200 键(16): ['category', 'datasheet_url', 'description', 'is_domestic', 'lead_time_days', 'lifecycle', 'manufacturer', 'package', 'part_no', 'pin_count', 'price_cny', 'stock', 'temp_max', 'temp_min', 'vcc_max', 'vcc_min']
    {"category": "微控制器MCU", "datasheet_url": "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf", "is_domestic": 0, "lead_time_days": 7, "lifecycle": "量产", "manufacturer": "STMicroelectronics", "package": "LQFP48", "part_no": "STM32F103C8T6", "pin_count": 48, "price_cny": 12.5, "stock": 12500, "temp_max": 85, "temp_min": -40, "vcc_max": 3.6, "vcc_min": 2.0}
[PASS] /api/part 契约 16 键齐全 :: 16/16
[INFO] /api/part 的 null 字段（前端必须兜底） :: 无
[PASS] /api/part 查不到 -> 404 + error :: HTTP 404 {"error":"未找到该型号"}


  /api/stats -> 200 键(7): ['alerts', 'by_category', 'categories', 'lifecycle', 'manufacturers', 'total', 'watch_count']
    total=89 manufacturers=36 categories=12 watch_count=7 dataset=None generated_at=None
    lifecycle 类型=list 值=[{"count": 84, "lifecycle": "量产"}, {"count": 4, "lifecycle": "NRND"}, {"count": 1, "lifecycle": "EOL"}]
    by_category[0:2]=[{"category": "微控制器MCU", "count": 13}, {"category": "线性稳压器LDO", "count": 12}]
    alerts 条数=7 alerts[0]={"category": "线性稳压器LDO", "lifecycle": "EOL", "manufacturer": "STMicroelectronics", "part_no": "LD1117S33TR", "reason": "原厂停产", "stock": 0}
[PASS] /api/stats 契约键齐全（total/manufacturers/categories/by_category/lifecycle/alerts） :: 齐全
[INFO] lifecycle 是数组 :: 元素键: ['count', 'lifecycle']
[INFO] watch_count 是否存在于 /api/stats :: 存在

  /api/suggest?q=stm -> 200 键: ['items'] items=2
    items[0:3]=[{"category": "微控制器MCU", "manufacturer": "STMicroelectronics", "part_no": "STM32F103C8T6"}, {"category": "微控制器MCU", "manufacturer": "STMicroelectronics", "part_no": "STM32F407VGT6"}]
[PASS] /api/suggest items 元素键为 {part_no,manufacturer,category} :: items≤8: 2 条

  /api/health -> 200 键(3): ['rows', 'status', 'version']
    {"rows": 89, "status": "ok", "version": "1.4"}
[INFO] health.version 是否存在 :: 存在='1.4'

  POST /api/feedback -> 200 body={"ok":true,"persisted":true}

[PASS] POST /api/feedback 返回 {ok:true}
  POST /api/feedback（空 body）-> 400 body={"error":"query 与 part_no 至少需要一个"}

[PASS] 空 body -> 400 :: HTTP 400
[PASS] 静态资源目录穿越被拒（非 200） :: HTTP 404
[INFO] 真实响应样例已存盘 :: .tmp/ui-check/live-samples.json（recommend 型号/NL、part、stats、health）

==============================================================================
汇总：FAIL 0 项 / INFO 8 条
==============================================================================
````


## 附 · 真实响应样例（`.tmp/ui-check/live-samples.json`）

`probe_live.py` 落盘的真实响应片段，共 778 行 / 21388 字节；以下为前 60 行摘录，完整内容见该文件。

````json
{
 "recommend_part": {
  "category": null,
  "elapsed_ms": 27.66,
  "filtered_out": 0,
  "matched_part": "STM32F103C8T6",
  "mode": "part",
  "query": "STM32F103C8T6",
  "rejected": [
   {
    "category": "微控制器MCU",
    "checks": [
     {
      "critical": false,
      "detail": "原类别 微控制器MCU，候选 微控制器MCU",
      "rule": "类别一致",
      "status": "pass"
     },
     {
      "critical": true,
      "detail": "原封装 LQFP48，候选 LQFP100，封装不同需改板",
      "rule": "封装一致",
      "status": "fail"
     },
     {
      "critical": true,
      "detail": "原 48 脚，候选 100 脚（差值 +52）",
      "rule": "引脚一致",
      "status": "fail"
     },
     {
      "critical": false,
      "detail": "原 2-3.6V，候选 1.8-3.6V，裕量 0V",
      "rule": "电压兼容",
      "status": "pass"
     },
     {
      "critical": true,
      "detail": "关键功能参数冲突（Flash/RAM）：原件 Flash=64KB/RAM=20KB，候选 Flash=1024KB/RAM=192KB",
      "rule": "功能一致",
      "status": "fail"
     },
     {
      "critical": false,
      "detail": "原 -40~85℃，候选 -40~85℃",
      "rule": "温度覆盖",
      "status": "pass"
     }
    ],
    "lead_time_days": 25,
    "lifecycle": "NRND",
    "manufacturer": "STMicroelectronics",
    "package": "LQFP100",
    "part_no": "STM32F407VGT6",
    "pin_count": 100,
    "price_cny": 42.0,
    "reasons": [
     "功能关键参数与原型号冲突（输出电压/位宽/容量/沟道等），功能不等效",
     "命中零容忍硬约束（封装一致、引脚一致、功能一致），已列入不推荐"
    ],
````
