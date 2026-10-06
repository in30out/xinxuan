# 芯选 —— 原型真实运行记录（原型链 v1）

> 本文档所有命令均在 `C:\MyFiles\Develop\dsh\work_1` 下真实执行，输出为终端原始内容（仅去掉 jieba 首次加载 stderr 的重复行）。
> 采集时间：2026-10-05。

## 0. 时效性说明（2026-10-06 追加，必读）

本文档 §1~§6 的终端输出采集于 **2026-10-05**，其中**相似度与总分绝对值已过时**：Lead 随后修复了 `recall.tokenize()` 的契约缺陷（原返回空格连接的字符串，被 sklearn `_word_ngrams` 按**字符**切片，1-2gram 退化；现返回 token 列表、token 内空白换下划线、丢弃单字符 ASCII token）。修复后相似度量级整体下降，**当前权威基线请看 `docs/refs/eval-report.md`**；本文档中仍然有效的是：命令与退出码、耗时量级、HTTP 状态码/字节数、规则拦截行为、`p2p_with` 关系结论、环境与踩坑记录。

另外两处改名/新增：`prototype/app.py` 已拆分为**应用本体 `prototype/wsgi.py`** + 转发壳 `prototype/app.py`（`app` 模块名会与 PyPI 无关发行版撞车，实测 `ImportError: cannot import name 'VERSION' from 'app'`）；`recall.py` 另增纯 numpy 的 `_NumpyTfidf` 兜底路径（`XINXUAN_VECTORIZER=sklearn|numpy` 可强制）。

**Lead 修复后我重测的当前基线**（同一命令，实测）：

```
python prototype/recommend.py STM32F103C8T6 --top 3     耗时: 25.32 ms
1. APM32F103C8T6            总分 0.726 相似 0.27 规则 1.00 供应链 0.79
2. STC8H8K64U-45I-LQFP48    总分 0.708 相似 0.17 规则 1.00 供应链 0.84
3. CH32V203C8T6             总分 0.689 相似 0.19 规则 1.00 供应链 0.75
```

**我的独立交叉验证（真实执行，exit 0）**：`scripts/compare_vectorizer.py` → `Top-5 顺序完全一致: 10/10` / `相似度最大相对误差: 2.429e-06` / `VECTORIZER_MATCH_OK`；`scripts/_check_api.py` → 7 组接口冒烟全 OK，耗时 1.50s，`SMOKE_OK`。

## 1. 运行环境与解释器

| 项 | 值 |
| --- | --- |
| 解释器 | `C:\Users\13718\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe` |
| Python | 3.12.14 |
| numpy / pandas | 2.3.5 / 3.0.1（解释器自带） |
| 附加依赖 | `<ws>\.deps`（scikit-learn 1.9.1、scipy 1.18.1、jieba 0.42.1、Flask 3.1.3、flask-cors 6.0.5 等） |
| 样例数据 | `data/samples/chips_seed.csv`，CSV 侧 89 行 × 16 列（第 16 列 `p2p_with` 为人工引脚兼容关系）；加载后 DataFrame 17 列（`desc_text` 为召回用衍生列，不落盘） |

运行前设置（中文输出必须，否则控制台乱码）：

```powershell
$env:PYTHONPATH="C:\MyFiles\Develop\dsh\work_1\.deps"
$env:PYTHONIOENCODING="utf-8"
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
```

## 2. CLI 链路：型号替换

### 2.1 `python prototype/recommend.py STM32F103C8T6 --top 3`

```
查询: STM32F103C8T6  模式: 型号替换  匹配原件: STM32F103C8T6  耗时: 5.83 ms
------------------------------------------------------------------------------------------------------------
1. APM32F103C8T6            极海Geehy                总分 0.806 相似 0.56 规则 1.00 供应链 0.79
   🟢低风险 | Pin-to-Pin 直接替换 | LQFP48/48脚 | 库存 5400 | ¥9.20 | 交期 12天 | 量产
   理由: APM32F103C8T6（极海Geehy）；关键规则全部达标；库存 5400 颗/单价 ¥9.20/交期 12 天；供应链因子 0.79；可 Pin-to-Pin 直接替换
2. CH32V203C8T6             沁恒WCH                  总分 0.790 相似 0.55 规则 1.00 供应链 0.75
   🟢低风险 | Pin-to-Pin 直接替换 | LQFP48/48脚 | 库存 3100 | ¥5.80 | 交期 20天 | 量产
   理由: CH32V203C8T6（沁恒WCH）；关键规则全部达标；库存 3100 颗/单价 ¥5.80/交期 20 天；供应链因子 0.75；可 Pin-to-Pin 直接替换
3. STC8H8K64U-45I-LQFP48    STC宏晶                  总分 0.785 相似 0.44 规则 1.00 供应链 0.84
   🟢低风险 | 功能等效需改板 | LQFP48/48脚 | 库存 12000 | ¥4.20 | 交期 6天 | 量产
   理由: STC8H8K64U-45I-LQFP48（STC宏晶）；关键规则全部达标；库存 12000 颗/单价 ¥4.20/交期 6 天；供应链因子 0.84；功能等效，需修改 PCB 布局或固件
------------------------------------------------------------------------------------------------------------
⚠ 规则已排除的候选（同系列但不可直接选用，列出以备核对）:
   ✗ LM358DR                  🟡中风险 | 不推荐 | 相似 0.29 | 库存 42000 | 量产 | 类别不同，仅可作为功能参考，需重新设计外围电路
   ✗ TS321ILT                 🟡中风险 | 不推荐 | 相似 0.23 | 库存 7600 | 量产 | 类别不同，仅可作为功能参考，需重新设计外围电路
   ✗ LM7805                   🔴高风险 | 不推荐 | 相似 0.23 | 库存 15000 | 量产 | 类别不同，仅可作为功能参考，需重新设计外围电路
EXIT=0
```

要点：同封装同脚数的国产 MCU 全部命中；`STC8H8K64U` 参数全过但描述里没有"引脚兼容"声明，因此判为 **功能等效需改板** 而不是 Pin-to-Pin；类别不同的运放/稳压器被规则拦到"已排除"列表，没有静默丢弃。

### 2.2 `python prototype/recommend.py AMS1117-3.3 --top 3`

```
查询: AMS1117-3.3  模式: 型号替换  匹配原件: AMS1117-3.3  耗时: 6.78 ms
1. LM1117-3.3               TI                     总分 0.853 相似 0.75 规则 1.00 供应链 0.78
   🟢低风险 | Pin-to-Pin 直接替换 | SOT-223/3脚 | 库存 18000 | ¥1.05 | 交期 10天 | 量产
2. AMS1117-5.0              AMS                    总分 0.733 相似 0.90 规则 0.70 供应链 0.90
   🔴高风险 | 参考替代 | SOT-223/3脚 | 库存 52000 | ¥0.31 | 交期 3天 | 量产
   理由: AMS1117-5.0（AMS）；不达标规则: 功能一致；…；仅供参考替代，需完整评估
3. AZ1117-1.8               DIODES                 总分 0.715 相似 0.66 规则 0.80 供应链 0.83
   🔴高风险 | 参考替代 | SOT-223/3脚 | 库存 11000 | ¥0.35 | 交期 5天 | 量产
   理由: AZ1117-1.8（DIODES）；不达标规则: 功能一致；…；仅供参考替代，需完整评估
⚠ 规则已排除的候选（同系列但不可直接选用，列出以备核对）:
   ✗ LD1117S33TR              🔴高风险 | 不推荐 | 相似 0.49 | 库存 0 | EOL | 原厂已停产（EOL），仅可做最后购买，不建议新设计采用
   ✗ LM2596S-5.0              🔴高风险 | 不推荐 | 相似 0.36 | 库存 6200 | 量产 | 类别不同，仅可作为功能参考，需重新设计外围电路
   ✗ LM2596S-ADJ              🟡中风险 | 不推荐 | 相似 0.34 | 库存 4800 | 量产 | 类别不同，仅可作为功能参考，需重新设计外围电路
EXIT=0
```

要点：**"无替代 / 必须报警"场景已复现** —— `LD1117S33TR` 相似度第 2（0.49）但 lifecyle=EOL 且库存 0，被判 🔴/不推荐并移出主榜；`AMS1117-5.0` 相似度最高（0.90）却因输出电压与原型号冲突（功能一致 fail）降为 🔴/参考替代，说明"纯相似度排序"会被规则纠正。

### 2.3 `python prototype/recommend.py W25Q64JVSSIQ --top 3`

```
查询: W25Q64JVSSIQ  模式: 型号替换  匹配原件: W25Q64JVSSIQ  耗时: 6.23 ms
1. GD25Q64ESIG              兆易创新GigaDevice         总分 0.846 相似 0.66 规则 1.00 供应链 0.84
   🟢低风险 | Pin-to-Pin 直接替换 | SOIC-8/8脚 | 库存 14000 | ¥2.10 | 交期 11天 | 量产
2. W25Q32JVSSIQ             Winbond                总分 0.784 相似 0.88 规则 0.80 供应链 0.87
   🔴高风险 | 参考替代 | SOIC-8/8脚 | 库存 26000 | ¥1.65 | 交期 9天 | 量产
   理由: W25Q32JVSSIQ（Winbond）；不达标规则: 功能一致
3. W25Q128JVSIQ             Winbond                总分 0.754 相似 0.83 规则 0.80 供应链 0.80
   🔴高风险 | 参考替代 | SOIC-8/8脚 | 库存 9800 | ¥3.80 | 交期 12天 | 量产
   理由: W25Q128JVSIQ（Winbond）；不达标规则: 功能一致
EXIT=0
```

要点：同容量（64Mbit）的兆易替代排第一；容量 32Mbit / 128Mbit 的同系列型号相似度更高（0.88/0.83）但被"容量"功能参数冲突拦成 🔴。

### 2.4 `python prototype/recommend.py TPS7A4901DGNR --top 3`

```
查询: TPS7A4901DGNR  模式: 型号替换  匹配原件: TPS7A4901DGNR  耗时: 5.65 ms
1. SPX3819M5-L-3-3          MaxLinear  总分 0.501 相似 0.51 规则 0.55 供应链 0.80 🟡中风险 | 参考替代 | SOT-23-5/5脚
   理由: 不达标规则: 封装一致/引脚一致
2. AMS1117-3.3              AMS        总分 0.495 相似 0.42 规则 0.55 供应链 0.92 🟡中风险 | 参考替代 | SOT-223/3脚
3. AMS1117-5.0              AMS        总分 0.491 相似 0.42 规则 0.55 供应链 0.90 🟡中风险 | 参考替代 | SOT-223/3脚
EXIT=0
```

要点：库中没有同封装（MSOP-8）候选时，**没有任何 Pin-to-Pin 结论输出**，最高只给"参考替代 + 需完整评估"——这正是选型工具应有的保守行为。

## 3. CLI 链路：自然语言查询

`python prototype/recommend.py "3.3V 低功耗 LDO SOT-23-5" --top 3`

```
查询: 3.3V 低功耗 LDO SOT-23-5  模式: 自然语言召回  匹配原件: None  耗时: 5.04 ms
1. MAX3485ESA               Maxim  总分 0.319 相似 0.36 🟡中风险 | 参考替代 | SOIC-8/8脚
   理由: MAX3485ESA（Maxim）语义召回候选；库存 3100 颗，交期 20 天，状态 量产；需按封装/供电/温度逐项核对后再选型
2. PCF8563T                 NXP    总分 0.289 相似 0.31 🟡中风险 | 参考替代 | SOIC-8/8脚
3. TLC555CDR                TI     总分 0.272 相似 0.29 🟡中风险 | 参考替代 | SOIC-8/8脚
⚠ 规则已排除的候选（同系列但不可直接选用，列出以备核对）:
   ✗ AZ1117-1.8   🔴高风险 | 不推荐 | 相似 0.22 | 功能关键参数与查询要求冲突…功能不等效
   ✗ AMS1117-5.0  🔴高风险 | 不推荐 | 相似 0.20 | 功能关键参数与查询要求冲突…功能不等效
   ✗ LD1117S33TR  🔴高风险 | 不推荐 | 相似 0.19 | 库存 0 | EOL
EXIT=0
```

**这条查询召回质量不合格，如实记录**：Top-1 是 RS-485 收发器而不是 LDO。原因是"低功耗"在语料中比"LDO/SOT"更罕见，TF-IDF 的 IDF 恰好把权重给了它；查询里最有区分度的品类词（LDO）与库中描述词的匹配没有被当成硬约束。已排除的 8 个候选里包含全部 3.3V 稳压器（因为查询的 3.3V 与它们的 5V/1.8V 功能冲突），说明规则层是对的，**问题出在召回层的语义理解**。修复方向见 `pipeline-verification.md` 第 6 节（品类词典 / 向量检索）。

同一套代码在"查询词与库内描述词高度重合"时表现正常，实测：

| 自然语言查询 | Top-1 | 是否合理 |
| --- | --- | --- |
| `RS-485 3.3V 收发器` | SP3485EN（0.64） | ✅ |
| `车规 CAN 收发器 5V` | TJA1050T（0.48） | ✅ |
| `64Mbit SPI Flash` | W25Q64JVSSIQ（0.48），32Mbit/128Mbit 被功能规则排除 | ✅ |
| `4通道 16位 ADC` | ADS1115IDGSR（0.32），12 位 ADS1015 被排除 | ✅ |
| `I2C EEPROM 2Kbit SOT-23-5` | AT24C02C-SSHM-T（0.48），32Kbit 被排除 | ✅ |
| `N沟道 30V MOSFET` | AO3400A（0.46），60V 的 2N7002K、P 沟道 AO3401A 被排除 | ✅ |
| `Cortex-M3 通用MCU` | STM32F103C8T6（0.44） | ✅ |

## 4. Web 服务端到端（Flask）

后台启动（`$env:PORT=5001`）：

```powershell
& $py prototype\wsgi.py     # 后台作业 pwsh-119
```

服务端日志（节选）：

```
loaded 89 chips, flask-cors=True
 * Running on http://127.0.0.1:5001
127.0.0.1 - - "GET /api/recommend?part=STM32F103C8T6&top=3 HTTP/1.1" 200 -
127.0.0.1 - - "GET /api/recommend HTTP/1.1" 400 -
127.0.0.1 - - "GET /stats HTTP/1.1" 200 -
127.0.0.1 - - "GET / HTTP/1.1" 200 -
127.0.0.1 - - "GET /?part=STC8H8K64U-45I-LQFP48&top=3 HTTP/1.1" 200 -
```

HTTP 实测（`Invoke-WebRequest`）：

| 请求 | 结果 |
| --- | --- |
| `/api/recommend?part=STM32F103C8T6&top=3` | HTTP 200，11772 bytes |
| `/api/recommend`（缺少 part） | **HTTP 400** |
| `/stats` | HTTP 200，2347 bytes |
| `/` | HTTP 200，635 bytes |
| `/?part=STC8H8K64U-45I-LQFP48&top=3` | HTTP 200，2673 bytes，含推荐表格与"规则已排除的候选"，`Access-Control-Allow-Origin: *` |

`/api/recommend?part=AMS1117-3.3&top=3` 返回的 JSON（节选）：

```
mode=part  matched=AMS1117-3.3  elapsed_ms=5.4  results=3  rejected=3
  LM1117-3.3   | 🟢低风险 | Pin-to-Pin 直接替换 | 0.8526
  AMS1117-5.0  | 🔴高风险 | 参考替代            | 0.7328
  AZ1117-1.8   | 🔴高风险 | 参考替代            | 0.7148
  ✗ LD1117S33TR | 🔴高风险 | 原厂已停产（EOL），仅可做最后购买，不建议新设计采用
```

验证完成后已终止该进程（端口 5001 释放），未留后台端口。

## 5. 性能（89 行芯片库，独立进程实测）

| 阶段 | 耗时 |
| --- | --- |
| `load_chips`（含 pandas 冷导入） | 1447.35 ms |
| TF-IDF 建索引（含 jieba 预热 + sklearn 导入） | 1357.48 ms |
| 全库 89 个型号各查一次 | 419 ms，**avg 4.71 ms/次** |
| 单次查询分布 | min 3.90 / p50 4.78 / p95 5.63 / max 6.00 ms |
| CLI 端到端（含冷启动） | 5.0 ~ 6.8 ms（`耗时` 字段，索引已在内存） |
| Flask 单请求处理 | 5.4 ms（服务器内部计时） |

一次性启动成本 ≈ 2.8 s（其中 pandas 导入 ≈ 1.4 s、jieba 词典 0.42 s、sklearn 导入 + 拟合 ≈ 0.9 s）；jieba 词典缓存在 `%TEMP%\jieba.cache`，二次启动降到 0.42 s 的加载时间。这个量级说明**几千~几万条芯片数据在单机内存里做全量排序毫无压力**，瓶颈只会出现在描述文本长度和向量维度上。

## 6. 复现步骤

```powershell
# 1) 准备依赖（受限环境用自写下载器）
python scripts\fetch_deps.py --target .deps        # 或 pwsh -File scripts/setup_env.ps1
# 2) 运行 CLI
$env:PYTHONPATH="<ws>\.deps"; $env:PYTHONIOENCODING="utf-8"
python prototype\recommend.py STM32F103C8T6 --top 5
# 3) 运行 Web
$env:PORT=5001; python prototype\wsgi.py
```

`prototype/` 各文件行数（用户要求每文件 ≤150 行）：`data_loader.py` 76、`recall.py` 72、`rules.py` 147、`ranking.py` 95、`risk.py` 150、`recommend.py` 110、`app.py` 88。
