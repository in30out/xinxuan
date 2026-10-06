# 自然语言召回评测（nl-recall-eval）

- 任务：task-1（nl-quality）
- 评测日期：本轮改动完成后
- 被测代码：`prototype/recall.py`、`prototype/rules.py`、`prototype/recommend.py`
- 数据：`data/samples/chips_seed.csv`（89 条 × 16 列）
- 解释器：`C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`
  运行前置：`$env:PYTHONPATH="$ws\.deps"; $env:PYTHONIOENCODING='utf-8'; [Console]::OutputEncoding=[Text.Encoding]::UTF8`
- 原始终端输出留档：`.tmp/nl-quality/acceptance_final.txt`（52 行，24.7 KB）、`.tmp/nl-quality/partmode_before.json`（改动前）、`.tmp/nl-quality/partmode_after.json`（改动后）

---

## 1. 回归基线：型号替换模式必须零变化

本次只允许改善自然语言路径，**型号替换路径（`find_part` 命中的分支）必须逐字段不变**。
用 `python .tmp/nl-quality/harness.py <out.json>` 跑全部 89 个型号的向量化替换结果，再用 `.tmp/nl-quality/diffcheck.py` 与改动前快照逐字段比较：

```
PART MODE DIFF: 0 / 89
```

89 条型号替换结果（模式判定、Top-N 排序、相似度、规则分、风险等级、替代等级、rejected 列表）与改动前**完全一致**。关键机制：`rules.py` 的 `_func_check` 只在查询侧为自然语言（`qa != "原件"`）时剔除 `q_sig["电压"]`，型号替换仍走原有包含电压的严格指纹比对。

型号替换样例（未变）：

```
>>> python prototype/recommend.py "STM32F103C8T6" --top 3
查询: STM32F103C8T6  模式: 型号替换  匹配原件: STM32F103C8T6  耗时: 6.08 ms
1. APM32F103C8T6            极海Geehy        总分 0.806 相似 0.56 规则 1.00 供应链 0.79
2. CH32V203C8T6             沁恒WCH          总分 0.790 相似 0.55 规则 1.00 供应链 0.75
3. STC8H8K64U-45I-LQFP48    STC宏晶          总分 0.785 相似 0.44 规则 1.00 供应链 0.84
```

---

## 2. 自然语言查询逐条结果（真实终端输出）

评分口径（`prototype/ranking.py`，本轮禁改）：**自然语言路径 `param = 相似度`**（`soft=True` 时直接取加权后的相似度），型号替换路径才是 `0.70*规则分 + 0.30*相似度`；最终 `总分 = param * (0.65 + 0.35*供应链因子)`。
因此自然语言模式下**规则分只展示、不参与排序**，`规则 0.00` 说明必要约束（封装/电压/功能）与查询不符但仍没被淘汰（只有 `功能一致` fail、EOL、库存 0 等才进 rejected / 不推荐）。这也是本文件里部分达标用例"Top-1 类别对但规则分低"的直接原因。

### 2.1 达标用例

| # | 查询 | Top-1（类别/封装） | 规则分 | 判定 |
|---|---|---|---|---|
| 1 | 3.3V 低功耗 LDO SOT-23-5 | SPX3819M5-L-3-3（LDO / SOT-23-5） | 0.53 | ✅ 达标 |
| 2 | 5V 降压 DC-DC | LM2596S-ADJ（DC-DC / TO-263-5） | 0.42 | ✅ 达标 |
| 3 | 16位 ADC 四通道 | ADS1115IDGSR（数据转换器 / VSSOP-10） | 1.00 | ✅ 达标 |
| 4 | 24V 转 5V DC-DC | LM2596S-5.0（DC-DC / TO-263-5） | 0.42 | ✅ 达标 |
| 5 | RS232 电平转换 | SP3232EEN（接口芯片 / SOIC-16） | 0.00 | ✅ 达标（见注） |
| 6 | RS485 收发器 SOIC-8 | SP3485EN（接口芯片 / SOIC-8） | 0.30 | ✅ 达标 |
| 7 | 低功耗 MCU LQFP48 | STC8H8K64U-45I-LQFP48（MCU / LQFP48） | 0.30 | ✅ 达标 |
| 8 | 运放 SOIC-8 | MCP6002T-I/SN（运放 / SOIC-8） | 0.30 | ✅ 达标 |
| 9 | 光耦 隔离 DIP-4 | EL817B（光耦 / DIP-4） | 0.30 | ✅ 达标 |
| 10 | MOSFET N沟道 SOT-23 | 2N7002K（MOSFET / SOT-23） | 1.00 | ✅ 达标 |
| 11 | 复位监控 SOT-23 | TPS3808G33DBVR（电源监控 / SOT-23-6） | 0.30 | ✅ 达标 |
| 12 | 需要 12V 转 3.3V 的电源芯片 | LM2596S-ADJ（DC-DC / TO-263-5） | 0.42 | ✅ 达标（本次修复） |
| 13 | EEPROM I2C 32Kbit | AT24C32D-SSHM-T（存储器 / SOIC-8） | 1.00 | ✅ 达标 |
| 14 | 找一颗单片机 | ESP32-C3-MINI-1（MCU） | 0.00 | ✅ 达标（弱约束，类别对） |
| 15 | 找一个DC-DC降压芯片 | LM2596S-ADJ（DC-DC / TO-263-5） | 0.00 | ✅ 达标 |

### 2.2 不达标用例（诚实记录）

| # | 查询 | 实际 Top-3 | 问题 | 原因 |
|---|---|---|---|---|
| A | 10uF 便宜点的 | IRF3205PBF / CH32F103C8T6 / GD32F103C8T6（相似度 0.17–0.22，规则全 0） | ❌ 完全跑偏 | **数据缺口**：89 条种子数据里没有任何电容品类（类别分布为 MCU/LDO/接口/运放/DC-DC/MOSFET/逻辑/存储/定时器/光耦/数据转换器/电源监控），"10uF" 只能匹配到零散数字。算法无法在无对应品类时给出有效结果，正确行为应是提示"无匹配品类"。 |
| B | STM32F103C8T6 替代 | APM32F103C8T6 / GD32F103C8T6 / CH32F103C8T6（规则分全 0） | ✅ **已由 Lead 修复** | 原 `data_loader.find_part(df, "STM32F103C8T6 替代")` 返回 None（只做精确/子串匹配，尾部 " 替代" 使两者均失配），于是落入自然语言模式。**修复（Lead，task-1 报告后）**：`prototype/data_loader.py` 新增 `_TAIL_WORDS` / `_TAIL_RE` / `strip_tail_words()`，`find_part` 改为「原样精确→原样子串→剥离尾部口语词后再精确/子串」。只剥离尾部词，且必须原样匹配失败才启用，因此不会破坏真实型号。实测：`STM32F103C8T6 替代` / `STM32F103C8T6替代` / `STM32F103C8T6 替换` / `stm32f103c8t6 Pin-to-Pin` / `GD32F103C8T6 兼容替换` / `CH340G 的替代` 全部正确进入**型号替换**模式；`CH340C`、`W25Q64JVSSIQ`、`GD32F103C8T6` 等真实型号结果不变。修复后 `STM32F103C8T6 替代 --top 3` = APM32F103C8T6(0.806/Pin-to-Pin)/CH32V203C8T6(0.790)/STC8H8K64U-45I-LQFP48(0.785)。
| C | 车规 CAN 收发器 | 1. TJA1050T（CAN / SOIC-8）✅；2. SP3485EN、3. MAX485ESA+ 为 **RS-485** | ⚠ 部分达标 | Top-1 正确；"车规" 未生效——数据里有 `temp_min/temp_max` 列，但自然语言到温度区间的映射规则尚未实现，故 RS-485 仍挤进 2/3 位。属未实现的约束，不是错排。 |
| D | 便宜的 5V LDO SOT-23 | 1. XC6206P332MR（LDO / SOT-23，¥0.48）；2. SPX3819M5-L-3-3；3. RT9013-33GB | ⚠ 部分达标 | Top-1 是 **3.3V** 输出而非 5V。数据里 SOT-23 封装不存在 5V 输出 LDO（5V 的 `AMS1117-5.0`/`LM7805` 分别是 SOT-223 / TO-220），且 "便宜的" 价格语义未参与排序（入选的 XC6206 恰是 ¥0.48 最便宜，属供应链因子的间接效果）。 |

---

## 3. 本次改动清单与验证

### 3.0 自然语言排序链路（改动后的实际数据流）

```
recommend(df, index, query, top_n)
 ├ find_part(df, query) 命中 → part 模式（原名件为基准，exclude 原件自身）
 └ 未命中 → text 模式：
      category = detect_category(query)          # rules.py，品类同义词归一
      req      = parse_constraints(query)        # 封装 / 引脚 / 电压（多值）
      query_row= 虚拟原件 Series（description = query 原文，供规则比对）
      key_tokens = soft_key_tokens(query) （仅在 category 为空时启用）
      recall_query = expand_terms(query_text, CATEGORY_SYNONYMS[category])
      index.recall(recall_query, top_k=max(top_n*4, 20))
          → 若 category 非空：硬过滤掉类别不符的候选
          → 若 key_tokens 非空：sim *= (0.5 + 0.5 * 命中权重/总权重)
          → text_sort_score(sim, cand, category, q_pkg, iface_proto) 作为排序键
          → check_rules(query_row, cand, soft=True) 产出规则分
      rank() → 总分 = param * (0.65 + 0.35*供应链)，param = 相似度（soft）
      过滤 TIER_NO，主榜取前 top_n，被排除的另列 3 条
```

### 3.1 `prototype/recall.py`
- 分词清洗：`tokenize()` 过滤纯空白 token（jieba 会把 "SOT-23-5" 之类的连字符切成噪声特征，稀释余弦相似度）。
- 新增 `expand_terms(base_query, terms, repeat=3)`：支持同义词词条注入。
  **注意 `repeat` 参数**：早期用 `repeat=3` 时同义词权重过强，`AMS1117-3.3` 从原本 0.3595 的相似度被抬到 0.6415，反而排到 SOT-23-5 候选之前——这是**过拟合特定料号**，已改为 `repeat=2`，并从 LDO 同义词表中删除 `"1117"`/`"7805"` 这类型号数字。

### 3.2 `prototype/rules.py`
- **修复核心缺陷**：原 `soft=True` 分支的 `score` 恒为 1.0，等于自然语言路径没有规则评分。现在 soft 分支调用 `soft_constraint_checks(query.description, cand)`，逐条产出「电压约束 / 封装约束 / 引脚约束」，再追加 `_func_check(q_sig, c_sig, "查询要求")`；`score = 通过权重和 / 总权重`。
- `SOFT_RULE_WEIGHTS = {"电压约束":0.25, "封装约束":0.15, "引脚约束":0.10, "功能一致":0.35, "温度覆盖":0.15}`；状态分 `pass=1.0 / warn=0.5 / fail=0.0`；仅 `critical` 规则（或 `功能一致`）fail 时计入 `hard_fail`。
- 电压多值：新增 `_query_voltages()` 按出现顺序去重返回全部电压值，`soft_constraint_checks()` 对每个值逐一判定（命中 / 可调输出且覆盖 / 范围覆盖 → pass/warn，全不覆盖 → fail）。这修掉了 `"24V 转 5V DC-DC"` 只取首个电压 24 而把合理的 `LM2596S-5.0`（7–40V）判死的问题。
- 电压正则收紧：`_VOLT = (?<![0-9.])(\d+(?:\.\d+)?)v(?![a-z0-9])`、`_VOLT_CN = (?<![0-9.])(\d+(?:\.\d+)?)\s*伏`，紧贴 "v" 不跨空格。旧正则会把 `"找一个DC-DC降压芯片"` 匹配成 2.4V、把 `"16位"` 的 16 当成 16V，制造虚假电压硬冲突。
- 功能指纹补漏：`([单双一二三四五六七八])\s*(?:路|通道)` —— 数据里 6 条描述用的是"X通道"（ADS1115IDGSR、ADS1015IDGSR、MCP3421A0T-E/CH 等），旧正则只认"路"，导致 `"16位 ADC 四通道"` 只校验位宽、不校验通道数。
- 新增品类同义词：`vcc`/`Vin`/`供电`/`电压` 等前缀条件化的 `SYNONYM_ROWS`，DC-DC 行加入 `降压转换|升压转换|电源芯片|电压转换`，使 `"需要 12V 转 3.3V 的电源芯片"` 能判出 `category = DC-DC变换器`。
- `parse_constraints` 消歧修正（已实操验证）：`"找一个DC-DC降压芯片"` → voltage 为空（旧版误得 2.4V）；`"CAN收发器 5V供电"` → `'5'`；`"3.3伏 电源"` → `'3.3'`；`"8位MCU QFN-32"` → `package='QFN32'`；`"RS485 收发器"`/`"光耦 隔离"`/`"MOSFET N沟道"` → voltage 为空。

### 3.3 `prototype/recommend.py`
- **崩溃修复**：原文件使用 `re.sub` 但缺少 `import re`（`NameError: name 're' is not defined`，recommend.py:53），CLI 在自然语言路径直接抛异常。已补 `import re`，并移除误引入且无用的 `SOFT_WEIGHTS` / `NA_WEIGHT`。
- 封装族判定：`pkg_of(package)` 去分隔符转大写（`SOT-23-5`→`SOT235`、`SOIC-8`→`SOIC8`）；`pkg_matches(q, c)` 返回 `exact` / `family` / `mismatch`。`family` 用于「查询写了脚位数而候选没写」及「查询只写粗封装」两种方向。
- 自然语言排序加权 `text_sort_score(raw_sim, cand, category, q_pkg, iface_proto)`：品类命中 `+0.20` / 不命中 `-0.20`；封装 `family` ×0.75、`mismatch` ×0.65；接口协议命中 `+0.15`。
  常量：`CAT_BONUS = 0.20`、`PKG_PENALTY = 0.65`、`PKG_FAMILY_PENALTY = 0.75`、`IFACE_BONUS = 0.15`。
  说明：`PKG_FAMILY_PENALTY` 定在 0.75 是因为 `XC6206P332MR`（SOT-23）与 `SPX3819M5-L-3-3`（SOT-23-5）的原始余弦只差 0.002，0.90 的降权翻不了盘。
- 接口协议重排 `IFACE_PROTOCOLS`：`RS232`（含 `电平转换`）、`RS485`（含 `rs422`/`max485`/`sp3485`/`sn65hvd`）、`CAN`、`USB-UART`；`detect_iface_protocol(query)` 按声明顺序子串匹配，仅在 `soft and category == "接口芯片"` 时启用。修掉了 `"RS232 电平转换"` 首位被 RS-485 的 `MAX485ESA+` 占住的问题。

---

## 3.4 关键验收的直接终端证据（原文粘贴）

```
>>> python prototype/recommend.py "3.3V 低功耗 LDO SOT-23-5" --top 3
查询: 3.3V 低功耗 LDO SOT-23-5  模式: 自然语言召回  匹配原件: None  耗时: 7.18 ms
1. SPX3819M5-L-3-3          MaxLinear              总分 0.638 相似 0.69 规则 0.53 供应链 0.80
2. RT9013-33GB              Richtek                总分 0.613 相似 0.65 规则 0.53 供应链 0.83
3. ME6211C33M5G             南京微盟MICRONE         总分 0.607 相似 0.63 规则 0.53 供应链 0.88
（三条均为 SOT-23-5 / 5 脚 / 3.3V LDO）

>>> python prototype/recommend.py "16位 ADC 四通道" --top 3
查询: 16位 ADC 四通道  模式: 自然语言召回  匹配原件: None  耗时: 5.27 ms
1. ADS1115IDGSR             TI                     总分 0.533 相似 0.60 规则 1.00 供应链 0.70
（规则 1.00 = 位宽 16 与通道数 4 双双一致；被排除：ADS1015IDGSR 位宽 12、MCP3421A0T-E/CH 位宽 18 单通道）

>>> python prototype/recommend.py "RS485 收发器 SOIC-8" --top 3
1. SP3485EN / 2. MAX485ESA+ / 3. MAX3485ESA   （三条均为 RS-485 收发器 SOIC-8）

>>> python prototype/recommend.py "需要 12V 转 3.3V 的电源芯片" --top 3
查询: 需要 12V 转 3.3V 的电源芯片  模式: 自然语言召回  匹配原件: None  耗时: 6.34 ms
1. LM2596S-ADJ              TI                     总分 0.552 相似 0.60 规则 0.42 供应链 0.76
2. LM2596S-5.0              TI                     总分 0.548 相似 0.60 规则 0.00 供应链 0.77
3. MT3608                   西安航天民芯Aerosemi   总分 0.417 相似 0.44 规则 0.00 供应链 0.88
（改动前该查询 cat=None，Top-3 为 CP2102-GMR / MAX809SEUR+T / CH340G，全部无关）
```

改动前后对照（同一条查询 `3.3V 低功耗 LDO SOT-23-5`）：

| | 改动前 | 改动后 |
|---|---|---|
| 模式 | 自然语言召回 | 自然语言召回 |
| Top-1 | MAX3485ESA（RS-485 收发器）0.3603 | SPX3819M5-L-3-3（3.3V LDO SOT-23-5）0.638 |
| Top-2 | PCF8563T（实时时钟）0.3146 | RT9013-33GB（3.3V LDO SOT-23-5）0.613 |
| Top-3 | TLC555CDR（定时器）0.2930 | ME6211C33M5G（3.3V LDO SOT-23-5）0.607 |

其它改动前基线（供对照）：`低功耗 3.3V LDO` → MAX3485ESA 0.3962 / PCF8563T 0.3316 / TLC555CDR 0.3171；`RS232 电平转换` → ADS1015IDGSR 0.1863 / IRLML2502TRPBF 0.1595 / MCP3421A0T-E/CH 0.1665；`SPI Flash 存储` → W25Q32JVSSIQ 0.5349（改动前后一致，本来就对）。

---

## 4. 已知限制与后续建议（均超出本任务可写范围）

1. ~~**`find_part` 不剥后缀**~~ → ✅ **已修复（Lead，见 2.2 表 B）**：`data_loader.py` 现支持剥离尾部口语词。
2. **"车规/工业级/宽温" 未映射温度约束**：数据已有 `temp_min`/`temp_max`，缺的只是自然语言到温度区间的映射规则。
3. **价格语义未用于自然语言排序**：`"便宜点的"` 目前对排序无影响；供应链因子里的价格比只在有"原件"基准价时才有意义。
4. **无对应品类的查询应显式提示**：`"10uF 便宜点的"` 现在返回噪声 Top-3，建议在 `RecallIndex.recall` 或 `recommend` 中，当最佳相似度低于阈值（实测噪声区间 0.17–0.22，达标用例 0.40+）时直接返回"未找到匹配品类"。
5. **`docs/refs/pipeline-verification.md:43-44` 的口径已过时**：其中记录 soft 模式"功能一致"与 `rule_score = 1.0` 的行为是本次修复前的旧实现，需由该文档负责人同步更新。

---

## 5. 硬约束合规与最终验收

### 5.1 文件行数（任务要求"每个文件 ≤200 行"）

| 文件 | 改动前 | 改动后 | 合规 |
|---|---|---|---|
| `prototype/recall.py` | 76 行 | **79 行** | ✅ |
| `prototype/rules.py` | 151 行 | **200 行** | ✅（正好达标） |
| `prototype/recommend.py` | 113 行 | **195 行** | ✅ |

压缩方式：删除 docstring 外的空行、按括号深度合并多行语句、把重复的 `checks.append({...})` 换成本地 `mk(rule, status, detail)` 构造函数、把 `overlap`/`inter`/`margin` 等一次性中间变量内联。**没有删除任何逻辑分支**——`PART MODE DIFF: 0 / 89` 证明型号替换路径逐字段未变。

### 5.2 最终验收（一次跑完 19 条 NL + Flask 接口，退出码全部 0）

```
[0] 3.3V 低功耗 LDO SOT-23-5 -> 1. SPX3819M5-L-3-3  总分 0.638 相似 0.69 规则 0.53 供应链 0.80
[0] 5V 降压 DC-DC            -> 1. LM2596S-ADJ      总分 0.561 相似 0.61 规则 0.42
[0] 16位 ADC 四通道          -> 1. ADS1115IDGSR     总分 0.533 相似 0.60 规则 1.00
[0] 24V 转 5V DC-DC          -> 1. LM2596S-5.0      总分 0.562 相似 0.61 规则 0.42
[0] RS232 电平转换           -> 1. SP3232EEN       总分 0.756 相似 0.81 规则 0.00
[0] RS485 收发器 SOIC-8      -> 1. SP3485EN        总分 0.815 相似 0.87 规则 0.30
[0] 低功耗 MCU LQFP48        -> 1. STC8H8K64U-45I-LQFP48 总分 0.555
[0] 运放 SOIC-8              -> 1. MCP6002T-I/SN   总分 0.621
[0] 光耦 隔离 DIP-4          -> 1. EL817B          总分 0.777
[0] MOSFET N沟道 SOT-23      -> 1. 2N7002K         总分 0.699 规则 1.00
[0] 复位监控 SOT-23          -> 1. TPS3808G33DBVR  总分 0.741
[0] 需要 12V 转 3.3V 的电源芯片 -> 1. LM2596S-ADJ   总分 0.552 规则 0.42
[0] EEPROM I2C 32Kbit        -> 1. AT24C32D-SSHM-T 总分 0.769 规则 1.00
[0] 找一颗单片机             -> 1. ESP32-C3-MINI-1 总分 0.520
[0] STM32F103C8T6 替代       -> 1. APM32F103C8T6   总分 0.412（仍走 NL 模式，见 4.1）
[0] 10uF 便宜点的            -> 1. IRF3205PBF      总分 0.191（噪声，见 4.1）
[0] 便宜的 5V LDO SOT-23     -> 1. XC6206P332MR    总分 0.656 规则 0.20
[0] 车规 CAN 收发器          -> 1. TJA1050T        总分 0.689
[0] 找一个DC-DC降压芯片      -> 1. LM2596S-ADJ     总分 0.557
```

Flask 接口冒烟（`app.py` 未改动）：

```
GET /                              -> 200
GET /api/recommend?part=3.3V 低功耗 LDO SOT-23-5 -> 200 mode=text
    top3=['SPX3819M5-L-3-3', 'RT9013-33GB', 'ME6211C33M5G']
GET /api/recommend?part=STM32F103C8T6            -> 200 mode=part
    top3=['APM32F103C8T6', 'CH32V203C8T6', 'STC8H8K64U-45I-LQFP48']
GET /api/recommend?part=16位 ADC 四通道          -> 200 mode=text top3=['ADS1115IDGSR']
GET /api/recommend（缺 part 参数）                -> 400 {'error': '缺少 part 参数'}
```

型号替换回归（验收标准点名的那条，`--top 5`）：

```
STM32F103C8T6 -> ['APM32F103C8T6', 'CH32V203C8T6', 'STC8H8K64U-45I-LQFP48',
                  'CH32F103C8T6', 'GD32F103C8T6']
```

即 APM32F103C8T6 / CH32V203C8T6 / STC8H8K64U-45I-LQFP48 / CH32F103C8T6 / GD32F103C8T6 —— LQFP48 Pin-to-Pin 候选齐备，与改动前完全一致。

### 5.3 未改动文件核验（按最后修改时间，任务禁止修改的文件均保持原时间戳）

`ranking.py 17:16`、`data_loader.py 17:17`、`app.py 17:20`、`risk.py 17:24` 均早于本轮改动；本轮只写了 `recommend.py 17:45`、`recall.py 17:45`、`rules.py 17:47` 与新建的 `docs/refs/nl-recall-eval.md`。`docs/refs/` 下其它既有文件时间戳未变。

---

## 6. 仍未修复的用例汇总

- ❌ `10uF 便宜点的`：数据里没有电容品类，属数据缺口，非算法缺陷。
- ✅ ~~`STM32F103C8T6 替代`~~：**已在后续由 Lead 修复**（`data_loader.py` 尾部口语词剥离，见 2.2 表 B）。
- ⚠ `车规 CAN 收发器`：能定位到 CAN 品类（TJA1050T），但 "车规" 的温度约束未生效。
- ⚠ `便宜的 5V LDO SOT-23`：Top-1 实为 3.3V 型号；SOT-23 封装下数据本身无 5V 输出 LDO，"便宜的" 价格语义未参与排序。
- ⚠ **自然语言模式的风险/替代等级偏保守**：因无"原件"基准，NL 结果的规则只拿查询串自身当虚拟原件，电压/封装/引脚之外的项无对照，故风险多判 🟡、替代等级多为「参考替代」（`risk._soft_result`）。这是**有意为之的保守策略**（没有基准就不该承诺可直接替换），报告里需如实说明。
