# 芯选 离线评测报告（experiments/eval.py）

> 本文所有数字都来自本机真实运行：`experiments/eval.py`。
> 原始结果（含每条用例的完整返回）另存于 `docs/refs/eval-seed.json` 与 `docs/refs/eval-real-semi.json`。
> 运行方式：
> ```powershell
> $env:PYTHONPATH = "<repo>\.deps"
> & <python> experiments\eval.py --json docs\refs\eval-seed.json
> & <python> experiments\eval.py --csv data\chips_real_semi.csv --json docs\refs\eval-real-semi.json
> ```

## 1. 指标的定义与口径

| 指标 | 定义 | 为什么这么定 |
| --- | --- | --- |
| **E1 Top-K 命中率** | 标注集里写明的**真正 Pin-to-Pin 替代**是否出现在 Top-K | 直接回答"系统有没有找对"，是最容易被评委追问的数字 |
| **E2 单次延迟** | `recommend()` 端到端 wall-clock，mean / p95 / max | 文档 §1 承诺"响应 < 2 s"，必须给出真实基线 |
| **E3 消融对比** | 每次只关闭一个机制（规则分 / 供应链因子 / 品类归一 / NL 重排），其余保持完整，比较 E1/E2/E4 | 证明每个机制都"有贡献"，而不是堆功能；对应评分表"创新性 30 分"要的差异化证据 |
| **E4 硬约束违规率** | 返回结果中**带零容忍硬约束失败**的条数占比 | 硬约束是零容忍设计，违规率必须为 **0**，否则就是过滤有漏洞 |

**口径红线（写进代码注释，避免以后自我美化）**：

- `pins` 只收**真正 Pin-to-Pin** 的料号。功能等效但要改板的（如 CH340G → CH340N SOP-8）放进 `functional`，**不计入 pin 命中**。
- 数据集里不存在的用例报 **SKIPPED**，不计失败也不计通过。
- 零容忍集合 = `rules.py` 里 `critical=True` 的失败项，**只有 5 条**：类别不符 / 封装串不同 / 脚位差 > 2 / 电压零交集 / 功能参数冲突。
  **温度覆盖不足刻意不算零容忍**（`critical=False`）——覆盖率低于 80% 仍判 `fail`、仍会拉低规则分与风险等级，
  但"工业级换商业级"是选型里常见的降档取舍，直接等于"装不上"会误杀真实可用的替代（见 §2.2 第 2 条）。
- E3 的四个变体**只改排序、不改过滤**，所以五个变体的 E4 必须都恒为 0；若某个变体的 E4 不为 0，说明消融开关改错了地方。

## 2. 主数据集（`data/samples/chips_seed.csv`，89 行）

```
芯选 evaluation  |  rows=89  top=5  csv=data/samples/chips_seed.csv
索引构建 377 ms

== 型号替换用例 ==
query          verdict  top1           expected_pins                      hard_failures  elapsed_ms
STM32F103C8T6  PASS     APM32F103C8T6  ['APM32F103C8T6','CH32V203C8T6']   []             4.63
W25Q64JVSSIQ   PASS     GD25Q64ESIG    ['GD25Q64ESIG']                    []             3.53
CH340G         PASS     CH340C         ['CH340C']                         []             3.44
SP3232EEN      PASS     MAX3232ESE+    ['MAX3232ESE+']                    []             3.47
TLC555CDR      PASS     ICM7555IBAZ    ['NE555DR']                        []             3.32
SP3485EN       PASS     MAX3485ESA     ['MAX3485ESA']                     []             3.46
AMS1117-3.3    PASS     LM1117-3.3     ['LM1117-3.3']                     []             4.03

== 自然语言用例（9 条）==
3.3V 低功耗 LDO SOT-23-5  PASS  线性稳压器LDO  SPX3819M5-L-3-3
RS485 收发器 SOIC-8       PASS  接口芯片       SP3485EN
RS232 电平转换             PASS  接口芯片       SP3232EEN
24V 转 5V DC-DC          PASS  DC-DC变换器    LM2596S-5.0
16位 ADC 四通道            PASS  数据转换器      ADS1115IDGSR
EEPROM I2C 32Kbit        PASS  存储器         AT24C32D-SSHM-T
运放 SOIC-8               PASS  运算放大器      MCP6002T-I/SN
光耦 隔离 DIP-4            PASS  光耦           EL817B
MOSFET N沟道 SOT-23       PASS  MOSFET        2N7002K

== 汇总 ==
E1 型号用例           : 7 例（跳过 0 例）
   Top-1 命中         : 6/7 = 85.7%
   Top-5 含任一预期 Pin-to-Pin : 7/7 = 100.0%
   有序性              : 1/1
E1 自然语言用例        : 9 例，空结果 0
   品类正确            : 9/9 = 100.0%
   封装正确            : 2/2 = 100.0%   （Top-1 即要求封装的条数同为 2/2）
E2 单次延迟            : mean 3.86 ms  p95 4.81 ms  max 4.81 ms  (n=7)   ← 多次运行在 3.7–3.9 ms 区间抖动
E4 硬约束违规          : 0/19 条返回结果 = 0.0%  [OK]
```

### 2.1 Top-1 未命中的那 1 例（诚实说明）

`TLC555CDR` 的 Top-1 是 `ICM7555IBAZ`（🟢 Pin-to-Pin 0.729），而标注集把 `NE555DR` 排在第一位。
原因不是排序错误，而是**温度口径**：`TLC555CDR` 是 −40~85℃ 工业级，`NE555DR` 是 0~70℃ 商业级，
覆盖率仅 **56%**，因此 `NE555DR` 被降级为「功能等效需改板」并排到第 2 位；`ICM7555IBAZ` 温度完全覆盖，
更该排第一。**这条用例暴露的是标注口径问题而不是系统缺陷**，因此保留为 Top-1 未命中，不做修饰。
`NE555DR` 仍在 Top-5 内（E1 Top-5 命中 7/7 = 100%）。

### 2.2 评测暴露并已修复的两个真实缺陷

| 缺陷 | 现象 | 修复 |
| --- | --- | --- |
| **硬约束零容忍没有真正落地** | `rules.py` 的 `_hard_checks` 产出的 check 没有 `critical` 字段；`risk.py` 只对类别/EOL/库存判「不推荐」，**封装不同 + 脚位差 > 2 的候选（CH340N SOP-8、TJA1050T、SP3485EN、MAX485ESA+）仍进主榜单**，只在输出里标红 | 给每条 check 加 `critical`（类别/封装/脚位/电压零交集/功能冲突），`risk.py` 改为「命中 `hard_fail` 即落 TIER_NO」；修复后 **E4 违规率 45.7% → 0.0%**，违规候选转入 `rejected` 并在理由里写明命中了哪条硬约束 |
| **温度 fail 被当成"装不上"** | `hard_fail = bool(failed)` 把温度覆盖不足也当成零容忍，导致 `TLC555CDR` 的 `NE555DR`（同封装同脚位、仅温度等级降档）被直接打入不推荐 | `hard_fail` 改为**只由 `critical` 标记决定**；温度 fail 仍是 fail（影响规则分与风险等级），但不再等于"不可推荐"。这与文档 §3.4.2 的校准决定一致 |

修复前后对照（同一台机器、同一份数据）：

| | 修复前 | 修复后 |
| --- | --- | --- |
| E4 硬约束违规 | 16/35 = **45.7%**（[BUG]） | 0/19 = **0.0%**（[OK]） |
| E1 型号 Top-1 | 5/7 = 71.4% | 6/7 = **85.7%** |
| E1 型号 Top-5 | 7/7 = 100% | 7/7 = **100%** |
| E1 NL 品类正确 | 7/9 = 77.8%（2 条是用例品类名写错） | 9/9 = **100.0%** |

## 3. E3 消融实验（`experiments/eval.py --ablate`）

命令行加 `--ablate` 即会额外跑 5 个配置：`full`（完整方案）+ 每次只关闭**一个**机制。
开关落在 `recommend(df, index, query, top_n, ablate=...)` 与 `ranking.rank(query, candidates, ablate=...)`，
取值 `"rules"` / `"supply"` / `"category"` / `"rerank"`；默认空集，行为与不带该参数**完全一致**。

```
== E3 消融对比（每行只关闭一个机制，其余保持完整） ==
variant      part_top1  part_topK  nl_cat  nl_pkg_top1  nl_empty  E4     mean_ms  说明
full         6/7        7/7        9/9     2/2          0         0/19   4.3      完整方案（基准）
no-supply    6/7        7/7        9/9     2/2          0         0/19   4.0      关闭供应链因子（只按参数分排序）
no-rules     5/7        7/7        9/9     2/2          0         0/19   3.9      关闭六维规则分（只按 TF-IDF 相似度排序）
no-category  6/7        7/7        9/9     2/2          0         0/19   4.3      关闭 NL 品类硬过滤与同义词注入
no-rerank    6/7        7/7        9/9     1/2          0         0/19   3.8      关闭 NL 重排（同品类加分/封装族降权/协议重排）

part_top1/part_topK = 型号用例 Top-1 / Top-K 命中数；nl_cat = NL 用例品类正确数；
nl_pkg_top1 = NL 用例里 Top-1 就是要求封装的条数（重排的真正作用点）；
E4 = 返回结果中带零容忍硬约束失败的条数（应恒为 0）。
```

### 3.1 能得出的结论

1. **六维规则分是唯一直接影响 Top-1 的机制**：关掉后型号 Top-1 从 6/7 掉到 5/7（`TLC555CDR` 那条丢失）。
   规则分不是装饰，它把"参数更像但封装/脚位不对"的候选压下去。
2. **NL 重排是唯一影响封装正确性的机制**：关掉后 `nl_pkg_top1` 从 **2/2 掉到 1/2**
   —— `RS485 收发器 SOIC-8` 的 Top-1 会退回 `MAX485ESA+`（SOP-8 5V 器件），而不是要求封装的 `SP3485EN`。
   这条指标是专为消融加的：只看 Top-K 只要有一条命中就永远"看得见"，会掩盖"错的料排第一"。
3. **供应链因子在现有 7+9 条用例上测不出 Top-1 差异**（6/7 → 6/7）。原因是这些用例的替代料供给条件相近，
   供应链的作用场景是"多料同分时的取舍"和"缺货/停产降档"，**需要在用例里专门设计"参数几乎相同、
   但一个缺货一个现货"的对照才能量出来**。这一点如实写在报告中，不夸大。
4. **五个变体的 E4 违规率恒为 0/19**，证明消融只影响排序、不影响零容忍过滤。

### 3.2 消融开关踩过的真实坑（值得写进报告的方法论）

给 `ranking.rank` 的候选元组从 `(sim, cand, rule_res)` 扩成 4 元组 `(sort_sim, cand, rule_res, raw_sim)` 后，
调用点写成 `sim = item[3] if len(item) > 3 else item[0]` —— **索引取反**：NL 模式本该用重排后的 `sort_sim`，
却用了重排前的 `raw_sim`，导致 `RS485 收发器 SOIC-8` 的 Top-1 从 `SP3485EN`(0.8152) 掉成 `MAX485ESA+`(0.4885)，
`3.3V 低功耗 LDO SOT-23-5` 从 `SPX3819M5-L-3-3` 掉成 `AMS1117-3.3`(SOT-223)。
定位方式是在候选循环里用环境变量 `XINXUAN_DEBUG` 打开 stderr 打点，打印 `raw/sort/soft/supply/score` 逐层比对。
修复是让 `rank` 固定 `sim = item[0]`，并在 docstring 里显式写明"第 1 个元素参与排序、第 4 个元素只供 `--ablate rerank` 还原基准"。
**教训：给有序元组追加字段时，索引语义必须写进 docstring，否则极易取反。**

## 4. 真实数据集（`data/chips_real_semi.csv`，20,890 行）

```
芯选 evaluation  |  rows=20890  top=5
索引构建 4695 ms
E1 型号用例           : 1 例（跳过 6 例，数据集缺料）
   Top-5 含任一预期 Pin-to-Pin : 1/1 = 100.0%
E1 自然语言用例        : 9 例，空结果 1；品类正确 0/9
E2 单次延迟            : mean 39.78 ms
E4 硬约束违规          : 0/5 条返回结果 = 0.0%  [OK]
```

**必须如实写进技术报告的三条结论**：

1. **真实快照不适合作为"芯片替代选型"的主数据源**。`data/chips_real_semi.csv` 是从 jlcparts 日更快照
   （`dougy83.github.io`，55,123 条）按半导体/IC 白名单抽出的子集，但它的品类分布由**连接器与无源件主导**
   （全量 54,134 行里 Connectors 占 17,647），IC 品类本身规模很小（Power Management 2,087、Interface ICs 551、
   Embedded Processors 349）。**7 条型号替换用例里有 6 条的料号在快照中根本不存在**（STM32F103C8T6、CH340G、
   SP3232EEN、TLC555CDR、W25Q64JVSSIQ、AMS1117-3.3），只能 SKIPPED。
2. **中文查询打不动英文库**。全量集的 `description` 是英文，而查询与同义词表是中文，TF-IDF 召回的
   candidate pool（`max(top*4, 20)`）里往往没有同品类候选。为缓解这一点，本轮给 `rules.py` 增加了
   `CATEGORY_SYNONYMS_EN`（22 条英文品类 → 中文口语别名），并在 `recommend.py` 增加
   `resolve_category(df, raw)` 把中文品类标签对齐到当前数据集的实际取值 —— 修复后
   `3.3V 低功耗 LDO SOT-23-5` → `Power Management` / `MIC5205-3.3YM5-MS`、
   `RS485 收发器 SOIC-8` → `Interface ICs` / `CS485S`、`EEPROM I2C 32Kbit` → `Memory` / `24C32-HXY`，
   品类过滤不再落空（修复前这 6 条全部 0 结果）。但**跨语言语义召回仍然很弱**（`运放 SOIC-8` 依然空结果），
   仍需中文品类词典扩充或中文 embedding，属于文档 §6 列出的增强路径。
3. **真实数据源缺两类关键字段**：**交期与生命周期（NRND/EOL）在整个 jlcparts 快照中都不存在**
   （`Status` 属性全库只有 `Active` 一种取值），引脚数只有 14.3% 的可得率（只能从封装串正则解析）。
   因此交付用的 `chips_seed.csv` 里 `lead_time_days` / `lifecycle` 是**人工整理的演示字段**，
   报告与演示视频必须声明，不能声称来自实时供应链。

## 5. 复现命令

```powershell
# 1) 依赖（本机沙箱下 pip 不可用，用仓库自带安装器）
& $py scripts\fetch_deps.py --target .deps

# 2) 主数据集评测（含 E1/E2/E4）
$env:PYTHONPATH = "$pwd\.deps"
& $py experiments\eval.py --json docs\refs\eval-seed.json

# 2b) 追加 E3 消融对比（5 个配置）
& $py experiments\eval.py --ablate --json docs\refs\eval-seed.json

# 3) 真实数据集（需先下载 tar 并构建）
& $py scripts\fetch_dataset.py                       # 需要外网环境
& $py scripts\build_dataset.py --categories semi --out data\chips_real_semi.csv
& $py experiments\eval.py --csv data\chips_real_semi.csv --json docs\refs\eval-real-semi.json
```

## 6. 未做 / 下一步

- **供应链因子的消融还缺对应用例**：现有 7+9 条用例测不出 `no-supply` 的差异（见 §3.1 第 3 条），
  需要新增"参数几乎相同、但一个缺货/停产、一个现货"的对照用例，才能把供应链加权的贡献量出来。
- **标注集仍是 7 + 9 条**，规模偏小，统计意义有限；扩到 50+ 条需要在项目 A 步骤内补齐（文档 §4 的 L1 策略）。
- **评测器与被测系统共享品类词典**：NL 用例的 `expected category` 目前是硬编码的单一品类名，
  在英文数据集上必然 0 命中。更严谨的做法是让评测器独立于被测词表（人工标注 category 取值），留待标注集扩充时一并做。
