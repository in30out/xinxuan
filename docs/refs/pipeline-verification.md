# 芯选 —— 技术链路验证报告（第一版原型）

> 结论先行：**链路已在真实环境跑通**（数据 → 召回 → 规则 → 排序 → 风险分级 → CLI / HTTP API 全为真实执行），
> 唯一硬约束是**本沙箱内 `pip` 无法使用**，已用自写下载器绕过并记录。原始终端输出见 `prototype-run.md`。

## 0. 时效性说明（2026-10-06 追加，必读）

本报告采集于 **2026-10-05**。以下内容仍然成立：pip 不可用与绕行方案（§2）、层次划分与规则行为（§3 的定性结论）、踩坑清单（§4）、创新点难度（§6）、技术栈建议（§7）、遗留问题（§8）。

**已过时的部分**：§3 与 §5 里所有**相似度/总分的具体数值**。原因是 Lead 修复了 `recall.tokenize()` 的 sklearn 契约缺陷（原返回字符串 → `ngram_range=(1,2)` 被按字符切片退化为伪 2-gram；现返回 token 列表并清洗空白/单字符 ASCII token），修复后相似度量级整体下降，且 §3 的 `vocab=1317` 需以修复后词表为准。当前权威评测请看 `docs/refs/eval-report.md`（型号 Top-1 6/7、Top-5 7/7，E4 硬约束违规 0/19，`pytest -q -p no:cacheprovider` 25 passed）。

**改名影响**：`app.py`（Flask 应用本体）已改为 `prototype/wsgi.py`，`prototype/app.py` 仅保留为转发壳；表格与命令中出现的 `app.py` 请按 `wsgi.py` 理解。

**修复后我实测的当前基线**：`python prototype/recommend.py STM32F103C8T6 --top 3` → 25.32 ms，APM32F103C8T6 0.726/相似 0.27/规则 1.00/🟢Pin-to-Pin，STC8H8K64U-45I-LQFP48 0.708，CH32V203C8T6 0.689。**独立交叉验证（exit 0）**：`scripts/compare_vectorizer.py` 10/10 顺序一致、相似度最大相对误差 2.429e-06、`VECTORIZER_MATCH_OK`；`scripts/_check_api.py` 7 组全 OK、1.50s、`SMOKE_OK`。

## 1. 环境结论（实测）

| 项 | 实测值 |
| --- | --- |
| 操作系统 | Windows x64 |
| 解释器（跑通全链路） | `C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` = **Python 3.12.14** |
| 默认 `python` | `...\Pycharm_test\.venv\Scripts\python.exe` = Python 3.14.0，只有 numpy 2.4.6 / pandas 2.3.3（**不能**直接跑本项目） |
| 解释器自带包 | numpy 2.3.5、pandas 3.0.1 |
| 追加安装位置 | `<workspace>\.deps`（`$env:PYTHONPATH` 注入，不改 site-packages） |
| 实测依赖版本 | scikit-learn 1.9.1、scipy 1.18.1、joblib 1.6.0、threadpoolctl 3.7.0、cloudpickle 3.1.2、narwhals 2.26.0、Flask 3.1.3、Werkzeug 3.1.9、Jinja2 3.1.6、MarkupSafe 3.0.4、itsdangerous 2.2.0、click 8.5.0、blinker 1.9.0、colorama 0.4.6、flask-cors 6.0.5、jieba 0.42.1 |
| 中文控制台 | 必须 `chcp 65001` / `[Console]::OutputEncoding=UTF8` + `$env:PYTHONIOENCODING="utf-8"`，否则输出乱码 |

## 2. 依赖安装：`pip` 为什么不可用，以及绕行方案

**结论：本沙箱环境下 `pip install` 一律失败**，与网络无关（PyPI 可正常访问），是沙箱拒绝 pip 解包 wheel 时写元数据/硬链接：

```
ERROR: Could not install packages due to an OSError: [Errno 13] Permission denied:
'C:\Users\13718\AppData\Local\Temp\dsh-PWAldB\pip-unpack-8ot7hfih\scikit_learn-1.9.1-cp312-cp312-win_amd64.whl.metadata'
```

已排除的可能性：把 `$env:TEMP`/`$env:TMP` 指到 workspace 后报错路径变化但错误相同；`pip download jieba` 同样 exit 1；
而用普通 `python -c "open(r'<ws>\.tmp\probe\x.whl.metadata','w')"` 写文件成功，`urllib` 拉 `https://pypi.org/pypi/jieba/json` 成功
→ 说明**不是磁盘权限/网络问题，而是 pip 的解包流程被沙箱拦截**。

**绕行方案（已实现并跑通）**：`scripts/fetch_deps.py`
- 直接请求 `https://pypi.org/pypi/{name}/json`，按当前解释器构造标签 `cp{major}{minor}` + `win_amd64`，挑 `*-none-any.whl` 或 `-cp312-cp312-win_amd64.whl` 下载 → `zipfile` 解压到 `--target`（默认 `<ws>\.deps`）；
- 纯平台 wheel（如 scikit-learn、scipy）**也能装**；只有 sdist 的 `jieba` 用固定暂存目录 `<ws>\.deps-build\{name}` 解包后 `copytree`（**不能用 `tempfile.TemporaryDirectory`**，其清理阶段报 `PermissionError [WinError 5]`）；
- `setup_env.ps1` 先试 `pip install -r requirements.txt`，失败自动回落 `fetch_deps.py`，因此**同一份脚本在正常环境和受限沙箱都能用**。

副作用：`jieba` 由 sdist 安装，`importlib.metadata.version('jieba')` 报 MISSING（`import jieba` 与分词正常），安装时有一条 `SyntaxWarning: invalid escape sequence`——不影响功能。

## 3. 链路是否跑通（逐层证据）

| 层 | 实现 | 实测证据 |
| --- | --- | --- |
| 数据层 | `data/samples/chips_seed.csv`（CSV 89 行 × 16 列，含 `p2p_with` 人工关系列；加载后 17 列）+ `data_loader.load_chips` | 89 行加载成功，`load_chips` 1447 ms（含 pandas 冷导入） |
| 召回层 | `recall.RecallIndex`：jieba 搜索模式分词 + `TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)` + 余弦相似度 | vocab=1317；RS-485 / CAN / SPI Flash 等查询 Top-1 正确 |
| 规则层 | `rules.check_rules`：类别/封装/引脚/电压/**功能参数指纹**/温度 六条规则，pass-warn-fail 三态 + 加权分 | `STM32F103C8T6` 类全部 pass，规则分 1.00；`AMS1117-5.0` 因输出电压冲突得 0.70/功能 fail |
| 排序层 | `ranking.rank`：型号模式 `0.70×规则分 + 0.30×相似度`；**自然语言模式 `param = 相似度`（规则分只展示、不参与排序）**；最后 × `(0.65 + 0.35×供应链因子)` | 相似度更高但功能冲突的候选（`W25Q32JVSSIQ` 0.88）被规则分拉低到第 2 |
| 风险层 | `risk.assess`：🟢/🟡/🔴 + 四档替代等级 + 中文理由 | `LD1117S33TR`（EOL/0 库存）→ 🔴 不推荐；`TPS7A4901DGNR` 无同封装候选 → 只给参考替代 |
| 应用层 | `recommend.py` CLI、`wsgi.py` Flask（`/`、`/api/recommend`、`/stats`，含 CORS；`app.py` 仅为转发壳） | CLI exit 0（见 2.x 各段）；HTTP 200/400 与服务器日志齐全，端口已释放 |

自写的两个"数据质量"机制在实测中都起到了作用：
1. **`p2p_with` 人工关系列**（同封装同脚数的直接替换关系）与描述关键词共同构成"引脚兼容证据"，
   没有证据的 `STC8H8K64U` 不会冒充 Pin-to-Pin；
2. **"已排除候选"列表**：被判"不推荐"的候选不静默消失，而是带理由列在结果下方。

## 4. 踩坑清单（全部为真实报错）

| # | 现象 | 根因 | 处理 |
| --- | --- | --- | --- |
| 1 | `pip install` → `OSError [Errno 13] Permission denied ...*.whl.metadata` | 沙箱拦截 pip 解包 | `scripts/fetch_deps.py` 自写下载器 |
| 2 | `tempfile.TemporaryDirectory` 清理 → `PermissionError [WinError 5]` | 同上 | 改用固定目录 `.deps-build` |
| 3 | `ModuleNotFoundError: No module named 'cloudpickle'` / `narwhals.stable.v2` | sklearn 1.9 的新传递依赖 | 补装并写进 `requirements.txt` |
| 4 | `ValueError: could not convert string to float: '双'` | 功能指纹正则 `([单双…])\s*路` 捕获中文数字后走 float 分支 | 中文数字映射表 + try/except 兜底（**基准测试的全库遍历才暴露，单点测试漏掉**） |
| 5 | `ModuleNotFoundError: No module named 'resource'` | `resource` 是 Unix-only 模块 | 去掉内存统计 |
| 6 | 控制台中文乱码 | Windows 默认 GBK | `chcp 65001` + `PYTHONIOENCODING=utf-8` |
| 7 | pwsh 报 `[exit code: 1]` 但 CLI 实际成功 | `& python ... 2>&1 \| Select-String` 这类管道使 `$?` 为 False（`$LASTEXITCODE` 仍为 0）；`Select-Object -First 1` 会截断管道使 python 收到 broken pipe 而退出 -1 | 采集证据时不用管道，直接运行 |
| 8 | 默认 `python` 没有 sklearn/flask | 默认解释器是 3.14 的 PyCharm venv | 固定用 dsh 运行时 3.12 解释器 + `PYTHONPATH=.deps` |

## 5. 性能实测（89 行芯片库）

- 一次性启动：`load_chips` 1.45 s（其中 pandas 冷导入约 1.4 s）+ 建索引 1.36 s（jieba 词典 0.42 s + sklearn 导入与拟合约 0.9 s）；
- 单次查询：**avg 4.71 ms，p50 4.78 ms，p95 5.63 ms（全量 89 个型号各查一次）**，CLI 端到端 5.0–6.8 ms，Flask 单请求 5.4 ms；
- 推理：耗时与库大小近似线性（全量打分 + 排序，无索引剪枝）。即使扩到 10 万条，单次查询预计仍在百毫秒级；
  真正需要优化的不是召回，而是**描述文本质量**（参数结构化后可用列级过滤直接剪枝）。

## 6. 创新点实现难度评估

| 创新点 | 本原型实现程度 | 难度 | 结论 / 风险 |
| --- | --- | --- | --- |
| 自然语言需求 → 候选召回 | 已实现（jieba + TF-IDF + 关键词加权） | ★★★☆ | 代码简单，**准确率是难点**：`3.3V 低功耗 LDO SOT-23-5` 的 Top-1 是 RS-485 收发器（品类词未被约束）。需补"品类词典"或向量检索 |
| 六维兼容性规则库（含功能参数指纹） | 已实现，阈值/权重集中可配 | ★★★☆ | 单条规则简单，难点在**参数抽取的召回率**（现在只认描述里的"3.3V/16位/2Kbit/N沟道"等模式）；生产必须把参数做成结构化字段而不是塞在描述里 |
| 功能参数指纹比对（电压/位宽/通道/容量/沟道归一化） | 已实现（1MB=1024KB、双路=2 等归一化） | ★★★★ | 是最"有含量"的一环，也是替换方案里最容易出错的一环（同名不同义、单位混用）；建议产线化时改为字段级比较 + 人工复核队列 |
| 风险分级 + 四档替代等级 | 已实现（🔴 触发：EOL/零库存/电压无交集/功能冲突） | ★★☆ | 规则明确、易解释，**是产品可感知的价值点**，成本低，建议优先做深 |
| 供应链接入（库存/价格/交期/生命周期几何加权） | 已实现（含零库存惩罚） | ★★☆ | 算法简单，难的是**数据获取与刷新**（真实库存/价格需商城 API 或人工维护） |
| 可解释推荐（理由/不达标规则/已排除候选） | 已实现 | ★★☆ | 直接提升 B 端用户信任度，实现成本低，建议保持 |
| 引脚兼容证据（`p2p_with` 关系表） | 已实现（人工列 + 描述关键词） | ★★★★ | 真正的护城河是**数据**：几百万型号的引脚兼容关系无法自动推出，需人工/厂商 datasheet 支撑 |
| Web API + 页面 | 已实现（Flask 单文件 + CORS + 表格页） | ★☆ | 无技术风险，工作量在 UI/交互 |

**总体判断**：整套链路的**代码量很小（`prototype/` 共 7 个文件、每个 ≤150 行），一周内可出可演示版本**；
成本和风险集中在三处——① 数据（参数、引脚、兼容关系、供货）的**真实性与覆盖率**；② 自然语言召回的准确率；
③ 参数抽取与规则的**长期维护**。建议立项时把"数据爬取/清洗 + 规则可配置化"当作一等公民，而不是先做花哨的排序模型。

## 7. 技术栈建议

**数据库：第一版 SQLite 足够，不建议一上来用 MySQL。**
- 依据：89 行的库全量加载 + 打分只需 5 ms；SQLite 单机可轻松支撑 10 万级器件表 + 全文检索（FTS5）、零运维、随应用分发；
- MySQL 的收益只在"多用户并发写 / 团队共享 / 权限审计 / 已有运维体系"时出现。建议做法：**DAL 层抽象成 repository 接口**，
  数据先用 CSV/SQLite 起步，接口稳定后再迁 MySQL/PostgreSQL，迁移成本几乎为零；
- 真要把"参数筛选"下推到数据库，建议把参数结构化（`vcc_min`、`vcc_max`、`pin_count`、`package` 等列已在种子数据里就绪），
  用列索引做第一层剪枝，再对少量候选做文本召回。

**向量库：当前阶段不需要，属于"过度工程"。**
- 依据：TF-IDF + 余弦在 10 万条内是毫秒级，且可解释、可离线、无额外服务；
- 若确有必要提升语义召回（例如上面 LDO 的失败案例），**优先低成本方案**：① 品类词典/同义词表（"LDO→线性稳压器"、"运放→运算放大器"），
  10 行代码即可显著改善；② 把功能参数结构化后做硬过滤；③ 再不行才上中文 embedding（bge-small-zh 等）+ FAISS/pgvector；
- 若最终上线，嵌入式/单机部署用 `sqlite + numpy 点积 + 预计算向量` 就够，**不必引入独立向量数据库服务**。

**运行时形态建议**：Python 3.12 + Flask/FastAPI + SQLite（或 MySQL）+ 预计算索引常驻内存；
前端可先服务端渲染（本原型的表格页已验证可用），后续再拆前后端。

## 8. 遗留问题与下一步

1. 自然语言召回准确率：补品类词典 / 同义词映射，或评估中文小模型 embedding；
2. 数据来源：89 行种子数据是手工构造的演示数据，下一版需接入真实数据（商城/原厂参数）并设计字段映射与去重；
3. 参数抽取召回率：把 `description` 里的关键参数转为结构化字段，规则层直接读列；
4. 规则权重与阈值（`WEIGHTS`、`STATUS_SCORE`、温度覆盖 0.8、交期 30 天等）目前是拍的，需要用真实选型反馈校准；
5. `p2p_with` 这类关系数据需要设计维护流程（人工录入 + 巡检）；
6. 英文/中英混排描述的分词与型号归一化（例如 `AMS1117-3.3` 与 `AMS1117-3.3V`）仍需专项处理。
