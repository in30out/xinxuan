"""_check_api.py —— Flask 新接口冒烟（用 werkzeug make_server，不走子进程管道）。

本沙箱禁止子进程管道，所以这里用 werkzeug 的 make_server + 后台线程 + urllib，
在同一个 python 进程里完成"起服务 → 发请求 → 校验 → 关服务"。

成功时最后打印 SMOKE_OK，失败打印 SMOKE_FAIL 并逐条列出问题。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "prototype"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FAILURES = []


def check(name, cond, detail=""):
    print(f"  [{'OK ' if cond else 'BAD'}] {name}{(' -> ' + str(detail)) if detail else ''}")
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def request(port, path, method="GET", body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


def main() -> int:
    from werkzeug.serving import make_server

    sys.path.insert(0, os.path.join(ROOT, "prototype"))
    # 模块名用 wsgi（不是 app）：PyPI 上存在同名的 `app` 发行版，一旦它出现在
    # sys.path 的靠前位置，`import app` 会静默拿到第三方包并抛
    # "cannot import name 'VERSION' from 'app'"。prototype/app.py 只是兼容壳。
    import wsgi as appmod

    port = 5099
    flask_app = appmod.create_app()
    server = make_server("127.0.0.1", port, flask_app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(1.0)
    t0 = time.time()
    try:
        # ---- 1. 页面 ----
        st, body, _ = request(port, "/")
        check("GET / 200", st == 200, st)
        check("GET / 是可视化页面（含 芯选 与 app.js）",
              "芯选" in body and "/static/app.js" in body,
              f"len={len(body)}")
        st, body, _ = request(port, "/?part=STM32F103C8T6&top=3")
        check("GET /?part=... 200", st == 200, st)
        st, body, _ = request(port, "/static/app.js")
        check("GET /static/app.js 200", st == 200, st)
        st, body, _ = request(port, "/static/app.css")
        check("GET /static/app.css 200", st == 200, st)
        st, body, _ = request(port, "/stats")
        check("GET /stats 200（旧统计页保留）", st == 200, st)

        # ---- 2. 路径穿越防护 ----
        st, body, _ = request(port, "/static/../prototype/wsgi.py")
        check("路径穿越被拒（不是 200 泄漏源码）", st != 200, st)

        # ---- 3. /api/recommend ----
        st, body, hdr = request(port, "/api/recommend?part=STM32F103C8T6&top=3")
        check("GET /api/recommend 200", st == 200, st)
        data = json.loads(body)
        for k in ("query", "mode", "category", "matched_part", "elapsed_ms",
                  "filtered_out", "results", "rejected"):
            check(f"recommend 顶层含 {k}", k in data, list(data)[:12])
        check("mode=part", data.get("mode") == "part", data.get("mode"))
        check("matched_part", data.get("matched_part") == "STM32F103C8T6",
              data.get("matched_part"))
        check("results 非空", len(data.get("results") or []) > 0,
              len(data.get("results") or []))
        row = (data.get("results") or [{}])[0]
        for k in ("part_no", "manufacturer", "category", "package", "pin_count",
                  "price_cny", "stock", "lead_time_days", "lifecycle", "similarity",
                  "rule_score", "supply", "score", "supply_detail", "checks",
                  "risk_level", "replacement_tier", "reasons", "summary"):
            check(f"结果项含 {k}", k in row)
        check("checks 六条齐全", len(row.get("checks") or []) == 6,
              len(row.get("checks") or []))
        check("supply_detail 五键",
              set((row.get("supply_detail") or {})) ==
              {"w_stock", "w_price", "w_lead", "w_life", "price_ratio"},
              sorted((row.get("supply_detail") or {})))
        print(f"       top1={row.get('part_no')} score={row.get('score')} "
              f"tier={row.get('replacement_tier')} risk={row.get('risk_level')}")

        st, body, _ = request(port, "/api/recommend?top=3")
        check("缺 part -> 400", st == 400, st)
        check("400 带中文错误", "缺少 part" in body, body[:60])

        st, body, _ = request(port, "/api/recommend?part=3.3V%20%E4%BD%8E%E5%8A%9F%E8%80%97%20LDO%20SOT-23-5&top=3")
        data = json.loads(body)
        check("NL 查询 mode=text", data.get("mode") == "text", data.get("mode"))
        check("NL 查询 category 已识别", bool(data.get("category")), data.get("category"))
        check("NL 查询 matched_part 为 null", data.get("matched_part") is None)
        check("NL 查询有结果", len(data.get("results") or []) > 0)

        # ---- 4. /api/part ----
        st, body, _ = request(port, "/api/part/STM32F103C8T6")
        check("GET /api/part/<no> 200", st == 200, st)
        pdata = json.loads(body)
        for k in ("part_no", "manufacturer", "category", "package", "pin_count",
                  "vcc_min", "vcc_max", "temp_min", "temp_max", "stock",
                  "price_cny", "lead_time_days", "lifecycle", "description",
                  "datasheet_url", "is_domestic"):
            check(f"part 详情含 {k}", k in pdata, sorted(pdata)[:20])
        st, body, _ = request(port, "/api/part/NOT_A_REAL_PART")
        check("未知型号 -> 404", st == 404, st)

        # ---- 5. /api/stats ----
        st, body, _ = request(port, "/api/stats")
        check("GET /api/stats 200", st == 200, st)
        sdata = json.loads(body)
        for k in ("total", "manufacturers", "categories", "by_category",
                  "lifecycle", "alerts", "watch_count"):
            check(f"stats 含 {k}", k in sdata)
        check("stats total=89", sdata.get("total") == 89, sdata.get("total"))
        check("by_category 降序",
              all(sdata["by_category"][i]["count"] >= sdata["by_category"][i + 1]["count"]
                  for i in range(len(sdata["by_category"]) - 1)))
        check("告警带 reason",
              all("reason" in a for a in sdata.get("alerts", [])))

        # ---- 6. /api/suggest ----
        st, body, _ = request(port, "/api/suggest?q=stm")
        check("GET /api/suggest 200", st == 200, st)
        sug = json.loads(body)
        check("suggest 返回 items", isinstance(sug.get("items"), list), type(sug.get("items")))
        check("suggest 有 stm 命中", len(sug["items"]) > 0, sug["items"][:2])
        check("suggest 上限 8", len(sug["items"]) <= 8, len(sug["items"]))

        # ---- 7. /api/health 与 feedback ----
        st, body, _ = request(port, "/api/health")
        check("GET /api/health 200", st == 200, st)
        check("health status ok", json.loads(body).get("status") == "ok")

        st, body, _ = request(port, "/api/feedback", method="POST",
                              body={"query": "STM32F103C8T6", "part_no": "APM32F103C8T6",
                                    "vote": "up"})
        check("POST /api/feedback 200", st == 200, st)
        check("feedback ok", json.loads(body).get("ok") is True, body[:80])
        st, body, _ = request(port, "/api/feedback", method="POST", body={})
        check("空 feedback -> 400", st == 400, st)
    finally:
        server.shutdown()

    print(f"\n耗时 {time.time() - t0:.2f}s")
    if FAILURES:
        print(f"SMOKE_FAIL ({len(FAILURES)} 项)")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
