"""wsgi.py —— Flask 应用工厂：可视化页面 + JSON API。

模块名为什么叫 wsgi 而不是 app：PyPI 上有一个无关的 `app` 发行版，只要第三方站点目录
排在 sys.path 靠前，`import app` 就会静默拿到它并报
`cannot import name 'VERSION' from 'app'`。打包成 exe 时风险更高，故改用 wsgi
（Flask 生态惯例）。`prototype/app.py` 只是转发的兼容壳。

启动:  python xinxuan.py                  (桌面窗口模式，.exe 用的就是它)
       python prototype/wsgi.py           (只起 HTTP 服务，默认 http://127.0.0.1:5000)
       python prototype/app.py            (兼容壳，等价于上一行)
页面:  GET /                 可视化单页（web/templates/index.html）
       GET /stats            旧版统计页（保留，纯文本）
接口:  GET /api/recommend?part=STM32F103C8T6&top=5
       GET /api/part/<part_no>
       GET /api/stats
       GET /api/suggest?q=stm
       GET /api/health
       POST /api/feedback    {"query":..,"part_no":..,"vote":"up"|"down"}

设计要点
--------
1. 应用工厂 `create_app()`：测试与桌面壳都通过它建应用，不依赖模块级副作用。
2. 数据集与索引**惰性构建**：RecallIndex 在 2 万行数据上要 4.7 秒，必须推迟到
   首次查询，否则桌面窗口（pywebview）会卡在启动等待里。启动只读 CSV（约 0.2 秒）。
3. 静态资源与模板都在仓库根的 web/ 下（模板 web/templates，静态 web/static），
   打包进 exe 后由 PyInstaller 的 datas 一并带上。
4. 所有接口对"数据缺失"保持宽容：字段缺失返回 0 / "" / null，不抛异常。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone

from flask import (Flask, jsonify, render_template, request,
                   send_from_directory)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from data_loader import find_part, load_chips, stats as data_stats  # noqa: E402
from recall import RecallIndex  # noqa: E402
from recommend import recommend  # noqa: E402

try:
    from flask_cors import CORS

    HAS_CORS = True
except ImportError:  # 缺少 flask-cors 时仅影响跨域，不影响本页访问
    HAS_CORS = False

VERSION = "1.4"
# 开发目录：<repo>/web；打包后：<_MEIPASS>/web（由 build_exe.py 的 --add-data 提供）
WEB_DIR = os.path.join(getattr(sys, "_MEIPASS", _ROOT), "web")
TEMPLATE_DIR = os.path.join(WEB_DIR, "templates")
STATIC_DIR = os.path.join(WEB_DIR, "static")

ALERT_REASONS = (("EOL", "原厂停产"), ("NRND", "即将停产"), ("LOW", "库存偏低"))
TOP_MIN, TOP_MAX = 1, 20
SUGGEST_LIMIT = 8
RECOMMEND_LIMIT = 3


# --------------------------------------------------------------------------- 数据层
class Dataset:
    """CSV 数据 + 召回索引的惰性持有者（线程安全，索引只建一次）。"""

    def __init__(self, csv_path=None):
        self.csv_path = csv_path or os.environ.get("CHIPS_CSV") or None
        self._df = None
        self._index = None
        self._lock = threading.Lock()

    @property
    def df(self):
        if self._df is None:
            self._df = load_chips(self.csv_path)
        return self._df

    @property
    def index(self):
        # 双检锁：2 万行索引要 4.7 秒，避免并发请求重复构建
        if self._index is None:
            with self._lock:
                if self._index is None:
                    self._index = RecallIndex(self.df)
        return self._index

    def part_row(self, part_no: str):
        return find_part(self.df, part_no)

    def suggestions(self, q: str, limit: int = SUGGEST_LIMIT) -> list:
        q = (q or "").strip().upper()
        if not q:
            return []
        df = self.df
        hit = df[df["part_no"].str.upper().str.contains(q, regex=False)]
        items = []
        for _, row in hit.head(limit * 4).iterrows():
            items.append({
                "part_no": row["part_no"],
                "manufacturer": row["manufacturer"],
                "category": row["category"],
            })
            if len(items) >= limit:
                break
        return items


def _feedback_path() -> str:
    """反馈文件必须可写：exe 常放在只读目录（U 盘/Program Files），故默认写临时目录。"""
    override = os.environ.get("XINXUAN_FEEDBACK")
    if override:
        return override
    base = os.path.join(tempfile.gettempdir(), "xinxuan")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "feedback.jsonl")


# --------------------------------------------------------------------------- 应用工厂
def create_app(csv_path=None, dataset: Dataset = None) -> Flask:
    app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
    # Flask 3.x 已废弃 JSON_AS_ASCII 配置项，必须用 app.json.ensure_ascii。
    # 不设置的话中文错误提示会变成 "\u7f3a\u5c11 part \u53c2\u6570"，前端与 curl 都不可读。
    app.json.ensure_ascii = False
    if HAS_CORS:
        CORS(app)
    ds = dataset or Dataset(csv_path)
    app.config["DATASET"] = ds

    # ---------- 页面 ----------
    @app.route("/")
    def home():
        """可视化单页。支持 ?part=xxx 直接带入查询（桌面壳与分享链接用）。"""
        return render_template("index.html", version=VERSION,
                               part=request.args.get("part", "").strip(),
                               top=request.args.get("top", "5"))

    @app.route("/favicon.ico")
    def favicon():
        return ("", 204)

    @app.route("/static/<path:filename>")
    def static_files(filename):
        # send_from_directory 自带路径穿越防护，不要自己拼路径
        return send_from_directory(STATIC_DIR, filename)

    # ---------- API ----------
    @app.route("/api/health")
    def api_health():
        return jsonify({"status": "ok", "version": VERSION,
                        "rows": int(len(ds.df))})

    @app.route("/api/recommend")
    def api_recommend():
        part = request.args.get("part", "").strip()
        if not part:
            return jsonify({"error": "缺少 part 参数"}), 400
        try:
            top = int(request.args.get("top", 5))
        except (TypeError, ValueError):
            top = 5
        top = max(TOP_MIN, min(TOP_MAX, top))
        result = recommend(ds.df, ds.index, part, top)
        result["filtered_out"] = int(result.get("filtered_out") or 0)
        return jsonify(result)

    @app.route("/api/part/<path:part_no>")
    def api_part(part_no):
        row = ds.part_row(part_no)
        if row is None:
            return jsonify({"error": "未找到该型号"}), 404
        keys = ("part_no", "manufacturer", "category", "package", "pin_count",
                "vcc_min", "vcc_max", "temp_min", "temp_max", "stock",
                "price_cny", "lead_time_days", "lifecycle", "description",
                "datasheet_url", "is_domestic")
        out = {}
        for k in keys:
            if k not in row.index:
                out[k] = "" if k in ("part_no", "manufacturer", "category", "package",
                                     "lifecycle", "description", "datasheet_url") else 0
                continue
            val = row[k]
            out[k] = val.item() if hasattr(val, "item") else val
        return jsonify(out)

    @app.route("/api/stats")
    def api_stats():
        s = data_stats(ds.df)
        by_category = [{"category": str(k), "count": int(v)}
                       for k, v in sorted(s["categories"].items(),
                                          key=lambda kv: kv[1], reverse=True)]
        life = ds.df["lifecycle"].fillna("未知").astype(str).value_counts().to_dict()
        lifecycle = [{"lifecycle": str(k), "count": int(v)}
                     for k, v in sorted(life.items(), key=lambda kv: kv[1], reverse=True)]
        alerts = []
        for rec in s["alerts"]:
            life_v = str(rec.get("lifecycle") or "未知")
            stock = int(rec.get("stock") or 0)
            reason = "库存偏低" if life_v not in ("EOL", "NRND") else dict(ALERT_REASONS)[life_v]
            alerts.append({
                "part_no": rec.get("part_no", ""),
                "manufacturer": rec.get("manufacturer", ""),
                "category": _category_of(ds.df, rec.get("part_no", "")),
                "stock": stock,
                "lifecycle": life_v,
                "reason": reason,
            })
        return jsonify({
            "total": int(s["total"]),
            "manufacturers": int(len(s["manufacturers"])),
            "categories": int(len(s["categories"])),
            "by_category": by_category,
            "lifecycle": lifecycle,
            "alerts": alerts,
            "watch_count": len(alerts),
        })

    @app.route("/api/suggest")
    def api_suggest():
        return jsonify({"items": ds.suggestions(request.args.get("q", ""))})

    @app.route("/api/feedback", methods=["POST"])
    def api_feedback():
        payload = request.get_json(silent=True) or {}
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "query": str(payload.get("query", ""))[:200],
            "part_no": str(payload.get("part_no", ""))[:80],
            "vote": "up" if str(payload.get("vote", "")).lower() in ("up", "1", "true", "👍") else "down",
        }
        if not record["query"] and not record["part_no"]:
            return jsonify({"error": "query 与 part_no 至少需要一个"}), 400
        try:
            path = _feedback_path()
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # 反馈不是关键路径：写不进去也不能让页面报错（只读介质/权限受限）
            return jsonify({"ok": True, "persisted": False}), 200
        return jsonify({"ok": True, "persisted": True})

    # ---------- 旧版统计页（保留：README 与需求文档都引用过 /stats） ----------
    @app.route("/stats")
    def stats_page():
        s = data_stats(ds.df)
        return render_template("stats.html", s=s, version=VERSION,
                               has_stats_page=os.path.exists(
                                   os.path.join(TEMPLATE_DIR, "stats.html")))

    return app


def _category_of(df, part_no: str) -> str:
    row = df[df["part_no"] == part_no]
    return str(row.iloc[0]["category"]) if not row.empty else ""


def main():
    app = create_app()
    ds = app.config["DATASET"]
    print(f"loaded {len(ds.df)} chips, flask-cors={HAS_CORS}, web={WEB_DIR}")
    print(f"page  http://127.0.0.1:{os.environ.get('PORT', '5000')}/")
    app.run(host=os.environ.get("XINXUAN_HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5000")), debug=False,
            use_reloader=False)


# 这里刻意**不**建模块级 app：工厂的意义就是让调用方（xinxuan.py / 测试 / flask CLI）
# 自己建实例。原先的模块级 app = create_app() 已移除，否则每次 import 都会多建一个
# Dataset 对象，桌面壳还会再多建一个。需要 WSGI 可调用对象请自己 create_app()。
# （`prototype/app.py` 里仍保留 `app = create_app()`，供 flask --app prototype/app.py 使用。）

if __name__ == "__main__":
    main()
