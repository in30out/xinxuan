"""rules.py —— 机械/电气/功能兼容性规则过滤与打分。soft=True 走自然语言支路（逐项比对电压/封装/引脚约束），否则走型号替换硬规则。
"""
from __future__ import annotations
import re
import pandas as pd
# 规则权重之和为 1.0（型号替换路径）
WEIGHTS = {"类别一致": 0.20, "封装一致": 0.15, "引脚一致": 0.10, "电压兼容": 0.20, "功能一致": 0.20, "温度覆盖": 0.15}
STATUS_SCORE = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
# 从描述里抽"功能关键参数"指纹；同类特征两边都有时等值比较，冲突即功能不等效
FUNC_PATTERNS = [(r"(\d+(?:\.\d+)?)\s*V(?![A-Za-z])", "电压"), (r"(\d+)\s*位", "位宽"),
                 (r"(\d+)\s*(?:路|通道)", "通道"), (r"([单双一二三四五六七八])\s*(?:路|通道)", "通道"),
                 (r"(\d+(?:\.\d+)?\s*[MmKk]bit)", "容量"), (r"([NP])\s*沟道", "沟道"),
                 (r"(\d+(?:\.\d+)?\s*[KkMm]B)\s*Flash", "Flash"), (r"(\d+(?:\.\d+)?\s*[KkMm]B)\s*RAM", "RAM")]
NUMERIC_KINDS = {"电压", "位宽", "通道"}
CN_NUM = {"单": 1, "一": 1, "双": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
# 品类同义词：键必须与 chips_seed.csv 的 category 列取值完全一致，值为口语/书面别名
SYNONYM_ROWS = [
    ("线性稳压器LDO", "ldo|线性稳压器|线性稳压|低压差|稳压器|linear regulator"),
    ("DC-DC变换器", "dc-dc|dcdc|dc dc|开关电源|开关稳压|降压|升压|降压转换|升压转换|电源芯片|电压转换|buck|boost"),
    ("微控制器MCU", "mcu|单片机|微控制器|微控制"), ("运算放大器", "运放|放大器|opamp|op-amp"),
    ("存储器", "flash|eeprom|nor flash|存储器|存储芯片"),
    ("接口芯片", "接口|收发器|transceiver|rs485|rs-485|rs422|rs232|rs-232|uart|can|串口|usb转串口|电平转换"),
    ("MOSFET", "mos|mosfet|场效应管|场效应"), ("光耦", "光耦|optocoupler|光电耦合"),
    ("定时器", "定时器|555|timer"), ("数据转换器", "adc|dac|模数转换|数模转换|a/d|d/a"),
    ("电源监控", "复位|监控|电压检测|看门狗|supervisor"), ("逻辑器件", "逻辑|门电路|logic|施密特|触发器")]
CATEGORY_SYNONYMS = {cat: aliases.split("|") for cat, aliases in SYNONYM_ROWS}
# 英文品类别名：jlcparts 全量数据的 category 是英文（data/chips_real_semi.csv），种子集是中文。
# 键必须与全量集 category 列取值完全一致；值为口语/部位别名，用于把中文查询映射到英文品类。
CATEGORY_SYNONYMS_EN = {
    "Power Management": "ldo|线性稳压器|低压差|稳压器|电源管理|电源芯片|dc-dc|dcdc|开关电源|降压|升压|电压转换|buck|boost|power management",
    "Interface ICs": "接口|收发器|transceiver|rs485|rs-485|rs422|rs232|rs-232|uart|can|串口|usb转串口|电平转换|interface",
    "Amplifiers and Comparators": "运放|放大器|比较器|opamp|op-amp|comparator|amplifier",
    "Embedded Processors and Controllers": "mcu|单片机|微控制器|微控制|处理器|mcu|microcontroller|processor",
    "Memory": "flash|eeprom|nor flash|存储器|存储芯片|memory|sram|dram",
    "Logic": "逻辑|门电路|logic|施密特|触发器|反相器",
    "Data Converters": "adc|dac|模数转换|数模转换|a/d|d/a|数据转换|converter",
    "Clock and Timing": "定时器|555|timer|时钟|晶振|振荡器|clock|oscillator|rtc",
    "Circuit Protection": "电源监控|复位|监控|电压检测|看门狗|supervisor|保护|tvs|esd|压敏|保险丝|protection",
    "RF and Wireless": "无线|射频|蓝牙|wifi|zigbee|rf|wireless|lora|天线",
    "Sensors": "传感器|sensor|温湿度|霍尔|hall|加速度|陀螺仪",
    "Motor Driver ICs": "电机驱动|马达驱动|motor driver|步进驱动|h桥",
    "Signal Isolation Devices": "光耦|光电耦合|隔离|optocoupler|digital isolator|光隔离",
    "Optoelectronics": "光电|led|发光二极管|数码管|红外|光敏|optoelectronic|display",
    "Transistors and Thyristors": "三极管|晶体管|mosfet|mos|场效应管|场效应|可控硅|晶闸管|igbt|transistor|thyristor",
    "Diodes": "二极管|整流|肖特基|快恢复|齐纳|稳压二极管|diode|schottky|zener|rectifier",
    "Power Modules": "电源模块|dc-dc模块|隔离电源|power module|dcdc module",
    "Displays and LED Drivers": "显示驱动|led驱动|数码管驱动|display driver|led driver",
    "IoT / Communication Modules": "物联网|通信模块|模组|iot|模块|module",
    "Silicon Carbide (Si C) Devices": "碳化硅|sic|silicon carbide|碳化硅器件",
    "Gallium Nitride (GaN) Devices": "氮化镓|gan|gallium nitride",
    "Optocouplers / Photocouplers": "光耦|光电耦合|optocoupler|photocoupler",
}
CATEGORY_SYNONYMS_ALL = {**CATEGORY_SYNONYMS, **{k: v.split("|") for k, v in CATEGORY_SYNONYMS_EN.items()}}
# 封装：长候选在前，避免 "sot-23-5" 先被 "sot-23" 截断
_PKG = re.compile(r"sot-?\d{2,3}(?:-\d{1,2})?|ssop-?\d{1,3}|tssop-?\d{1,3}|vssop-?\d{1,3}|msop-?\d{1,3}"
                  r"|soic-?\d{1,3}|so[p]-?\d{1,3}|qfn-?\d{1,3}|dfn-?\d{1,3}|bga-?\d{1,3}|lqfp-?\d{2,3}"
                  r"|tqfp-?\d{2,3}|qfp-?\d{2,3}|dip-?\d{1,2}|to-?\d{2,3}(?:-\d{1,2}[a-z]{0,2})?|smd-?\d{1,3}", re.I)
# NL 模式的约束权重（check_rules soft 支路用）
SOFT_RULE_WEIGHTS = {"电压约束": 0.25, "封装约束": 0.15, "引脚约束": 0.10, "功能一致": 0.35, "温度覆盖": 0.15}
# 仅 V 后缀紧贴数字才认作电压：避免 "DC-DC" 被读成 2.4V、"16位" 被读成 16V
_VOLT = re.compile(r"(?<![0-9.])(\d+(?:\.\d+)?)v(?![a-z0-9])", re.I)
_VOLT_CN = re.compile(r"(?<![0-9.])(\d+(?:\.\d+)?)\s*伏", re.I)
_PIN = re.compile(r"(?<![0-9a-z])(\d{1,3})\s*(?:脚|引脚|pin)", re.I)
_SEP = re.compile(r"[\s\-_]")
def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
def _volt(raw: str) -> str:
    """3.30 -> 3.3；5.0 -> 5。"""
    return f"{float(raw):.3f}".rstrip("0").rstrip(".")
def _query_voltages(query: str) -> list:
    """按出现顺序抽出查询里的全部电压，形如 [{'value': '24', 'raw': '24V'}]。

    "24V 转 5V DC-DC" 同时含输入/输出两个电压，只取第一个会把 "5V 输出型" 候选误判成电压不兼容。"""
    pairs = [(m.start(), _volt(m.group(1)), m.group(0)) for rx in (_VOLT_CN, _VOLT) for m in rx.finditer(str(query))]
    seen, uniq = set(), []
    for _, v, raw in sorted(pairs, key=lambda x: x[0]):
        if v not in seen:
            seen.add(v)
            uniq.append({"value": v, "raw": raw})
    return uniq
def _query_voltage(query: str) -> str:
    vals = _query_voltages(query)
    return vals[0]["value"] if vals else ""
def _covers_range(volt, cand) -> bool:
    lo, hi = _f(cand.get("vcc_min")), _f(cand.get("vcc_max"))
    for v in (volt if isinstance(volt, (set, frozenset)) else [volt]):
        try:
            if lo <= float(v) <= hi:
                return True
        except (TypeError, ValueError):
            return False
    return False
def _norm(kind: str, raw: str) -> str:
    """归一化取值：1MB -> 1024KB，64Mbit -> 65536Kbit，双路 -> 2，5.0V -> 5。"""
    txt = str(raw).strip()
    try:
        if kind in ("Flash", "RAM"):
            m = re.match(r"([\d.]+)\s*([KkMm])B", txt)
            return f"{float(m.group(1)) * (1024 if m.group(2).lower() == 'm' else 1):g}KB"
        if kind == "容量":
            m = re.match(r"([\d.]+)\s*([MmKk])bit", txt)
            return f"{float(m.group(1)) * (1024 if m.group(2).lower() == 'm' else 1):g}Kbit"
        if kind == "通道" and txt in CN_NUM:
            return f"{CN_NUM[txt]:g}"
        if kind in NUMERIC_KINDS:
            return f"{float(txt):g}"
    except (AttributeError, ValueError):
        pass
    return txt.upper()
def func_signature(text: str) -> dict:
    sig: dict = {}
    for pattern, kind in FUNC_PATTERNS:
        for raw in re.findall(pattern, str(text)):
            sig.setdefault(kind, set()).add(_norm(kind, raw))
    return sig
def _fmt_sig(sig: dict) -> str:
    return "无" if not sig else "/".join(f"{k}={'|'.join(sorted(v))}" for k, v in sorted(sig.items()))
def _term_matches(term: str, text: str) -> bool:
    if re.search(r"[a-z0-9]", term):
        return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None
    return term in text
def detect_category(query: str):
    # 自然语言查询 -> 库中 category；命中多个品类并列时返回 None（行为与改动前一致）
    vote = {c: sum(1 for a in al if _term_matches(a, str(query).lower())) for c, al in CATEGORY_SYNONYMS.items()}
    vote = {c: n for c, n in vote.items() if n}
    if not vote:
        return None
    top, win, cnt = max(vote.values()), None, 0
    for c, n in vote.items():
        if n == top:
            win, cnt = c, cnt + 1
    return win if cnt == 1 else None
def parse_constraints(query: str) -> dict:
    text = str(query)
    mp, mn = _PKG.search(text), _PIN.search(text)
    return {"voltage": _query_voltage(text), "pin_count": int(mn.group(1)) if mn else 0,
            "package": _SEP.sub("", mp.group(0)).upper() if mp else ""}
def soft_constraint_checks(query: str, cand) -> list:
    # NL 约束的实际比对：只对查询里写明的项出结论；电压全不覆盖判 fail，封装/引脚不符判 warn
    req, out, volts = parse_constraints(query), [], _query_voltages(query)
    # 查询可能同时写输入/输出电压（"24V 转 5V"）：任一落在候选供电范围内即兼容
    if volts:
        desc = str(cand.get("description", "")).lower()
        rng = f"{_f(cand['vcc_min']):g}-{_f(cand['vcc_max']):g}V"
        in_desc = [v["value"] for v in volts if v["value"] in {_volt(m) for m in _VOLT.findall(desc)}]
        if in_desc:
            st, why = "pass", f"描述中含 {in_desc[0]}V"
        elif re.search(r"可调|adjust", desc) and _covers_range({v["value"] for v in volts}, cand):
            st, why = "pass", f"描述标注可调输出，范围 {rng} 覆盖查询电压"
        elif _covers_range({v["value"] for v in volts}, cand):
            cov = [v["raw"] for v in volts if _covers_range(v["value"], cand)]
            st, why = "warn", (f"描述未写明 {'/'.join(v['value'] for v in volts)}V，但供电范围 {rng} 覆盖 {'/'.join(cov)}")
        else:
            st, why = "fail", (f"查询要求 {'/'.join(v['raw'] for v in volts)}，候选供电范围 {rng} 均不覆盖")
        out.append({"rule": "电压约束", "status": st, "detail": why, "critical": st == "fail",
                    "values": [v["value"] for v in volts]})
    pkg = req["package"]
    if pkg:
        c_pkg = _SEP.sub("", str(cand.get("package", ""))).upper()
        ok = bool(c_pkg) and (pkg in c_pkg or c_pkg in pkg)
        out.append({"rule": "封装约束", "status": "pass" if ok else "warn", "critical": False,
                    "detail": f"查询要求 {pkg}，候选 {cand.get('package', '')}" + ("" if ok else "（封装不一致，需改板或加转接）")})
    if req["pin_count"]:
        c_pin, pin = int(_f(cand.get("pin_count"))), req["pin_count"]
        out.append({"rule": "引脚约束", "status": "pass" if c_pin == pin else "warn", "critical": False,
                    "detail": f"查询要求 {pin} 脚，候选 {c_pin} 脚" + ("" if c_pin == pin else f"（差 {c_pin - pin:+d}）")})
    return out
def _func_check(q_sig: dict, c_sig: dict, qa: str = "原件") -> dict:
    # 功能参数比对：冲突 fail / 可比且一致 pass / 无同类参数 warn；qa 为查询侧称谓。
    # NL 查询（qa="查询要求"）剔除"电压"键：查询里的电压是目标电压（可能是输入也可能是输出），
    # 描述里的数字是输入范围/输出档位，口径不同，混判会把 AMS1117-3.3（描述只写 4.75-15V 输入）误杀；
    # 电压由 soft_constraint_checks 的电压约束规则单独负责。型号替换路径保持原严格口径，含电压。
    q_cmp = {k: v for k, v in q_sig.items() if not (qa != "原件" and k == "电压")}
    common = sorted(set(q_cmp) & set(c_sig))
    conflicts = [k for k in common if q_cmp[k] != c_sig[k]]
    if conflicts:
        return {"rule": "功能一致", "status": "fail", "detail": f"关键功能参数冲突（{'/'.join(conflicts)}）：{qa} {_fmt_sig(q_sig)}，候选 {_fmt_sig(c_sig)}"}
    if common:
        return {"rule": "功能一致", "status": "pass", "detail": f"功能参数可比且一致（{'/'.join(common)}）：{qa} {_fmt_sig(q_sig)}"}
    return {"rule": "功能一致", "status": "warn", "detail": f"描述中无同类可比较的功能参数，需人工核对：{qa} {_fmt_sig(q_sig)}，候选 {_fmt_sig(c_sig)}"}
def _hard_checks(query: pd.Series, cand: pd.Series, q_sig: dict, c_sig: dict) -> list:
    """型号替换路径的机械/电气硬规则。

    `critical=True` 的失败意味着"装不上去/用不了"，`risk.py` 据此把候选打入「不推荐」档，
    不再出现在主榜单。这条线只在型号替换模式下最严：类别不符、封装不同、脚位差 >2、
    电压零交集都是必须改板或换料才能用的情形；温度覆盖不足仍按 warn 逐级降级
    （见 §3.4.2 的校准决定），功能参数冲突沿用 `_func_check` 的 fail（critical=False 由此函数
    的调用方判定为"需人工确认"，但功能冲突在替代场景同样意味着不可直接替换）。
    """
    def mk(rule, status, detail, critical=False):
        return {"rule": rule, "status": status, "detail": detail, "critical": critical}
    checks = [mk("类别一致", "pass" if str(cand["category"]) == str(query["category"]) else "fail",
                 f"原类别 {query['category']}，候选 {cand['category']}",
                 critical=str(cand["category"]) != str(query["category"]))]
    same_pkg = str(cand["package"]).upper() == str(query["package"]).upper()
    checks.append(mk("封装一致", "pass" if same_pkg else "fail",
                     f"原封装 {query['package']}，候选 {cand['package']}" + ("，封装不同需改板" if not same_pkg else ""),
                     critical=not same_pkg))
    dpin = int(_f(cand["pin_count"]) - _f(query["pin_count"]))
    checks.append(mk("引脚一致", "pass" if dpin == 0 else ("warn" if abs(dpin) <= 2 else "fail"),
                     f"原 {int(_f(query['pin_count']))} 脚，候选 {int(_f(cand['pin_count']))} 脚（差值 {dpin:+d}）",
                     critical=abs(dpin) > 2))
    qmin, qmax = _f(query["vcc_min"]), _f(query["vcc_max"])
    cmin, cmax = _f(cand["vcc_min"]), _f(cand["vcc_max"])
    covers = cmin <= qmin and cmax >= qmax
    checks.append(mk("电压兼容", "pass" if covers else ("warn" if min(cmax, qmax) > max(cmin, qmin) else "fail"),
                     f"原 {qmin:g}-{qmax:g}V，候选 {cmin:g}-{cmax:g}V"
                     + (f"，裕量 {round(max(0.0, min(cmax - qmax, cmin - qmin)), 2):g}V" if covers else "，供电范围不包含原件需求"),
                     critical=not covers and not (min(cmax, qmax) > max(cmin, qmin))))
    func = _func_check(q_sig, c_sig)
    func["critical"] = func["status"] == "fail"      # 功能参数冲突 = 不是同一颗芯片
    checks.append(func)
    qtmin, qtmax = _f(query["temp_min"]), _f(query["temp_max"])
    ctmin, ctmax = _f(cand["temp_min"]), _f(cand["temp_max"])
    t_covers = ctmin <= qtmin and ctmax >= qtmax
    ratio = (max(0.0, min(ctmax, qtmax) - max(ctmin, qtmin)) / (qtmax - qtmin)) if qtmax > qtmin else 1.0
    checks.append(mk("温度覆盖", "pass" if t_covers else ("warn" if ratio >= 0.8 else "fail"),
                     f"原 {qtmin:g}~{qtmax:g}℃，候选 {ctmin:g}~{ctmax:g}℃" + ("" if t_covers else f"，温度等级需降级（覆盖 {ratio:.0%}）")))
    return checks
def check_rules(query: pd.Series, cand: pd.Series, soft: bool = False) -> dict:
    # soft=True 用于自然语言查询（没有明确原件参数）：跳过机械/电气硬规则，只做约束与功能指纹比对
    q_sig = func_signature(str(query.get("description", "")))
    c_sig = func_signature(str(cand.get("description", "")))
    if soft:
        checks = soft_constraint_checks(str(query.get("description", "")), cand)
        checks.append(_func_check(q_sig, c_sig, "查询要求"))
        failed = [c["rule"] for c in checks if c["status"] == "fail"]
        # 只有功能参数冲突、或查询电压与候选供电区间无交集，才算硬排除
        hard = [c["rule"] for c in checks if c["status"] == "fail" and (c.get("critical") or c["rule"] == "功能一致")]
        passed = sum(SOFT_RULE_WEIGHTS[c["rule"]] for c in checks if c["status"] == "pass")
        total = sum(SOFT_RULE_WEIGHTS[c["rule"]] for c in checks) or 1.0
        return {"checks": checks, "hard_fail": bool(hard), "failed_rules": failed,
                "score": round(passed / total, 4), "soft": True}
    checks = _hard_checks(query, cand, q_sig, c_sig)
    failed = [c["rule"] for c in checks if c["status"] == "fail"]
    # 零容忍 = 只由具体 check 的 critical 标记决定。
    # 「温度覆盖」即使 fail 也刻意不列 critical：温度等级不足是"需降额使用/评估环境"，
    # 不是"装不上"，按 §3.4.2 的校准走 🟡 中风险 + 降权，而不是直接打入不推荐。
    hard = [c["rule"] for c in checks if c["status"] == "fail" and c.get("critical")]
    score = sum(WEIGHTS[c["rule"]] * STATUS_SCORE[c["status"]] for c in checks)
    return {"checks": checks, "hard_fail": bool(hard), "failed_rules": failed, "score": round(score, 4)}
