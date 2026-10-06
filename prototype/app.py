"""app.py —— Flask 第一版：搜索页 + JSON 推荐接口 + 统计页。

启动:  python prototype/app.py            (默认 http://127.0.0.1:5000)
接口:  GET /                      搜索页
       GET /api/recommend?part=STM32F103C8T6&top=5
       GET /stats                 数据统计 + 库存/停产告警
"""
from __future__ import annotations

import os
import sys

from flask import Flask, jsonify, render_template_string, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_chips, stats  # noqa: E402
from recall import RecallIndex  # noqa: E402
from recommend import recommend  # noqa: E402

try:
    from flask_cors import CORS

    HAS_CORS = True
except ImportError:  # 缺少 flask-cors 时仅影响跨域，不影响本页访问
    HAS_CORS = False

app = Flask(__name__)
if HAS_CORS:
    CORS(app)

DF = load_chips(os.environ.get("CHIPS_CSV") or None)
INDEX = RecallIndex(DF)

PAGE = """<!doctype html><meta charset="utf-8"><title>芯选 · 芯片替代选型</title>
<style>body{font-family:system-ui;margin:24px}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:6px 8px;font-size:14px}th{background:#f5f5f5}</style>
<h2>芯选 —— 芯片替代选型智能推荐</h2>
<form method="get" action="/"><input name="part" value="{{ part }}" style="width:320px">
<select name="top"><option>3</option><option selected>5</option><option>10</option></select>
<button>推荐替代料</button></form>
{% if part %}<p>原件: {{ matched or '未命中型号（按自然语言召回）' }} · 耗时 {{ elapsed }} ms</p>
<table><tr><th>#</th><th>型号</th><th>厂商</th><th>总分</th><th>风险</th><th>替代等级</th>
<th>库存</th><th>单价</th><th>交期</th><th>理由</th></tr>
{% for r in rows %}<tr><td>{{ loop.index }}</td><td>{{ r.part_no }}</td><td>{{ r.manufacturer }}</td>
<td>{{ '%.3f'|format(r.score) }}</td><td>{{ r.risk_level }}</td><td>{{ r.replacement_tier }}</td>
<td>{{ r.stock }}</td><td>{{ '%.2f'|format(r.price_cny) }}</td><td>{{ r.lead_time_days }}</td>
<td>{{ r.summary }}</td></tr>{% endfor %}</table>
{% if rejected %}<h4>⚠ 规则已排除的候选（不可直接选用，列出以备核对）</h4>
<table><tr><th>型号</th><th>风险</th><th>相似度</th><th>库存</th><th>状态</th><th>原因</th></tr>
{% for r in rejected %}<tr><td>{{ r.part_no }}</td><td>{{ r.risk_level }}</td>
<td>{{ '%.2f'|format(r.similarity) }}</td><td>{{ r.stock }}</td><td>{{ r.lifecycle }}</td>
<td>{{ r.reasons[0] }}</td></tr>{% endfor %}</table>{% endif %}{% endif %}
<p><a href="/stats">数据统计</a> · <a href="/api/recommend?part=STM32F103C8T6&top=3">API 示例</a></p>"""


@app.route("/")
def home():
    part = request.args.get("part", "").strip()
    top = int(request.args.get("top", 5))
    rows, matched, elapsed, rejected = [], None, 0.0, []
    if part:
        res = recommend(DF, INDEX, part, top)
        rows, matched = res["results"], res["matched_part"]
        elapsed, rejected = res["elapsed_ms"], res["rejected"]
    return render_template_string(PAGE, part=part, rows=rows, matched=matched,
                                  elapsed=elapsed, rejected=rejected)


@app.route("/api/recommend")
def api_recommend():
    part = request.args.get("part", "").strip()
    if not part:
        return jsonify({"error": "缺少 part 参数"}), 400
    return jsonify(recommend(DF, INDEX, part, int(request.args.get("top", 5))))


@app.route("/stats")
def stats_page():
    s = stats(DF)
    return render_template_string(
        "<meta charset='utf-8'><h2>数据统计</h2><p>芯片总数: {{ s.total }}</p>"
        "<h3>厂商分布</h3><pre>{{ s.manufacturers }}</pre>"
        "<h3>库存/停产告警 ({{ s.alerts|length }})</h3><pre>{{ s.alerts }}</pre>"
        "<p><a href='/'>返回</a></p>", s=s)


if __name__ == "__main__":
    print(f"loaded {len(DF)} chips, flask-cors={HAS_CORS}")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
