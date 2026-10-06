# 开源参考项目可用性与 License 核实（2026AIC 方向5 芯片智能供应链 / 芯选）

核实日期：2026-10 会话内实测。**所有结论均来自本次实际请求**（GitHub REST API、ungh.cc、img.shields.io、raw 正文经 ghfast.top 代理、GitHub 网页）。
方法与环境限制：本机 pwsh 无网络（`schannel: SEC_E_NO_CREDENTIALS 0x8009030e`），全部取证经 `web_fetch`；`raw.githubusercontent.com` 直连失败，改用 `https://ghfast.top/https://raw.githubusercontent.com/...` 取正文；无法用 `git clone`，文件级结论来自远端文件清单（ungh.cc）与 raw 正文。

## 主表

| 名称 | 核实后的 owner/repo | 存在? | Star | License (spdx) | 最后更新 | 语言 | 最关键可借鉴点(具体文件/函数) | 复用风险 |
|---|---|---|---|---|---|---|---|---|
| STM32 RAG 助手 | `AmalDak/stm32-rag-assistant` | 是 | 1 | **无**（API `license: null`，仓库无 LICENSE 文件） | 2026-08-16 | Python | 三段式检索链：`retrieval/requirement_extractor.py` → `retrieval/catalog_filter.py` → `retrieval/reranker.py`（先抽需求、再按目录过滤、再重排），配 `evaluation/run_eval.py` | 无 License ⇒ 默认版权保留，**不可抄代码**；仅能参考"抽取-过滤-重排"分层设计 |
| 元器件搜索/替代推荐 | `cosmicbeing619/The_Gradient_Decendants` | 是 | 1 | **无**（README 仅写"as-is for educational and development purposes"） | 2026-09-25 | Python | `app.py` + `chatbot.py`：Gemini 做查询改写、Mouser API 检索、FuzzyWuzzy/Levenshtein 容错匹配 | 无 License；`.env` 已提交（密钥泄露）；README 自称的 `mouser_search_engine.py`/`MouserSearchApp` **在仓库中不存在**，README 与代码不一致 ⇒ 只能当思路 |
| 离线 MCU 选型 | `new-bmp/MCUS` | 是 | 47 | **Apache-2.0** | 2026-09-29 | Python | 数据快照 **13,791 个器件 / 20,853 个订货号**（`mcu-l-catalog/`），纯静态可部署的选型前端 `mcu-l-web/staticfiles/`，手机构建 `mcu-l-android/` | Apache-2.0：可安全参考/复用，需保留版权与 NOTICE；数据库时效取决于快照 |
| 确定性推荐排序 | `moellere/WireStudio` | 是 | 26 | **MIT** | 2026-10-03 | Python | `wirestudio/recommend/recommender.py`：`recommend_components(library, query, constraints=None, limit=10, inventory=None)`、`_match_score()`、`_passes_constraints()`、`_FIELD_WEIGHTS={"use_cases":4.0,"name":2.5,"category":2.0,"aliases":1.5}`、`_INVENTORY_BOOST=5.0`；**score = match + 3.0*in_examples − 0.05*peak_ma**；docstring 明示 "Pure: no LLM call, no network."（可作为"规则分+库存分"的可解释排序基线） | MIT，可放心参考/复用，保留版权声明即可；建议只借鉴公式与结构 |
| 元器件比价/替代 | `SourceParts/parts-mcp` | 是 | 2 | **双文件不一致**：`LICENSE`=Apache-2.0（API 取到），`LICENSE.md`="MIT License with Trademark Protection" | 2026-08-16 | Python | `parts_mcp/utils/component_matcher.py`（参数/封装/值匹配）、`parts_mcp/tools/sourcing.py` 中 `find_alternatives`、`parts_mcp/utils/bom_parser.py`；工具链还有 search_parts / get_part_pricing / check_availability / process_bom 等 | 以 Apache-2.0 计可复用，但附加商标条款：**不得**在衍生作品名中使用 "Source Parts"/"Parts MCP" 或 logo；运行需 `SOURCE_PARTS_API_KEY` 调其云服务（离线/断网不可用） |
| 立创商城 MCP | **未找到**（网上流传的 `zhr1008/szlcsc-mcp`） | **否（404）** | — | — | — | — | 替代见下节 | — |
| JLC 元件目录数据库 | **原创 `yaqwsx/jlcparts`**（`sleemanj/jlcparts` 与 `dougy83/jlcparts` 均为其 fork） | 是 | 837（原创） | **MIT** | 2026-10-04 | Python | CI 抓取 JLC PCB 的 XLS → 按类别生成 JSON；构建命令 `jlcparts buildtables --jobs 0 --ignoreoldstock 30 cache.sqlite3 web/public/data`；前端 IndexedDB 本地查询，无后端 | MIT，可放心参考；**"~20MB 数据库 / 每日更新"未在 README 中出现 ⇒ 未确认**（更新由 `.github/workflows/update_components.yaml` 触发） |
| 立创 API 搜索 | **`Bouni/kicad-jlcpcb-tools`**（`harry10086/kicad-jlcpcb-tools` 是它的 fork） | 是 | 2094（上游） | **MIT** | 2026-10-04 | Python | `common/jlcapi.py`（12206B）+ `lcsc_api.py`/`lcsc.py`：立创商城搜索与价格/库存 API 封装；`common/partsdb.py` + `db_build/jlcparts_db_convert.py`：把 jlcparts 数据转本地可用库；`value_normalize.py` 参数归一化 | MIT，谨慎复用；用上游而非 fork（fork 描述另含嘉立创/SZLCSC 订货号改动） |
| `jlcpcb-component-finder` skill | **未验证成功**（搜索命中的 `takazudo/claude-resources/main/skills/jlcpcb-component-finder/SKILL.md` 现为 404） | 未确认 | — | — | — | — | 可替代的已验证同功能项目：`Takazudo/jlcpcb-parts-finder-skill`（`SKILL.md`+`query.js`，把查询交给 CLI 脚本的 skill 写法） | 该替代仓库 **License 未指定**（shields 返回 "not specified"）⇒ 只可参考 skill 文件组织方式 |

## 404 / 改名 / 不可用清单

| 原始名称 | 核实结果 | 替代项目（含链接） | 替代项目 License |
|---|---|---|---|
| `zhr1008/szlcsc-mcp` | **404**：`api.github.com/repos/zhr1008/szlcsc-mcp` → `{"message":"Not Found","status":"404"}`；shields 徽章 → `repo not found`；`zhr1008` 名下 8 个仓库（Antigravity-Manager、HLTV-Demo-Downloader、kuake_qiandao、mermaid-live-editor、OpenCut、orderingforstudent、pintree、Quark_Auot_Check_In）中**没有** szlcsc-mcp（MCP 目录站 glama.ai 仍有其收录页，但 GitHub 源已不可用） | [Eyalm321/jlcpcb-mcp](https://github.com/Eyalm321/jlcpcb-mcp)（JLC/LCSC 目录检索 + wmsc.lcsc.com 实时库存/价格/数据手册） | MIT（本次 shields 确认） |
| `sleemanj/jlcparts` | **不是原创，是 fork**（default_branch 为 `deploy-fixes`，star 1） | [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts)（原创，star 837） | MIT |
| `harry10086/kicad-jlcpcb-tools` | **是 fork**（star 2），上游为 Bouni | [Bouni/kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools)（star 2094） | MIT |
| `jlcpcb-component-finder` skill | 原路径 **404**（未验证成功） | [Takazudo/jlcpcb-parts-finder-skill](https://github.com/Takazudo/jlcpcb-parts-finder-skill) | 未指定（无 License） |
| 其他未核实项 | `chengyangliu-lcy/lcsc-mcp-server-node` **未核实**（仅搜索命中，未打开） | — | — |

## License 风险结论

- **可直接参考/复用（宽松许可，保留版权声明即可）**：MIT — `moellere/WireStudio`、`yaqwsx/jlcparts`、`Bouni/kicad-jlcpcb-tools`、`Eyalm321/jlcpcb-mcp`；Apache-2.0 — `new-bmp/MCUS`、`SourceParts/parts-mcp`。
- **本次核实中未发现 GPL / AGPL / LGPL 项目** —— 即没有"因为传染性许可而不能碰代码"的项目。风险集中在另外两类：
  1. **无 License**（`AmalDak/stm32-rag-assistant`、`cosmicbeing619/The_Gradient_Decendants`、`Takazudo/jlcpcb-parts-finder-skill`）：默认保留全部版权，**不能复制代码/数据**，只能读思路后自研；写进报告时必须说明。
  2. **附加条款**：`SourceParts/parts-mcp` 同一仓库存在两个 License 文件（Apache-2.0 与 "MIT + 商标限制"），且其 `LICENSE.md` 明确禁止在衍生品名称/logo 中使用其商标 —— 引用时以 Apache-2.0 为准，但**不使用其名称与品牌**。
- **可写进报告的一句话（建议原文采用）**：
  > "本项目仅参考上述开源项目的**设计思路与算法范式**（如确定性规则打分、需求抽取-过滤-重排、离线元件目录构建），所有代码与数据均为自研/自行采集；对采用 MIT / Apache-2.0 许可的组件，如需直接复用将在 `NOTICE` 中保留原始版权声明；对无 License 的项目（`AmalDak/stm32-rag-assistant`、`cosmicbeing619/The_Gradient_Decendants`）不复制任何代码。"

## 对「依赖某个开源项目」的建议

- **适合"直接用/调用"**：
  - `yaqwsx/jlcparts`（MIT）：其产出的按类别 JSON / SQLite 缓存可作为元件目录数据源；`Bouni/kicad-jlcpcb-tools` 的 `common/jlcapi.py` 展示了立创搜索/价格 API 的调用方式。
  - `new-bmp/MCUS`（Apache-2.0）：13,791 器件 / 20,853 订货号的离线快照 + 静态前端，适合做本地选型底座。
  - `Eyalm321/jlcpcb-mcp`（MIT）：现成的 JLC/LCSC MCP 服务，可接入自研 Agent 取实时库存。
- **仅适合"参考思路"，不要引入为依赖**：
  - `moellere/WireStudio`（MIT，质量最高）：许可允许复用，但它是 ESPHome/KiCad 领域的完整应用，与芯片选型域不匹配；建议**移植其排序公式与 `Constraints` 设计**，代码自研。
  - `SourceParts/parts-mcp`：核心价值在 `component_matcher.py` 与 `find_alternatives` 的匹配维度，但强依赖其云 API Key，做比赛 Demo 有断网/配额风险 ⇒ 参考维度设计，自研离线匹配。
  - `AmalDak/stm32-rag-assistant`、`cosmicbeing619/The_Gradient_Decendants`：无 License，**只能读结构**（RAG 三段链 / 查询改写+模糊匹配），不得复制。
  - `Takazudo/jlcpcb-parts-finder-skill`：无 License，仅可参考 skill 的 `SKILL.md` 编写形式。

## 本次核实的证据

| 项目 | 实际取得的证据 | 证据类型 |
|---|---|---|
| `AmalDak/stm32-rag-assistant` | API 返回含 `"full_name":"AmalDak/stm32-rag-assistant"`、`"license":null`、`"pushed_at":"2026-08-16T13:43:29Z"`；文件清单见 `retrieval/requirement_extractor.py` 等 | **API 确认** |
| `cosmicbeing619/The_Gradient_Decendants` | API：1 star、`license: null`、pushed_at 2026-09-25；README 网页正文含项目结构仅 README.md/app.py/chatbot.py/requirements.txt 与 "MouserSearchApp"，并写明仅 "educational and development purposes" | **API + 网页确认** |
| `new-bmp/MCUS` | API：`"license":{"spdx_id":"Apache-2.0"}`、47 stars、size 194510；README 正文含 "13,791 个器件、20,853 个订货号" | **API + 网页确认** |
| `moellere/WireStudio` | API：26 stars、MIT、pushed_at 2026-10-03（topics 含 kicad/mcp）；`recommender.py` raw 正文含 `_INVENTORY_BOOST = 5.0` 与 "Pure: no LLM call, no network." | **API + 网页确认** |
| `SourceParts/parts-mcp` | API：Apache-2.0（`LICENSE` 11342B）；README 正文工具表含 "find_alternatives";`LICENSE.md` raw 正文首行 "MIT License with Trademark Protection" | **API + 网页确认** |
| `zhr1008/szlcsc-mcp` | `api.github.com/repos/zhr1008/szlcsc-mcp` → `{"message":"Not Found","status":"404"}`；`ungh.cc/users/zhr1008/repos` 列出的 8 个仓库中无此项；shields 返回 `repo not found` | **API 确认（404）** |
| `sleemanj/jlcparts` → `yaqwsx/jlcparts` | API：sleemanj 仓库 `"fork":true`、`"default_branch":"deploy-fixes"`、parent=dougy83；`yaqwsx/jlcparts` 837 stars、MIT、Python、master。README 正文含 `jlcparts buildtables --jobs 0 --ignoreoldstock 30 cache.sqlite3 web/public/data` | **API + 网页确认** |
| `harry10086/kicad-jlcpcb-tools` → `Bouni/kicad-jlcpcb-tools` | API：harry10086 仓库 `"fork":true`，source/parent=`Bouni/kicad-jlcpcb-tools`；上游 2094 stars、MIT、pushed_at 2026-10-04；文件清单含 `common/jlcapi.py`、`lcsc_api.py` | **API 确认** |
| `jlcpcb-component-finder skill` | 搜索命中 raw 路径标题 "name: jlcpcb-component-finder"，但经 gh-proxy.com 与 ghfast.top 访问该路径均 404；`takazudo/claude-resources` 文件清单中无 `skills/jlcpcb-component-finder/`；替代项 `Takazudo/jlcpcb-parts-finder-skill` 文件清单含 `SKILL.md`(4423B)/`query.js` | **网页确认（含 404）** |
| 替代项 `Eyalm321/jlcpcb-mcp` | ungh 返回 `{"repo":"Eyalm321/jlcpcb-mcp","description":"MCP server for JLCPCB/LCSC: catalog search (yaqwsx/jlcparts SQLite) + live stock, pricing, and datasheets from wmsc.lcsc.com","stars":2,"defaultBranch":"main"}`；shields license → `"MIT"` | **API/徽章确认** |

> 说明：表中凡标"未确认/未验证成功"的条目（如 jlcparts 的"~20MB/每日更新"、`chengyangliu-lcy/lcsc-mcp-server-node`）均**未取得直接证据**，不得作为事实引用。
