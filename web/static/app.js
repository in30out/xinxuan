/* =====================================================================
 * 芯选 XinXuan —— 前端交互层
 * app.js  |  原生 JS，零依赖、零构建、零 CDN
 * ---------------------------------------------------------------------
 * 接口契约（与后端冻结版本一致，页面不做任何字段猜测）：
 *   GET  /api/recommend?part=<str>&top=<1..20>
 *   GET  /api/part/<part_no>
 *   GET  /api/stats
 *   GET  /api/suggest?q=<str>
 *   POST /api/feedback   {query, part_no, vote}
 *   GET  /api/health
 * ===================================================================== */

(function () {
  'use strict';

  /* ============ 0. 小工具 ============ */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  function fmtNum(v) {
    if (!isNum(v)) return '—';
    return v.toLocaleString('zh-CN');
  }

  function fmtScore(v) { return isNum(v) ? v.toFixed(3) : '—'; }

  function fmtPrice(v) {
    if (!isNum(v)) return '—';
    if (v >= 10) return '¥' + v.toFixed(2);
    if (v >= 1) return '¥' + v.toFixed(3);
    return '¥' + v.toFixed(4);
  }

  function clamp01(v) { return Math.max(0, Math.min(1, isNum(v) ? v : 0)); }

  function barPct(v) { return (clamp01(v) * 100).toFixed(1) + '%'; }

  /* ---- 语义映射：风险 / 替代等级 / 生命周期 ---- */
  var RISK_ORDER = { '🟢低风险': 0, '🟡中风险': 1, '🔴高风险': 2 };
  var TIER_ORDER = {
    'Pin-to-Pin 直接替换': 0, '功能等效需改板': 1, '参考替代': 2, '不推荐': 3
  };
  var LC_ORDER = { '量产': 0, '预览': 1, '未知': 2, 'NRND': 3, 'EOL': 4 };

  function riskClass(level) {
    var s = String(level || '');
    if (s.indexOf('低') >= 0) return 'risk-low';
    if (s.indexOf('中') >= 0) return 'risk-mid';
    if (s.indexOf('高') >= 0) return 'risk-high';
    return 'risk-ref';
  }
  function tierClass(tier) {
    var s = String(tier || '');
    if (s.indexOf('Pin-to-Pin') >= 0) return 'tier-p2p';
    if (s.indexOf('改板') >= 0) return 'tier-redesign';
    if (s.indexOf('不推荐') >= 0) return 'tier-no';
    return 'tier-ref';
  }
  function tierCardClass(tier) {
    var s = tierClass(tier);
    return s === 'tier-p2p' ? 'tier-p2p-card'
      : s === 'tier-redesign' ? 'tier-redesign-card'
      : s === 'tier-no' ? 'tier-no-card' : 'tier-ref-card';
  }
  function lcClass(lc) {
    var s = String(lc || '');
    if (s === '量产') return 'lc-mass';
    if (s === 'NRND') return 'lc-nrnd';
    if (s === 'EOL') return 'lc-eol';
    if (s === '预览') return 'lc-prev';
    return 'lc-unk';
  }
  function statusPill(st) {
    var s = String(st || '').toLowerCase();
    var cls = s === 'pass' ? 'pill-pass' : s === 'warn' ? 'pill-warn' : 'pill-fail';
    return '<span class="pill ' + cls + '">' + esc(s || '—') + '</span>';
  }
  function lcBadge(lc) {
    return '<span class="lc ' + lcClass(lc) + '">' + esc(lc || '未知') + '</span>';
  }
  function riskBadge(level) {
    return '<span class="risk ' + riskClass(level) + '">' + esc(level || '—') + '</span>';
  }
  function tierBadge(tier) {
    return '<span class="tier ' + tierClass(tier) + '">' + esc(tier || '—') + '</span>';
  }

  function pinText(n) {
    if (!isNum(n) || n <= 0) return '—（数据缺失）';
    return n + ' 脚';
  }
  function rangeText(lo, hi, unit, sep) {
    var a = isNum(lo) && lo !== 0 ? String(lo) : null;
    var b = isNum(hi) && hi !== 0 ? String(hi) : null;
    if (a === null && b === null) return '—（数据缺失）';
    if (a !== null && b !== null) return a + (sep || '-') + b + unit;
    return (a !== null ? '≥' + a : '≤' + b) + unit;
  }

  /* ============ 1. API 层 ============ */
  function ApiError(message, status, payload) {
    this.name = 'ApiError';
    this.message = message;
    this.status = status;
    this.payload = payload || null;
  }
  ApiError.prototype = Object.create(Error.prototype);

  function request(url, options) {
    var opt = options || {};
    return fetch(url, {
      method: opt.method || 'GET',
      headers: opt.body
        ? { 'Content-Type': 'application/json', 'Accept': 'application/json' }
        : { 'Accept': 'application/json' },
      body: opt.body ? JSON.stringify(opt.body) : undefined
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) { try { data = JSON.parse(text); } catch (e) { data = null; } }
        if (!res.ok) {
          var msg = (data && data.error) ? data.error : 'HTTP ' + res.status;
          throw new ApiError(msg, res.status, data);
        }
        if (data === null) throw new ApiError('响应不是合法 JSON', res.status, null);
        return data;
      });
    }, function (netErr) {
      throw new ApiError('网络请求失败：' + (netErr && netErr.message ? netErr.message : '未知错误'), 0, null);
    });
  }

  var API = {
    recommend: function (part, top) {
      return request('/api/recommend?part=' + encodeURIComponent(part) + '&top=' + encodeURIComponent(top));
    },
    part: function (partNo) {
      return request('/api/part/' + encodeURIComponent(partNo));
    },
    stats: function () { return request('/api/stats'); },
    suggest: function (q) { return request('/api/suggest?q=' + encodeURIComponent(q)); },
    feedback: function (payload) { return request('/api/feedback', { method: 'POST', body: payload }); },
    health: function () { return request('/api/health'); }
  };

  /* ============ 2. 状态 ============ */
  var state = {
    query: '',
    top: 5,
    data: null,                 // 最近一次 /api/recommend 响应
    view: 'cards',              // cards | table
    sort: { key: 'score', dir: 'desc' },
    expanded: {},               // part_no -> true
    original: null,             // /api/part/<matched_part> 响应
    originalNo: null,
    originalState: 'idle',      // idle | loading | ok | missing | error
    votes: {},                  // part_no -> 'up' | 'down'
    stats: null,
    statsState: 'idle',
    suggest: { items: [], idx: -1, timer: null, seq: 0 },
    reqSeq: 0
  };

  /* ============ 3. 标签页路由 ============ */
  var TABS = ['search', 'stats', 'model', 'about'];

  function activateTab(name, skipHash) {
    if (TABS.indexOf(name) < 0) name = 'search';
    $$('.tab-btn').forEach(function (b) {
      var on = b.getAttribute('data-tab') === name;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    TABS.forEach(function (t) {
      var panel = $('#panel-' + t);
      if (!panel) return;
      var on = t === name;
      panel.classList.toggle('is-active', on);
      if (on) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
    });
    if (!skipHash && window.location.hash !== '#' + name) {
      window.location.hash = name;
    }
    if (name === 'stats') loadStats();
  }

  function initTabs() {
    $$('.tab-btn').forEach(function (b) {
      b.addEventListener('click', function () { activateTab(b.getAttribute('data-tab')); });
    });
    window.addEventListener('hashchange', function () {
      activateTab(String(window.location.hash || '').replace('#', ''), true);
    });
    var initial = String(window.location.hash || '').replace('#', '');
    activateTab(TABS.indexOf(initial) >= 0 ? initial : 'search', true);
  }

  /* ============ 4. 轻提示 ============ */
  var toastTimer = null;
  function toast(msg, kind) {
    var el = $('#toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast';
      el.className = 'toast';
      document.body.appendChild(el);
    }
    el.className = 'toast toast-' + (kind || 'info') + ' is-on';
    el.textContent = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('is-on'); }, 2600);
  }

  /* ============ 5. 搜索与自动补全 ============ */
  function hideSuggest() {
    var box = $('#suggest-list');
    if (box) { box.setAttribute('hidden', ''); box.innerHTML = ''; }
    state.suggest.items = [];
    state.suggest.idx = -1;
  }

  function renderSuggest(items, q) {
    var box = $('#suggest-list');
    if (!box) return;
    if (!items.length) {
      box.innerHTML = '<li class="suggest-empty">没有匹配的型号（演示数据集仅收录 89 条）</li>';
      box.removeAttribute('hidden');
      return;
    }
    box.innerHTML = items.map(function (it, i) {
      var meta = [it.manufacturer, it.category].filter(Boolean).join(' · ');
      return '<li class="suggest-item" role="option" data-idx="' + i + '" data-part="' + esc(it.part_no) + '">'
        + '<span class="suggest-part">' + esc(it.part_no) + '</span>'
        + '<span class="suggest-meta">' + esc(meta) + '</span>'
        + '</li>';
    }).join('');
    box.removeAttribute('hidden');
  }

  function setActiveSuggest(idx) {
    var items = $$('#suggest-list .suggest-item');
    if (!items.length) return;
    state.suggest.idx = Math.max(0, Math.min(items.length - 1, idx));
    items.forEach(function (el, i) { el.classList.toggle('is-active', i === state.suggest.idx); });
  }

  function requestSuggest(q) {
    var seq = ++state.suggest.seq;
    API.suggest(q).then(function (data) {
      if (seq !== state.suggest.seq) return;
      renderSuggest(Array.isArray(data.items) ? data.items : [], q);
    }).catch(function () {
      if (seq !== state.suggest.seq) return;
      hideSuggest();
    });
  }

  function initSearch() {
    var form = $('#search-form');
    var input = $('#q');
    var clear = $('#search-clear');
    var box = $('#suggest-list');
    var topSel = $('#top-n');

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      runSearch(input.value, topSel.value);
    });

    input.addEventListener('input', function () {
      var v = input.value.trim();
      if (clear) { if (v) clear.removeAttribute('hidden'); else clear.setAttribute('hidden', ''); }
      if (state.suggest.timer) clearTimeout(state.suggest.timer);
      if (!v) { hideSuggest(); return; }
      state.suggest.timer = setTimeout(function () { requestSuggest(v); }, 180);
    });

    input.addEventListener('keydown', function (e) {
      var open = box && !box.hasAttribute('hidden');
      if (e.key === 'ArrowDown' && open) {
        e.preventDefault(); setActiveSuggest(state.suggest.idx + 1);
      } else if (e.key === 'ArrowUp' && open) {
        e.preventDefault(); setActiveSuggest(state.suggest.idx - 1);
      } else if (e.key === 'Enter' && open && state.suggest.idx >= 0) {
        e.preventDefault();
        var el = $$('#suggest-list .suggest-item')[state.suggest.idx];
        if (el) { input.value = el.getAttribute('data-part'); hideSuggest(); runSearch(input.value, topSel.value); }
      } else if (e.key === 'Escape') {
        hideSuggest();
      }
    });

    box.addEventListener('mousedown', function (e) {
      var li = e.target.closest ? e.target.closest('.suggest-item') : null;
      if (!li) return;
      e.preventDefault();
      input.value = li.getAttribute('data-part');
      if (clear) clear.removeAttribute('hidden');
      hideSuggest();
      runSearch(input.value, topSel.value);
    });

    document.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('.search-field')) return;
      hideSuggest();
    });

    if (clear) {
      clear.addEventListener('click', function () {
        input.value = '';
        clear.setAttribute('hidden', '');
        hideSuggest();
        input.focus();
      });
    }

    $$('.chip-example').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var q = btn.getAttribute('data-q');
        input.value = q;
        if (clear) clear.removeAttribute('hidden');
        runSearch(q, topSel.value);
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key !== '/') return;
      var tag = (document.activeElement && document.activeElement.tagName) || '';
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      e.preventDefault();
      activateTab('search');
      input.focus();
      input.select();
    });

    topSel.addEventListener('change', function () {
      if (state.data && state.query) runSearch(state.query, topSel.value);
    });
  }

  /* ============ 6. 查询主流程 ============ */
  function setLoading(on) {
    var el = $('#loading-state');
    var btn = $('#search-btn');
    if (el) { if (on) el.removeAttribute('hidden'); else el.setAttribute('hidden', ''); }
    if (btn) {
      btn.classList.toggle('is-busy', !!on);
      var txt = $('.btn-text', btn);
      if (txt) txt.textContent = on ? '查询中…' : '推荐替代料';
    }
  }
  function showError(err) {
    var box = $('#error-state');
    var msg = $('#error-msg');
    if (!box) return;
    if (msg) {
      msg.textContent = err && err.name === 'ApiError'
        ? (err.status ? ('[' + err.status + '] ' + err.message) : err.message)
        : ('未知错误：' + (err && err.message ? err.message : err));
    }
    box.removeAttribute('hidden');
  }
  function hideError() {
    var box = $('#error-state');
    if (box) box.setAttribute('hidden', '');
  }
  function hideEmpty() {
    var el = $('#empty-state');
    if (el) el.setAttribute('hidden', '');
  }
  function hideResults() {
    var el = $('#results-block');
    if (el) el.setAttribute('hidden', '');
  }

  function runSearch(q, top) {
    q = String(q || '').trim();
    if (!q) { var i = $('#q'); if (i) i.focus(); return; }
    var topN = parseInt(top, 10);
    if (!(topN >= 1 && topN <= 20)) topN = 5;

    state.query = q;
    state.top = topN;
    state.expanded = {};
    state.original = null;
    state.originalNo = null;
    state.originalState = 'idle';
    state.sort = { key: 'score', dir: 'desc' };
    hideSuggest();
    hideError();
    hideEmpty();
    hideResults();
    setLoading(true);

    var seq = ++state.reqSeq;
    API.recommend(q, topN).then(function (data) {
      if (seq !== state.reqSeq) return;
      state.data = data;
      if (data.matched_part) {
        state.originalNo = data.matched_part;
        loadOriginal(data.matched_part);
      }
      renderResults();
    }).catch(function (err) {
      if (seq !== state.reqSeq) return;
      state.data = null;
      showError(err);
    }).then(function () {
      if (seq !== state.reqSeq) return;
      setLoading(false);
    });
  }

  function loadOriginal(partNo) {
    if (!partNo) return;
    state.originalState = 'loading';
    API.part(partNo).then(function (p) {
      if (state.originalNo !== partNo) return;
      state.original = p;
      state.originalState = 'ok';
      if (hasExpanded()) renderResults();
    }).catch(function (err) {
      if (state.originalNo !== partNo) return;
      state.original = null;
      state.originalState = (err && err.status === 404) ? 'missing' : 'error';
      if (hasExpanded()) renderResults();
    });
  }

  function hasExpanded() {
    for (var k in state.expanded) { if (state.expanded[k]) return true; }
    return false;
  }

  /* ============ 7. 查询概要 / 空结果 ============ */
  function renderStatus(data) {
    var $scope = $('#query-status');
    if (!data) return;
    var isText = data.mode === 'text';
    $('#status-mode').textContent = isText ? '需求检索（自然语言）' : '型号替换';
    /* 实测：型号模式下 /api/recommend 的 category 为 null（仅候选行带品类），需区分「未识别」与「—」 */
    $('#status-category').textContent = data.category || (isText ? '未识别出器件品类' : '—（型号模式不返回顶层品类）');
    $('#status-matched').textContent = data.matched_part || '—（未命中型号，已按自然语言召回）';
    $('#status-elapsed').textContent = (isNum(data.elapsed_ms) ? data.elapsed_ms.toFixed(1) : '—') + ' ms';
    $('#status-filtered').textContent = isNum(data.filtered_out) ? (data.filtered_out + ' 条') : '—';
    $('#result-count').textContent = (data.results || []).length;
    /* 口径说明（答辩会被追问，写死在界面上） */
    var note = $('#status-note');
    if (note) {
      var tips = [];
      if (isText) {
        tips.push('自然语言模式没有原型号作基准：<b>rule_score 仅作展示、不参与排序</b>，风险等级按保守口径给出（🟡中风险 / 参考替代 / 不推荐），这是设计决定而非计算错误。');
      }
      tips.push('相似度仅用于召回排序（实测区间约 0.1–0.7，不要按 1.0 满分预期读），综合得分由六维规则分与供应链因子加权得出。');
      note.innerHTML = tips.join(' ');
      note.removeAttribute('hidden');
    }
    $scope.removeAttribute('hidden');
  }

  function emptyHintHTML(data) {
    var parts = [];
    var n = (data.rejected || []).length;
    if (data.mode === 'part') {
      parts.push('已按<strong>型号替换</strong>模式查询 <code>' + esc(data.query) + '</code>，但演示数据集里没有通过硬约束的同类候选。');
    } else if (!data.category) {
      parts.push('这句话<strong>没有识别出器件品类</strong>，也没有命中任何型号，因此在 89 条演示数据里召回为空。');
    } else {
      parts.push('已识别品类为 <strong>' + esc(data.category) + '</strong>，但该品类下没有通过硬约束过滤的候选。');
    }
    if (n > 0) {
      parts.push('有 <strong>' + n + '</strong> 条候选被零容忍规则排除，理由见下方「被规则排除的候选」。');
    }
    parts.push('建议：① 直接输入具体型号（如 <code>STM32F103C8T6</code>）；② 在自然语言里补上封装 / 电压 / 脚位约束（如 <code>3.3V LDO SOT-23-5</code>）；③ 换用品类词表内的说法（LDO、DC-DC、MCU、运放、接口芯片、MOSFET、光耦…）。');
    return parts.join('<br>');
  }

  function renderEmpty(data) {
    $('#empty-title').textContent = data.mode === 'part'
      ? '该型号没有可用替代料'
      : '没有召回可推荐的候选';
    $('#empty-hint').innerHTML = emptyHintHTML(data);
    $('#empty-state').removeAttribute('hidden');
  }

  /* ============ 8. 卡片视图 ============ */
  function factorLine(name, cls, val, raw) {
    return '<div class="factor-line">'
      + '<span class="fl-name">' + esc(name) + '</span>'
      + '<span class="fl-track"><i class="fl-fill ' + cls + '" style="width:' + barPct(val) + '"></i></span>'
      + '<span class="fl-val" title="' + esc(raw === undefined ? '' : String(raw)) + '">' + fmtScore(val) + '</span>'
      + '</div>';
  }

  function voteHTML(partNo) {
    var v = state.votes[partNo];
    return '<span class="vote">'
      + '<span class="vote-label">采纳反馈</span>'
      + '<button type="button" class="votebtn' + (v === 'up' ? ' is-on' : '') + '" data-vote="up" data-vote-part="' + esc(partNo) + '" title="这条推荐可用于选型">👍 可用</button>'
      + '<button type="button" class="votebtn' + (v === 'down' ? ' is-on' : '') + '" data-vote="down" data-vote-part="' + esc(partNo) + '" title="这条推荐不适用">👎 不适用</button>'
      + '</span>';
  }

  function cardHTML(r, idx) {
    var open = !!state.expanded[r.part_no];
    var meta = [
      r.manufacturer, r.category, r.package,
      (isNum(r.pin_count) && r.pin_count > 0 ? r.pin_count + ' 脚' : '脚数缺失')
    ].filter(function (x) { return x !== undefined && x !== null && x !== ''; }).join(' · ');

    return '<article class="card ' + tierCardClass(r.replacement_tier) + (open ? ' is-open' : '') + '" data-part="' + esc(r.part_no) + '">'
      + '<div class="card-top">'
      +   '<span class="card-rank' + (idx === 0 ? ' is-top' : '') + '">' + (idx + 1) + '</span>'
      +   '<div class="card-ident">'
      +     '<div class="card-part">' + esc(r.part_no) + '</div>'
      +     '<div class="card-meta">' + esc(meta) + '</div>'
      +   '</div>'
      +   '<div class="card-score">'
      +     '<div class="card-score-num">' + (isNum(r.score) ? r.score.toFixed(3) : '—') + '</div>'
      +     '<div class="card-score-cap">综合得分</div>'
      +     '<div class="card-score-bar"><i style="width:' + barPct(r.score) + '"></i></div>'
      +   '</div>'
      + '</div>'
      + '<div class="card-badges">' + tierBadge(r.replacement_tier) + riskBadge(r.risk_level)
      +   '<span class="tag">相似度 ' + fmtScore(r.similarity) + '</span>'
      +   '<span class="tag">库存 ' + fmtNum(r.stock) + '</span>'
      +   '<span class="tag">' + esc(fmtPrice(r.price_cny)) + '</span>'
      +   '<span class="tag">交期 ' + (isNum(r.lead_time_days) ? r.lead_time_days : '—') + ' 天</span>'
      +   lcBadge(r.lifecycle)
      + '</div>'
      + '<div class="card-factors">'
      +   factorLine('规则分', 'fl-rule', r.rule_score)
      +   factorLine('相似度', 'fl-sim', r.similarity)
      +   factorLine('供应链', 'fl-sup', r.supply)
      + '</div>'
      + '<div class="card-summary">' + esc(r.summary || '（无一句话结论）') + '</div>'
      + '<div class="card-actions">'
      +   '<button type="button" class="linkbtn' + (open ? ' is-open' : '') + '" data-act="toggle" data-part="' + esc(r.part_no) + '">'
      +     (open ? '收起详情' : '展开详情：六维规则 / 供应链四因子 / 理由') + '<span class="caret">▼</span></button>'
      +   voteHTML(r.part_no)
      + '</div>'
      + (open ? detailHTML(r) : '')
      + '</article>';
  }

  function renderCards() {
    var list = (state.data && state.data.results) || [];
    var box = $('#cards-view');
    box.innerHTML = list.map(cardHTML).join('');
  }

  /* ============ 9. 详情面板（卡片与表格共用） ============ */
  function rulesTableHTML(checks) {
    if (!checks || !checks.length) {
      return '<p class="detail-loading">后端未返回规则明细。</p>';
    }
    return '<table class="rules-table"><tbody>' + checks.map(function (c) {
      var st = String(c.status || '').toLowerCase();
      var rowCls = st === 'pass' ? 'is-pass' : st === 'warn' ? 'is-warn' : 'is-fail';
      return '<tr class="' + rowCls + '">'
        + '<td class="rt-name">' + esc(c.rule) + (c.critical ? ' <span class="tag tag-critical">零容忍</span>' : '') + '</td>'
        + '<td class="rt-status">' + statusPill(st) + '</td>'
        + '<td class="rt-detail">' + esc(c.detail || '') + '</td>'
        + '</tr>';
    }).join('') + '</tbody></table>';
  }

  function supplyBarsHTML(r) {
    var d = r.supply_detail || {};
    var wStock = clamp01(d.w_stock), wPrice = clamp01(d.w_price);
    var wLead = clamp01(d.w_lead), wLife = clamp01(d.w_life);
    var ratio = isNum(d.price_ratio) ? d.price_ratio : null;
    var zeroStock = isNum(r.stock) && r.stock <= 0;

    var calc = (Math.pow(wStock, 0.45) * Math.pow(wPrice, 0.20) * Math.pow(wLead, 0.20) * Math.pow(wLife, 0.15)) * (zeroStock ? 0.2 : 1);

    function row(name, en, cls, val, note) {
      return '<div class="fbar">'
        + '<span class="fbar-name">' + esc(name) + '<b>' + esc(en) + '</b></span>'
        + '<span class="fbar-track"><i class="fbar-fill ' + cls + '" style="width:' + barPct(val) + '"></i></span>'
        + '<span class="fbar-val">' + fmtScore(val) + '</span>'
        + '<span class="fbar-note">' + note + '</span>'
        + '</div>';
    }

    return '<div class="factor-bars">'
      + row('库存', 'w_stock', 'f-stock', wStock, '库存 ' + fmtNum(r.stock) + ' 片 → log1p 归一化')
      + row('价格', 'w_price', 'f-price', wPrice,
          ratio === null ? '无原型号参考价' :
          ('价格比 ' + ratio.toFixed(3) + '× 原型号（' + (ratio > 1.0001 ? '更贵' : ratio < 0.9999 ? '更便宜' : '持平') + '）'))
      + row('交期', 'w_lead', 'f-lead', wLead, (isNum(r.lead_time_days) ? r.lead_time_days : '—') + ' 天交期（7 天为基准，67 天触底）')
      + row('生命周期', 'w_life', 'f-life', wLife, esc(r.lifecycle || '未知') + ' → 系数 ' + wLife.toFixed(2))
      + '</div>'
      + '<div class="supply-total">'
      + '<span>加权式</span>'
      + '<span class="mono">' + wStock.toFixed(3) + '<sup>0.45</sup> · ' + wPrice.toFixed(3) + '<sup>0.20</sup> · '
      + wLead.toFixed(3) + '<sup>0.20</sup> · ' + wLife.toFixed(3) + '<sup>0.15</sup>'
      + (zeroStock ? ' × 0.2（缺货惩罚）' : '') + '</span>'
      + '<span>= <b>' + fmtScore(calc) + '</b></span>'
      + '<span>接口返回 supply = <b>' + fmtScore(r.supply) + '</b></span>'
      + '</div>';
  }

  /* 硬约束规则文本 → 「原型号 | 候选」两列 */
  function splitPair(detail) {
    var m = String(detail || '').match(/^(.*?)[，,]\s*候选\s*([\s\S]*)$/);
    if (!m) return null;
    var left = m[1].replace(/^原\s*(?:类别|封装|型号)?\s*/, '').trim();
    return [left, m[2].trim()];
  }

  function checkByRule(checks, name) {
    if (!checks) return null;
    for (var i = 0; i < checks.length; i++) { if (checks[i].rule === name) return checks[i]; }
    return null;
  }

  function compareTableHTML(r) {
    var checks = r.checks || [];
    var isPart = state.data && state.data.mode === 'part';
    var o = state.original;

    if (!isPart) {
      /* 自然语言模式：没有原型号，展示候选关键参数 */
      var rows = [
        ['器件品类', esc(r.category || '—')],
        ['封装', esc(r.package || '—')],
        ['引脚数', esc(pinText(r.pin_count))],
        ['库存', fmtNum(r.stock) + ' 片'],
        ['单价', esc(fmtPrice(r.price_cny))],
        ['交期', (isNum(r.lead_time_days) ? r.lead_time_days : '—') + ' 天'],
        ['生命周期', lcBadge(r.lifecycle)]
      ];
      return '<table class="compare">'
        + '<thead><tr><th>候选关键参数</th><th>' + esc(r.part_no) + '（' + esc(r.manufacturer || '—') + '）</th></tr></thead>'
        + '<tbody>' + rows.map(function (x) {
          return '<tr><td class="cmp-k">' + x[0] + '</td><td class="cmp-c">' + x[1] + '</td></tr>';
        }).join('') + '</tbody></table>'
        + '<p class="compare-note">自然语言需求模式没有「原型号」可比，规则基准是查询语句本身（见上方六维规则表的逐条依据）；这里列出候选自身的关键参数，供人工核对。</p>';
    }

    /* 型号替换模式：原型号 vs 候选 */
    var y = function (v) { return v === null || v === undefined || v === '' ? '—' : esc(v); };
    var head = '<thead><tr><th>关键参数</th>'
      + '<th class="compare-th-part">原型号 ' + esc(state.data.matched_part) + '</th>'
      + '<th class="compare-th-part">候选 ' + esc(r.part_no) + '</th>'
      + '<th>结论</th></tr></thead>';

    var hard = [
      ['类别一致', '器件品类'],
      ['封装一致', '封装'],
      ['引脚一致', '引脚数'],
      ['电压兼容', '供电范围'],
      ['功能一致', '功能参数'],
      ['温度覆盖', '温度范围']
    ];
    var body = hard.map(function (pair) {
      var c = checkByRule(checks, pair[0]);
      if (!c) return '';
      var sp = splitPair(c.detail);
      var l = sp ? sp[0] : (c.detail || '—');
      var rt = sp ? sp[1] : '—';
      var st = String(c.status || '').toLowerCase();
      return '<tr class="' + (st === 'pass' ? '' : 'is-diff') + '">'
        + '<td class="cmp-k">' + esc(pair[1]) + '</td>'
        + '<td class="cmp-o">' + esc(l) + '</td>'
        + '<td class="cmp-c">' + esc(rt) + '</td>'
        + '<td>' + statusPill(st) + '</td>'
        + '</tr>';
    }).join('');

    /* 供货侧参数：原型号来自 /api/part，候选来自推荐结果行 */
    var sup;
    if (state.originalState === 'ok' && o) {
      var priceDelta = (isNum(o.price_cny) && isNum(r.price_cny) && o.price_cny > 0)
        ? ((r.price_cny / o.price_cny - 1) * 100) : null;
      sup = [
        ['生产厂商', y(o.manufacturer), esc(r.manufacturer || '—'), ''],
        ['库存', fmtNum(o.stock) + ' 片', fmtNum(r.stock) + ' 片', ''],
        ['单价',
          esc(fmtPrice(o.price_cny)) + (o.is_domestic ? ' <span class="tag">国产</span>' : ''),
          esc(fmtPrice(r.price_cny)) + (priceDelta === null ? '' :
            ' <span class="tag">' + (priceDelta > 0 ? '+' : '') + priceDelta.toFixed(1) + '%</span>'),
          ''],
        ['交期', (isNum(o.lead_time_days) ? o.lead_time_days : '—') + ' 天', (isNum(r.lead_time_days) ? r.lead_time_days : '—') + ' 天', ''],
        ['生命周期', lcBadge(o.lifecycle), lcBadge(r.lifecycle), '']
      ].map(function (x) {
        return '<tr><td class="cmp-k">' + x[0] + '</td><td class="cmp-o">' + x[1] + '</td><td class="cmp-c">' + x[2] + '</td><td>' + x[3] + '</td></tr>';
      }).join('');
    } else if (state.originalState === 'loading') {
      sup = '<tr><td class="cmp-k">供货参数</td><td class="cmp-o" colspan="3">正在读取 <code>/api/part/' + esc(state.originalNo || '') + '</code> …</td></tr>';
    } else {
      sup = '<tr><td class="cmp-k">供电 / 温度 / 描述</td><td class="cmp-o" colspan="3">'
        + (state.originalState === 'missing'
            ? '原型号不在演示数据集中（/api/part 返回 404），规则表里仍保留了规则侧的比对原文。'
            : '原型号画像接口不可用，仅展示规则侧比对原文。')
        + '</td></tr>';
    }
    var note = '<p class="compare-note">带下划线的行表示该项未通过或需人工确认。「原型号」列取自规则引擎实际参与比对的原文，候选侧同样来自六维规则逐条计算；供货参数由 <code>/api/part/&lt;part_no&gt;</code> 画像与推荐结果行合成。</p>';

    return '<table class="compare">' + head + '<tbody>' + body + sup + '</tbody></table>' + note;
  }

  /* 原型号画像（来自 /api/part/<matched_part>，型号模式才有） */
  function profileHTML() {
    if (!(state.data && state.data.mode === 'part')) return '';
    if (state.originalState !== 'ok' || !state.original) {
      if (state.originalState === 'idle' || state.originalState === 'loading') return '';
      return '<div class="detail-h">原型号画像</div>'
        + '<p class="detail-loading">'
        + (state.originalState === 'missing'
            ? '原型号 <code>' + esc(state.originalNo || '') + '</code> 不在演示数据集中（<code>/api/part/&lt;part_no&gt;</code> 返回 404），无法给出画像。'
            : '原型号画像接口暂时不可用。')
        + '</p>';
    }
    var o = state.original;
    function cell(k, v, extra) {
      return '<div class="pc-cell"><span class="pc-k">' + esc(k) + '</span><span class="pc-v">' + v
        + (extra ? ' ' + extra : '') + '</span></div>';
    }
    var grid = [
      cell('生产厂商', esc(o.manufacturer || '—')),
      cell('器件品类', esc(o.category || '—')),
      cell('封装', esc(o.package || '—')),
      cell('引脚数', esc(pinText(o.pin_count))),
      cell('供电范围', esc(rangeText(o.vcc_min, o.vcc_max, 'V'))),
      cell('工作温度', esc(rangeText(o.temp_min, o.temp_max, '℃', '~'))),
      cell('库存', fmtNum(o.stock) + ' 片'),
      cell('单价', esc(fmtPrice(o.price_cny))),
      cell('交期', (isNum(o.lead_time_days) ? o.lead_time_days : '—') + ' 天'),
      cell('生命周期', lcBadge(o.lifecycle))
    ].join('');
    var desc = o.description ? '<p class="pc-desc" title="' + esc(o.description) + '">' + esc(o.description) + '</p>' : '';
    var link = o.datasheet_url
      ? '<a class="pc-link" href="' + esc(o.datasheet_url) + '" target="_blank" rel="noopener noreferrer">datasheet ↗</a>'
      : '<span class="pc-link is-off">暂无 datasheet 链接</span>';
    return '<div class="detail-h">原型号画像</div>'
      + '<div class="profile-card">'
      +   '<div class="pc-title"><span class="mono">' + esc(o.part_no || state.originalNo || '') + '</span>'
      +     (o.is_domestic ? '<span class="tag tag-domestic">国产</span>' : '<span class="tag">进口 / 海外</span>')
      +     link + '</div>'
      +   '<div class="pc-grid">' + grid + '</div>'
      +   desc
      + '</div>';
  }

  function detailHTML(r) {
    var reasons = (r.reasons || []).slice();
    return '<div class="detail">'
      + '<div class="detail-grid">'
      +   '<div class="detail-sec">'
      +     '<div class="detail-h">六维兼容规则（逐条依据）</div>'
      +     rulesTableHTML(r.checks)
      +   '</div>'
      +   '<div class="detail-sec">'
      +     '<div class="detail-h">供应链四因子</div>'
      +     supplyBarsHTML(r)
      +     profileHTML()
      +     '<div class="detail-h">原型号 vs 候选</div>'
      +     compareTableHTML(r)
      +   '</div>'
      + '</div>'
      + '<div class="detail-sec detail-foot">'
      +   '<div class="detail-h">判定理由（' + reasons.length + ' 条）</div>'
      +   (reasons.length
            ? '<ul class="reasons">' + reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>'
            : '<p class="detail-loading">后端未给出额外理由（规则全部达标时通常为空）。</p>')
      +   '<div class="summary-line"><span class="sl-cap">一句话结论</span>' + esc(r.summary || '—') + '</div>'
      + '</div>'
      + '</div>';
  }

  /* ============ 10. 对比表格视图 ============ */
  var COLS = [
    { key: '_rank', label: '#', cls: 'c-num', sortable: false },
    { key: 'part_no', label: '型号', cls: 'c-part' },
    { key: 'manufacturer', label: '厂商' },
    { key: 'category', label: '品类' },
    { key: 'package', label: '封装' },
    { key: 'pin_count', label: '引脚', cls: 'c-num' },
    { key: 'score', label: '综合分', cls: 'c-num' },
    { key: 'rule_score', label: '规则分', cls: 'c-num' },
    { key: 'similarity', label: '相似度', cls: 'c-num' },
    { key: 'supply', label: '供应链', cls: 'c-num' },
    { key: 'risk_level', label: '风险' },
    { key: 'replacement_tier', label: '替代等级' },
    { key: 'stock', label: '库存', cls: 'c-num' },
    { key: 'price_cny', label: '单价', cls: 'c-num' },
    { key: 'lead_time_days', label: '交期(天)', cls: 'c-num' },
    { key: 'lifecycle', label: '生命周期' },
    { key: '_detail', label: '详情', sortable: false }
  ];

  function sortValue(r, key) {
    if (key === 'risk_level') return RISK_ORDER[r.risk_level] !== undefined ? RISK_ORDER[r.risk_level] : 9;
    if (key === 'replacement_tier') return TIER_ORDER[r.replacement_tier] !== undefined ? TIER_ORDER[r.replacement_tier] : 9;
    if (key === 'lifecycle') return LC_ORDER[r.lifecycle] !== undefined ? LC_ORDER[r.lifecycle] : 9;
    var v = r[key];
    if (typeof v === 'number') return v;
    if (v === null || v === undefined) return '';
    return String(v);
  }

  function sortedResults() {
    var list = ((state.data && state.data.results) || []).slice();
    var key = state.sort.key, dir = state.sort.dir === 'asc' ? 1 : -1;
    if (key === '_rank' || !key) return list;
    list.sort(function (a, b) {
      var va = sortValue(a, key), vb = sortValue(b, key);
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
      var sa = String(va), sb = String(vb);
      return sa.localeCompare(sb, 'zh-Hans-CN') * dir;
    });
    return list;
  }

  function cellHTML(r, col, rank) {
    switch (col.key) {
      case '_rank': return '<td class="c-num c-faint">' + rank + '</td>';
      case 'part_no': return '<td class="c-part">' + esc(r.part_no) + '</td>';
      case 'manufacturer': return '<td>' + esc(r.manufacturer || '—') + '</td>';
      case 'category': return '<td>' + esc(r.category || '—') + '</td>';
      case 'package': return '<td>' + esc(r.package || '—') + '</td>';
      case 'pin_count': return '<td class="c-num' + (r.pin_count > 0 ? '' : ' c-faint') + '">' + (isNum(r.pin_count) && r.pin_count > 0 ? r.pin_count : '—') + '</td>';
      case 'score': return '<td class="c-num"><strong>' + fmtScore(r.score) + '</strong></td>';
      case 'rule_score': return '<td class="c-num">' + fmtScore(r.rule_score) + '</td>';
      case 'similarity': return '<td class="c-num">' + fmtScore(r.similarity) + '</td>';
      case 'supply': return '<td class="c-num">' + fmtScore(r.supply) + '</td>';
      case 'risk_level': return '<td>' + riskBadge(r.risk_level) + '</td>';
      case 'replacement_tier': return '<td>' + tierBadge(r.replacement_tier) + '</td>';
      case 'stock': return '<td class="c-num">' + fmtNum(r.stock) + '</td>';
      case 'price_cny': return '<td class="c-num">' + esc(fmtPrice(r.price_cny)) + '</td>';
      case 'lead_time_days': return '<td class="c-num">' + (isNum(r.lead_time_days) ? r.lead_time_days : '—') + '</td>';
      case 'lifecycle': return '<td>' + lcBadge(r.lifecycle) + '</td>';
      case '_detail': return '<td class="c-faint">' + (state.expanded[r.part_no] ? '收起 ▴' : '展开 ▾') + '</td>';
      default: return '<td>—</td>';
    }
  }

  function renderTable() {
    var thead = $('#compare-thead');
    var tbody = $('#compare-tbody');
    thead.innerHTML = '<tr>' + COLS.map(function (c) {
      var sorted = state.sort.key === c.key;
      var arrow = sorted ? (state.sort.dir === 'asc' ? '▲' : '▼') : '⇅';
      var cls = [];
      if (c.cls) cls.push(c.cls);
      if (c.sortable !== false) cls.push('sortable');
      if (sorted) cls.push('is-sorted');
      var attr = cls.length ? ' class="' + cls.join(' ') + '"' : '';
      if (c.sortable !== false) attr += ' data-sort="' + c.key + '"';
      return '<th' + attr + '>' + esc(c.label)
        + (c.sortable === false ? '' : '<span class="th-arrow">' + arrow + '</span>') + '</th>';
    }).join('') + '</tr>';

    var list = sortedResults();
    tbody.innerHTML = list.map(function (r, i) {
      var open = !!state.expanded[r.part_no];
      var main = '<tr class="row-main' + (open ? ' is-open' : '') + '" data-part="' + esc(r.part_no) + '" tabindex="0">'
        + COLS.map(function (c) { return cellHTML(r, c, i + 1); }).join('') + '</tr>';
      var det = open
        ? '<tr class="row-detail"><td colspan="' + COLS.length + '">' + detailHTML(r) + '</td></tr>'
        : '';
      return main + det;
    }).join('');
  }

  /* ============ 11. 排除清单 ============ */
  function renderRejected(data) {
    var box = $('#rejected-block');
    var list = data.rejected || [];
    if (!list.length) { box.setAttribute('hidden', ''); return; }
    $('#rejected-count').textContent = list.length + ' 条';
    $('#rejected-list').innerHTML = list.map(function (r) {
      var meta = [r.manufacturer, r.package].filter(Boolean).join(' · ');
      var reasons = (r.reasons && r.reasons.length) ? r.reasons : ['命中零容忍硬约束，未通过规则过滤'];
      return '<div class="rejected-item">'
        + '<div>'
        +   '<div class="rejected-part">' + esc(r.part_no) + '</div>'
        +   (meta ? '<div class="rejected-meta">' + esc(meta) + '</div>' : '')
        +   '<div class="rejected-nums">相似度 ' + fmtScore(r.similarity) + ' · 得分 ' + fmtScore(r.score) + '</div>'
        +   '<div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">' + riskBadge(r.risk_level) + tierBadge(r.replacement_tier) + '</div>'
        + '</div>'
        + '<div class="rejected-why"><ul>' + reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></div>'
        + '</div>';
    }).join('');
    box.removeAttribute('hidden');
  }

  /* ============ 12. 结果渲染总入口 ============ */
  function renderResults() {
    var data = state.data;
    if (!data) return;
    renderStatus(data);
    var results = data.results || [];
    var box = $('#results-block');
    $('#result-count').textContent = results.length;

    if (!results.length) {
      box.setAttribute('hidden', '');
      renderEmpty(data);
      renderRejected(data);
      var rj = $('#rejected-block');
      if (rj && (data.rejected || []).length) rj.setAttribute('open', '');
      return;
    }

    hideEmpty();
    box.removeAttribute('hidden');
    $('#result-sub').textContent = state.view === 'cards'
      ? '按综合得分降序 · 每条可展开六维规则与供应链四因子'
      : '点击表头排序 · 点击行展开明细';

    var cards = $('#cards-view'), table = $('#table-view');
    if (state.view === 'cards') {
      cards.removeAttribute('hidden');
      table.setAttribute('hidden', '');
      renderCards();
    } else {
      table.removeAttribute('hidden');
      cards.setAttribute('hidden', '');
      renderTable();
    }
    renderRejected(data);
    $('#rejected-block').removeAttribute('open');
  }

  /* ============ 13. 结果区交互 ============ */
  function toggleExpand(partNo) {
    if (!partNo) return;
    if (state.expanded[partNo]) delete state.expanded[partNo];
    else state.expanded[partNo] = true;
    if (state.view === 'cards') renderCards(); else renderTable();
  }

  function initResultInteractions() {
    var cards = $('#cards-view');
    cards.addEventListener('click', function (e) {
      var t = e.target;
      var vote = t.closest ? t.closest('.votebtn') : null;
      if (vote) { sendVote(vote.getAttribute('data-vote-part'), vote.getAttribute('data-vote'), vote); return; }
      var btn = t.closest ? t.closest('[data-act="toggle"]') : null;
      if (btn) toggleExpand(btn.getAttribute('data-part'));
    });

    var tbody = $('#compare-tbody');
    tbody.addEventListener('click', function (e) {
      var vote = e.target.closest ? e.target.closest('.votebtn') : null;
      if (vote) { sendVote(vote.getAttribute('data-vote-part'), vote.getAttribute('data-vote'), vote); return; }
      var row = e.target.closest ? e.target.closest('tr.row-main') : null;
      if (row) toggleExpand(row.getAttribute('data-part'));
    });
    tbody.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var row = e.target.closest ? e.target.closest('tr.row-main') : null;
      if (!row) return;
      e.preventDefault();
      toggleExpand(row.getAttribute('data-part'));
    });

    var thead = $('#compare-thead');
    thead.addEventListener('click', function (e) {
      var th = e.target.closest ? e.target.closest('th[data-sort]') : null;
      if (!th) return;
      var key = th.getAttribute('data-sort');
      if (state.sort.key === key) state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
      else state.sort = { key: key, dir: (key === 'risk_level' || key === 'replacement_tier' || key === 'lifecycle' || key === 'price_cny' || key === 'lead_time_days' || key === 'pin_count') ? 'asc' : 'desc' };
      renderTable();
    });

    $$('#view-switch .seg-btn').forEach(function (b) {
      b.addEventListener('click', function () {
        state.view = b.getAttribute('data-view');
        $$('#view-switch .seg-btn').forEach(function (x) {
          var on = x === b;
          x.classList.toggle('is-active', on);
          x.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        if (state.data && (state.data.results || []).length) renderResults();
      });
    });
  }

  function sendVote(partNo, vote, el) {
    state.votes[partNo] = vote;
    $$('.votebtn').forEach(function (b) {
      if (b.getAttribute('data-vote-part') !== partNo) return;
      b.classList.toggle('is-on', b.getAttribute('data-vote') === vote);
    });
    toast('已记录「' + partNo + '」的反馈（' + (vote === 'up' ? '可用' : '不适用') + '）', 'ok');
    API.feedback({ query: state.query, part_no: partNo, vote: vote }).catch(function (err) {
      toast('反馈上报失败：' + (err && err.message ? err.message : '未知错误'), 'error');
    });
  }

  /* ============ 14. 数据总览 ============ */
  function loadStats() {
    if (state.statsState === 'loading' || state.statsState === 'ok') return;
    state.statsState = 'loading';
    API.stats().then(function (s) {
      state.stats = s;
      state.statsState = 'ok';
      renderStats(s);
      renderBadge(s);
    }).catch(function (err) {
      state.statsState = 'error';
      var sk = $('#stats-skeleton');
      if (sk) sk.setAttribute('hidden', '');
      var el = $('#stats-empty');
      if (el) {
        el.removeAttribute('hidden');
        $('.empty-hint', el).textContent = '统计数据加载失败：' + (err && err.message ? err.message : '未知错误');
      }
      var cards = $('#stat-cards');
      if (cards) cards.innerHTML = '';
    });
  }

  function renderBadge(s) {
    var makers = s.manufacturers;
    var makerCount = typeof makers === 'number' ? makers : (makers && typeof makers === 'object' ? Object.keys(makers).length : null);
    var cats = s.categories;
    var catCount = typeof cats === 'number' ? cats : (cats && typeof cats === 'object' ? Object.keys(cats).length : null);
    var txt = [];
    if (isNum(s.total)) txt.push(s.total + ' 条');
    if (makerCount !== null) txt.push(makerCount + ' 厂商');
    if (catCount !== null) txt.push(catCount + ' 品类');
    var el = $('#badge-nums');
    if (el && txt.length) el.textContent = txt.join(' · ');
  }

  var LC_COLORS = {
    '量产': '#15803d', '预览': '#2563eb', '未知': '#94a3b8', 'NRND': '#d97706', 'EOL': '#b91c1c'
  };

  function renderStats(s) {
    var sk = $('#stats-skeleton');
    if (sk) sk.setAttribute('hidden', '');
    /* --- 数字卡片 --- */
    var makers = s.manufacturers;
    var makerCount = typeof makers === 'number' ? makers : (makers && typeof makers === 'object' ? Object.keys(makers).length : '—');
    var cats = s.categories;
    var catCount = typeof cats === 'number' ? cats : (cats && typeof cats === 'object' ? Object.keys(cats).length : '—');
    var alerts = s.alerts || [];

    $('#stat-cards').innerHTML = [
      { label: '演示数据条目', value: fmtNum(s.total), foot: '公开 jlcparts 数据集抽取子集', cls: '' },
      { label: '覆盖厂商', value: fmtNum(makerCount), foot: '含国产与海外原厂 / 代理商料号', cls: 'is-teal' },
      { label: '器件品类', value: fmtNum(catCount), foot: '规则库覆盖的品类范围', cls: '' },
      { label: '供应链告警', value: fmtNum(alerts.length), foot: '库存<1000 或 EOL / NRND', cls: 'is-amber' },
      { label: '风险关注条目', value: fmtNum(isNum(s.watch_count) ? s.watch_count : alerts.length), foot: '列入持续观察清单（watch_count）', cls: 'is-green' }
    ].map(function (c) {
      return '<div class="stat-card ' + c.cls + '">'
        + '<div class="stat-label">' + esc(c.label) + '</div>'
        + '<div class="stat-value">' + esc(c.value) + '</div>'
        + '<div class="stat-foot">' + esc(c.foot) + '</div>'
        + '</div>';
    }).join('');

    /* --- 品类分布条形图 --- */
    var byCat = (s.by_category || []).slice();
    var maxCat = byCat.reduce(function (m, x) { return Math.max(m, x.count || 0); }, 1);
    $('#chart-category').innerHTML = byCat.length ? byCat.map(function (x) {
      var pct = (x.count || 0) / maxCat * 100;
      return '<div class="hbar-row" title="' + esc(x.category) + '：' + esc(x.count) + ' 条">'
        + '<span class="hbar-label">' + esc(x.category) + '</span>'
        + '<span class="hbar-track"><i class="hbar-fill" style="width:' + pct.toFixed(2) + '%"></i></span>'
        + '<span class="hbar-val">' + esc(x.count) + '</span>'
        + '</div>';
    }).join('') : '<p class="detail-loading">无品类数据。</p>';

    /* --- 生命周期环形图（手写 conic-gradient） --- */
    /* 实测 /api/stats 的 lifecycle 是 [{lifecycle,count}] 数组；这里同时兼容
       {生命周期: 条数} 对象形式（旧 data_loader.stats() 的返回形状），避免换数据源即崩。 */
    var lcRaw = s.lifecycle;
    var lc = [];
    if (Object.prototype.toString.call(lcRaw) === '[object Array]') {
      lc = lcRaw.slice();
    } else if (lcRaw && typeof lcRaw === 'object') {
      lc = Object.keys(lcRaw).map(function (k) { return { lifecycle: k, count: lcRaw[k] }; });
    }
    var total = lc.reduce(function (a, b) { return a + (b.count || 0); }, 0) || 1;
    var acc = 0;
    var stops = lc.map(function (x) {
      var from = acc / total * 100;
      acc += (x.count || 0);
      var to = acc / total * 100;
      var color = LC_COLORS[x.lifecycle] || '#a5b4fc';
      return color + ' ' + from.toFixed(3) + '% ' + to.toFixed(3) + '%';
    });
    var donut = $('#chart-lifecycle');
    donut.style.background = stops.length ? ('conic-gradient(' + stops.join(', ') + ')') : '#e2e8f0';
    donut.innerHTML = '<div class="donut-center"><b>' + esc(total) + '</b><span>条目总计</span></div>';

    $('#chart-lifecycle-legend').innerHTML = lc.map(function (x) {
      var color = LC_COLORS[x.lifecycle] || '#a5b4fc';
      var pct = ((x.count || 0) / total * 100);
      return '<li><span class="lg-swatch" style="background:' + color + '"></span>'
        + '<span class="lg-name">' + esc(x.lifecycle) + '</span>'
        + '<span class="lg-val">' + esc(x.count) + '</span>'
        + '<span class="lg-pct">' + pct.toFixed(1) + '%</span></li>';
    }).join('');

    /* --- 告警清单 --- */
    $('#alerts-count').textContent = alerts.length;
    $('#alerts-body').innerHTML = alerts.length ? alerts.map(function (a) {
      var low = isNum(a.stock) && a.stock < 1000;
      return '<tr>'
        + '<td class="t-part">' + esc(a.part_no) + '</td>'
        + '<td>' + esc(a.manufacturer || '—') + '</td>'
        + '<td>' + esc(a.category || '—') + '</td>'
        + '<td class="num ' + (low ? 'mono' : '') + '" style="' + (low ? 'color:#b45309;font-weight:600' : '') + '">' + fmtNum(a.stock) + '</td>'
        + '<td>' + lcBadge(a.lifecycle) + '</td>'
        + '<td class="t-reason">' + esc(a.reason || '—') + '</td>'
        + '</tr>';
    }).join('') : '<tr><td colspan="6" class="c-faint">当前没有触发告警的条目。</td></tr>';
    $('#stats-empty').setAttribute('hidden', '');
  }

  /* ============ 15. 页头初始化 ============ */
  function initHeader() {
    API.health().then(function (h) {
      var v = (h && h.version) ? h.version : 'ok';
      $('#version-chip').textContent = 'v' + String(v).replace(/^v/, '') + ' · ' + (h && h.status ? h.status : 'ok');
      $('#footer-version').textContent = String(v);
    }).catch(function () {
      $('#version-chip').textContent = '接口未就绪';
      $('#footer-version').textContent = '不可用';
    });
  }

  /* ============ 16. 启动 ============ */
  function init() {
    initTabs();
    initSearch();
    initResultInteractions();
    initHeader();
    loadStats();
    var input = $('#q');
    if (input) input.focus();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
