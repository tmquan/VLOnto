/* VLOnto - dashboard (ECharts 6, canvas renderer). Filters (document type, issue-year range, legal area) are applied in the
   browser to per-document columns (data/dash_extra.js) so every document chart, the change chart and the most-cited tables
   stay linked; court, Q&A, term and news charts use the aggregates of data/dashboard.js and apply the dimensions they have. */
(function () {
  'use strict';
  var VL = window.VL, M = window.__VLONTO_METRICS;
  VL.chrome();
  M.page = 'dashboard';
  var S = window.VLONTO.stats, DB = window.VLONTO.dashboard, X = window.VLONTO.dash_extra;
  var FONT = '"Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math", sans-serif';
  var mq = window.matchMedia('(max-width: 600px)');
  var N = X.docs.type.length;
  var TYPES = X.types, AREAS = X.areas, ISSUERS = X.issuers, VALID = X.validity, KINDS = X.change_kinds;
  var UNK = VALID.indexOf('unknown');
  /* One year range for every dated record: the issue year of a document, the effective year of a change event and the year
     of a court decision or Q&A. While the range is untouched every chart shows all records - undated ones in their own
     bucket - so the totals equal the knowledge graph; once the user narrows it, undated records are left out and the
     captions say how many. */
  var DY0 = 9999, DY1 = 0;
  X.docs.year.forEach(function (y) { if (y > 0) { if (y < DY0) DY0 = y; if (y > DY1) DY1 = y; } });
  var Y0 = DY0, Y1 = DY1;
  function widen(y) { if (y > 0) { if (y < Y0) Y0 = y; if (y > Y1) Y1 = y; } }
  X.changes.year.forEach(widen);
  DB.decisions_by_category_year.forEach(function (r) { widen(r.year); });
  DB.qas_by_area_year.forEach(function (r) { widen(r.year); });
  var F = { type: -1, area: -1, y0: Y0, y1: Y1 };
  var charts = {}, finished = 0, total = 0, readySent = false;
  var NOTE = {};   /* undated records left out by a narrowed year range, filled in by the chart builders */
  VL.$('#asof').textContent = (S && S.validity_as_of) || '2026-11-08';

  /* ------------------------------------------------------------------ filters */
  function yearActive() { return F.y0 !== Y0 || F.y1 !== Y1; }
  function yearOk(y) { return y > 0 ? (y >= F.y0 && y <= F.y1) : !yearActive(); }
  function docOk(i, skip) {
    if (skip !== 'type' && F.type >= 0 && X.docs.type[i] !== F.type) return false;
    if (skip !== 'area' && F.area >= 0 && X.docs.area[i] !== F.area) return false;
    return yearOk(X.docs.year[i]);
  }
  /* change events: type and area filters apply to the affected document, the year range to the effective year */
  function changeOk(j) {
    var d = X.changes.affected[j];
    if (F.type >= 0 && X.docs.type[d] !== F.type) return false;
    return !(F.area >= 0 && X.docs.area[d] !== F.area);
  }
  function plural(n, one, many) { return VL.fmt(n) + ' ' + (n === 1 ? one : many); }
  function listJoin(a) { return a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]; }
  var typeSel = VL.$('#f-type'), y0Sel = VL.$('#f-y0'), y1Sel = VL.$('#f-y1'), areaSel = VL.$('#f-area');
  typeSel.innerHTML = '<option value="-1">All types</option>' + TYPES.map(function (t, i) { return '<option value="' + i + '">' + VL.esc(t.en + ' · ' + t.vi) + '</option>'; }).join('');
  var yearsOpts = '';
  for (var y = Y0; y <= Y1; y++) yearsOpts += '<option value="' + y + '">' + y + '</option>';
  y0Sel.innerHTML = yearsOpts;
  y1Sel.innerHTML = yearsOpts;
  var areaCount = {};
  X.docs.area.forEach(function (a) { if (a >= 0) areaCount[a] = (areaCount[a] || 0) + 1; });
  var areaOrder = Object.keys(areaCount).map(Number).sort(function (a, b) { return AREAS[a][2].localeCompare(AREAS[b][2]); });
  areaSel.innerHTML = '<option value="-1">All areas</option>' + areaOrder.map(function (a) { return '<option value="' + a + '">' + VL.esc(AREAS[a][2]) + '</option>'; }).join('');
  function syncControls() {
    typeSel.value = String(F.type); areaSel.value = String(F.area); y0Sel.value = String(F.y0); y1Sel.value = String(F.y1);
  }
  /* the line under the filters: what is selected and, while a year range is set, which undated records it leaves out */
  function noteFilters() {
    var parts = [];
    if (F.type >= 0) parts.push(TYPES[F.type].en + ' (' + TYPES[F.type].vi + ')');
    if (yearActive()) parts.push('years ' + F.y0 + '–' + F.y1);
    if (F.area >= 0) parts.push(AREAS[F.area][2] + ' (' + AREAS[F.area][1] + ')');
    var t = parts.length ? 'Showing: ' + parts.join(' · ') + '.'
      : 'No filter set: all ' + VL.fmt(N) + ' documents and every related record, undated ones included.';
    if (yearActive()) {
      var out = [];
      if (NOTE.docs) out.push(plural(NOTE.docs, 'document', 'documents') + ' without an issue year');
      if (NOTE.changes) out.push(plural(NOTE.changes, 'change event', 'change events') + ' without an effective date');
      if (NOTE.decisions) out.push(plural(NOTE.decisions, 'court decision', 'court decisions') + ' without a year');
      if (NOTE.qa) out.push(plural(NOTE.qa, 'Q&A', 'Q&As') + ' without a year');
      if (out.length) t += ' The year range leaves out ' + listJoin(out) + '.';
    }
    VL.$('#f-active').textContent = t;
  }
  function setFilter(k, v) {
    if (k === 'y0') { F.y0 = Math.min(+v, F.y1); }
    else if (k === 'y1') { F.y1 = Math.max(+v, F.y0); }
    else F[k] = +v;
    syncControls();
    update();
  }
  typeSel.addEventListener('change', function () { setFilter('type', typeSel.value); });
  areaSel.addEventListener('change', function () { setFilter('area', areaSel.value); });
  y0Sel.addEventListener('change', function () { setFilter('y0', y0Sel.value); });
  y1Sel.addEventListener('change', function () { setFilter('y1', y1Sel.value); });
  VL.$('#f-reset').addEventListener('click', function () { F = { type: -1, area: -1, y0: Y0, y1: Y1 }; syncControls(); update(); });

  /* ------------------------------------------------------------------ chart helpers */
  function mob() { return mq.matches; }
  /* chart colours of the current theme (css/site.css --chart-*, --hue-*); series palettes are read at render time,
     so a theme switch only has to re-render (update + staticCharts) */
  var C = {};
  function readTheme() {
    C = { fg: VL.tok('--chart-fg') || '#2f3a56', muted: VL.tok('--chart-muted') || '#5a6684', grid: VL.tok('--chart-grid') || '#e6ebf5',
      axis: VL.tok('--chart-axis') || '#c6cfe2', fade: VL.tok('--chart-fade') || 'rgba(160, 172, 200, 0.35)',
      tipBg: VL.tok('--chart-tip-bg') || '#ffffff', tipLine: VL.tok('--chart-tip-line') || '#c6cfe2', tipFg: VL.tok('--chart-tip-fg') || '#111a30' };
    M.chartTheme = { theme: VL.theme(), fg: C.fg, grid: C.grid };
  }
  readTheme();
  var hue = VL.hue;
  function hues(names) { return names.map(function (n) { return VL.hue(n); }); }
  /* axis lines, ticks, labels and split lines in theme colours unless a chart set its own */
  function themeAxes(o) {
    ['xAxis', 'yAxis'].forEach(function (k) {
      if (!o[k]) return;
      (Array.isArray(o[k]) ? o[k] : [o[k]]).forEach(function (a) {
        a.axisLine = a.axisLine || {};
        a.axisLine.lineStyle = Object.assign({ color: C.axis }, a.axisLine.lineStyle || {});
        a.axisTick = a.axisTick || {};
        a.axisTick.lineStyle = Object.assign({ color: C.axis }, a.axisTick.lineStyle || {});
        a.axisLabel = a.axisLabel || {};
        if (!a.axisLabel.color) a.axisLabel.color = C.muted;
        if (a.type === 'value') {
          a.splitLine = a.splitLine || {};
          a.splitLine.lineStyle = Object.assign({ color: C.grid }, a.splitLine.lineStyle || {});
        }
      });
    });
    return o;
  }
  function base(extra) {
    var o = {
      animation: false,
      textStyle: { fontFamily: FONT, color: C.fg, fontSize: mob() ? 11 : 12 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true, textStyle: { fontFamily: FONT, fontSize: 12 } },
      grid: { left: 8, right: mob() ? 14 : 22, top: 40, bottom: 8, containLabel: true }
    };
    Object.keys(extra || {}).forEach(function (k) { o[k] = extra[k]; });
    if (o.tooltip) {
      o.tooltip.backgroundColor = o.tooltip.backgroundColor || C.tipBg;
      o.tooltip.borderColor = o.tooltip.borderColor || C.tipLine;
      o.tooltip.textStyle = Object.assign({ fontFamily: FONT, fontSize: 12 }, o.tooltip.textStyle || {}, { color: C.tipFg });
    }
    return themeAxes(o);
  }
  /* text measuring (same font as the charts) so legends and wrapped axis labels get the room they need */
  var _mctx = null;
  function textW(s, size) {
    if (!_mctx) _mctx = document.createElement('canvas').getContext('2d');
    _mctx.font = '400 ' + size + 'px ' + FONT;
    return _mctx.measureText(String(s)).width;
  }
  function legendFont() { return mob() ? 10.5 : 12; }
  function legendGap() { return mob() ? 8 : 10; }
  /* plain (multi-row) legends: never paginated; returns the grid top that clears all legend rows */
  function legendTop(id, names) {
    var el = VL.$('#' + id), W = Math.max(120, el.clientWidth), size = legendFont(), gap = legendGap(), rows = 1, x = 0;
    names.forEach(function (n) {
      var w = 12 + 5 + textW(n, size) + gap;
      if (x > 0 && x + w - gap > W) { rows++; x = 0; }
      x += w;
    });
    return rows * (Math.ceil(size * 1.3) + gap) + 8;
  }
  function legend(extra) {
    var l = { type: 'plain', top: 0, left: 0, right: 0, itemWidth: 12, itemHeight: 10, itemGap: legendGap(), inactiveColor: C.axis,
      textStyle: { fontFamily: FONT, fontSize: legendFont(), color: C.fg } };
    Object.keys(extra || {}).forEach(function (k) { l[k] = extra[k]; });
    return l;
  }
  function catW(desk, phone) { return mob() ? (phone || 140) : (desk || 250); }
  function catAxisLabel(width) {
    return { fontFamily: FONT, fontSize: mob() ? 10.5 : 11.5, color: C.fg, width: width || catW(), overflow: 'break', lineHeight: mob() ? 13 : 14 };
  }
  /* row pitch for a category axis whose labels wrap at `width` (ECharts overflow: 'break' wraps at spaces) */
  function catPitch(labels, width, minPitch) {
    var size = mob() ? 10.5 : 11.5, lh = mob() ? 13 : 14, sp = textW(' ', size), mx = 1;
    width -= 14;   /* ECharts wraps a little earlier than the raw text width suggests */
    labels.forEach(function (t) {
      var words = String(t).split(/\s+/), lines = 1, cur = 0;
      words.forEach(function (wd) {
        var ww = textW(wd, size);
        if (cur > 0 && cur + sp + ww > width) { lines++; cur = ww; } else cur += (cur > 0 ? sp : 0) + ww;
      });
      mx = Math.max(mx, lines);
    });
    return Math.max(minPitch, mx * lh + 10);
  }
  function axisK(v) { return v >= 1e6 ? (Math.round(v / 1e5) / 10) + 'M' : v >= 1000 ? (Math.round(v / 100) / 10) + 'k' : String(v); }
  var valueAxis = function (extra) {
    var a = { type: 'value', axisLabel: { fontFamily: FONT, fontSize: mob() ? 10.5 : 11.5, color: C.muted, formatter: axisK, hideOverlap: true }, splitLine: { lineStyle: { color: C.grid } } };
    Object.keys(extra || {}).forEach(function (k) { a[k] = extra[k]; });
    return a;
  };
  function setHeight(id, rows, pitch, extra) {
    var el = VL.$('#' + id);
    var h = Math.max(240, Math.round(rows * (pitch || (mob() ? 30 : 26)) + (extra || 70)));
    if (el.style.height !== h + 'px') { el.style.height = h + 'px'; if (charts[id]) charts[id].resize(); }
  }
  function chart(id) {
    if (!charts[id]) {
      charts[id] = echarts.init(VL.$('#' + id), null, { renderer: 'canvas' });
      total++;
      charts[id].on('finished', function () { if (!charts[id].__done) { charts[id].__done = true; finished++; checkReady(); } });
    }
    return charts[id];
  }
  function checkReady() {
    if (!readySent && finished >= total && total > 0) {
      readySent = true;
      setTimeout(function () { VL.setReady({ charts: total }); }, 120);
    }
  }
  function fade(color, on) { return on ? color : C.fade; }

  /* category axis over years with bucket labels at either end ('before 2000', 'no year'): year labels are thinned so that
     they never collide with each other or with a bucket label, and bucket labels are always shown */
  function yearAxis(id, cats) {
    var el = VL.$('#' + id), n = Math.max(1, cats.length), fs = mob() ? 10.5 : 11.5;
    var cw = Math.max(120, el.clientWidth - (mob() ? 56 : 66)) / n, yw = textW('2000', fs) + 10;
    var step = Math.max(1, Math.ceil(yw / cw)), first = -1, special = [];
    cats.forEach(function (c, i) {
      if (/^\d{4}$/.test(c)) { if (first < 0) first = i; } else special.push([i, textW(c, fs)]);
    });
    function show(i) {
      if (!/^\d{4}$/.test(cats[i])) return true;
      if ((i - first) % step) return false;
      for (var k = 0; k < special.length; k++) if (Math.abs(i - special[k][0]) * cw < (special[k][1] + yw) / 2 + 4) return false;
      return true;
    }
    return { type: 'category', data: cats, axisTick: { alignWithLabel: true, interval: show },
      axisLabel: { fontFamily: FONT, fontSize: fs, color: C.muted, hideOverlap: true, interval: show } };
  }
  function sumCol(rows, col) { return rows.reduce(function (s, r) { return s + (r[col] || 0); }, 0); }

  /* ------------------------------------------------------------------ aggregations + charts */
  function typeYear() {
    var lo = Math.max(F.y0, DY0), hi = Math.min(F.y1, DY1), cats = [], undated = !yearActive(), left = 0, other = null;
    for (var y = lo; y <= hi; y++) cats.push(String(y));
    var nY = cats.length;
    if (undated) cats.push('no year');
    var cnt = TYPES.map(function () { return cats.map(function () { return 0; }); });
    for (var i = 0; i < N; i++) {
      /* every type is counted (unselected types are drawn faded); the area filter and the year range apply */
      if (F.area >= 0 && X.docs.area[i] !== F.area) continue;
      var yy = X.docs.year[i], t = X.docs.type[i], col;
      if (yy > 0) { if (yy < lo || yy > hi) continue; col = yy - lo; }
      else if (undated) col = nY;
      else { if (F.type < 0 || t === F.type) left++; continue; }
      if (t >= 0) cnt[t][col]++;
      else { if (!other) other = cats.map(function () { return 0; }); other[col]++; }
    }
    var sum = 0;
    var series = TYPES.map(function (t, ti) {
      var on = F.type < 0 || F.type === ti;
      cnt[ti].forEach(function (v) { if (on) sum += v; });
      return { name: t.en, type: 'bar', stack: 'docs', barCategoryGap: '18%', data: cnt[ti], itemStyle: { color: fade(VL.TYPE_COLORS[t.code], on) }, emphasis: { focus: 'series' } };
    }).filter(function (s) { return s.data.some(function (v) { return v > 0; }); });
    if (other) {
      series.push({ name: 'type not recorded', type: 'bar', stack: 'docs', data: other, itemStyle: { color: fade(hue('slate'), F.type < 0) } });
      if (F.type < 0) other.forEach(function (v) { sum += v; });
    }
    M.typeYearSum = sum;
    NOTE.docs = left;
    var noYear = undated ? cnt.reduce(function (s, r) { return s + r[nY]; }, 0) + (other ? other[nY] : 0) : 0;
    VL.$('#sub-type-year').textContent = 'Stacked by document type' +
      (noYear ? '; “no year” holds the ' + plural(noYear, 'document', 'documents') + ' without an issue year' : '') +
      (left ? '; the year range leaves out ' + plural(left, 'document', 'documents') + ' without an issue year' : '') +
      '. Click a segment to filter by its type.';
    var c = chart('c-type-year');
    c.setOption(base({
      legend: legend(),
      grid: { left: 8, right: 16, top: legendTop('c-type-year', series.map(function (s) { return s.name; })), bottom: 8, containLabel: true },
      xAxis: yearAxis('c-type-year', cats),
      yAxis: valueAxis(),
      series: series
    }), true);
  }
  function validityByType() {
    var cnt = TYPES.map(function () { return VALID.map(function () { return 0; }); });
    for (var i = 0; i < N; i++) {
      if (!docOk(i, 'type')) continue;
      var t = X.docs.type[i], v = X.docs.validity[i];
      if (v < 0) v = UNK;
      if (t >= 0 && v >= 0) cnt[t][v]++;
    }
    var tot = cnt.map(function (r) { return r.reduce(function (a, b) { return a + b; }, 0); });
    var rows = TYPES.map(function (t, i) { return i; }).filter(function (i) { return tot[i] > 0; });
    var order = VL.VALIDITY_ORDER.map(function (v) { return VALID.indexOf(v); }).filter(function (ix) { return ix >= 0; });
    var series = order.map(function (vi) {
      var name = VALID[vi], meta = VL.VALIDITY[name] || VL.VALIDITY.unknown;
      return { name: meta.en, type: 'bar', stack: 'v', barWidth: '62%',
        data: rows.map(function (ti) { return { value: tot[ti] ? Math.round(1000 * cnt[ti][vi] / tot[ti]) / 10 : 0, n: cnt[ti][vi], itemStyle: { color: fade(meta.color, F.type < 0 || F.type === ti) } }; }),
        itemStyle: { color: meta.color } };
    });
    var lt = legendTop('c-validity', series.map(function (s) { return s.name; }));
    var tl = rows.map(function (ti) { return TYPES[ti].en; }), tw = catW(120, 92);
    setHeight('c-validity', rows.length, catPitch(tl, tw, mob() ? 30 : 28), lt + 40);
    var c = chart('c-validity');
    c.setOption(base({
      legend: legend(),
      grid: { left: 8, right: mob() ? 14 : 22, top: lt, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true, textStyle: { fontFamily: FONT, fontSize: 12 },
        formatter: function (ps) {
          var s = VL.esc(ps[0].name) + ' (' + VL.fmt(tot[rows[ps[0].dataIndex]]) + ')';
          ps.forEach(function (p) { if (p.data.n) s += '<br>' + p.marker + VL.esc(p.seriesName) + ': ' + VL.fmt(p.data.n) + ' (' + p.value + '%)'; });
          return s;
        } },
      xAxis: valueAxis({ max: 100, axisLabel: { fontFamily: FONT, fontSize: mob() ? 10.5 : 11.5, color: C.muted, formatter: '{value}%' } }),
      yAxis: { type: 'category', inverse: true, data: tl, axisLabel: catAxisLabel(tw), axisTick: { show: false } },
      series: series
    }), true);
    c.__rows = rows;
  }
  function ranks() {
    var cnt = [0, 0, 0, 0, 0, 0];
    for (var i = 0; i < N; i++) if (docOk(i)) cnt[X.docs.rank[i]]++;
    var SHORT = ['Constitution', 'Codes, laws, NA resolutions', 'Ordinances, NASC resolutions', 'Decrees, joint resolutions', 'Prime Minister decisions', 'Circulars, other decisions'];
    var full = (X.ranks || []).map(function (r) { return r.en; });
    var labels = SHORT.map(function (s, r) { return r + ' · ' + s; }), rw = catW(210, 150);
    setHeight('c-ranks', 6, catPitch(labels, rw, mob() ? 30 : 28), 50);
    chart('c-ranks').setOption(base({
      grid: { left: 8, right: mob() ? 44 : 56, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 },
        formatter: function (p) { return 'Rank ' + p.dataIndex + ' · ' + VL.esc(full[p.dataIndex] || SHORT[p.dataIndex]) + '<br>' + VL.fmt(p.value) + ' documents'; } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: labels, axisLabel: catAxisLabel(rw), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '58%', data: cnt.map(function (v, r) { return { value: v, itemStyle: { color: hues(['yellow', 'rose', 'pink', 'blue', 'cyan', 'green'])[r] } }; }),
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 11, color: C.fg, formatter: function (p) { return VL.fmt(p.value); } } }]
    }), true);
  }
  function areasChart() {
    var cnt = {}, none = 0;
    for (var i = 0; i < N; i++) { if (!docOk(i, 'area')) continue; var a = X.docs.area[i]; if (a >= 0) cnt[a] = (cnt[a] || 0) + 1; else none++; }
    var rows = Object.keys(cnt).map(Number).sort(function (a, b) { return cnt[b] - cnt[a]; });
    if (none) { rows.push(-1); cnt[-1] = none; }   /* documents without a recorded area get their own (unclickable) bar */
    function lab(a) { return a < 0 ? 'no area recorded' : AREAS[a][2]; }
    setHeight('c-areas', rows.length, catPitch(rows.map(lab), catW(), mob() ? 26 : 24), 40);
    var c = chart('c-areas');
    c.setOption(base({
      grid: { left: 8, right: mob() ? 48 : 60, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) {
        var k = rows[p.dataIndex];
        if (k < 0) return 'No legal area recorded<br>' + VL.fmt(p.value) + ' documents';
        var a = AREAS[k]; return VL.esc(a[2]) + '<br><i>' + VL.esc(a[1]) + '</i><br>' + VL.fmt(p.value) + ' documents'; } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: rows.map(lab), axisLabel: catAxisLabel(), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '64%', cursor: 'pointer', data: rows.map(function (a) { return { value: cnt[a], itemStyle: { color: a < 0 ? hue('slate') : F.area < 0 || F.area === a ? hue('blue') : VL.alpha(hue('blue'), 0.3) } }; }),
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.compact(p.value); } } }]
    }), true);
    c.__rows = rows.map(function (a) { return a < 0 ? null : a; });
  }
  function issuersChart() {
    var cnt = {}, noIss = 0;
    for (var i = 0; i < N; i++) { if (!docOk(i)) continue; var s = X.docs.issuer[i]; if (s >= 0) cnt[s] = (cnt[s] || 0) + 1; else noIss++; }
    var ex = X.docs.extra_issuers;
    for (var k = 0; k < ex.length; k += 2) if (docOk(ex[k])) cnt[ex[k + 1]] = (cnt[ex[k + 1]] || 0) + 1;
    var nIss = Object.keys(cnt).length;
    var rows = Object.keys(cnt).map(Number).sort(function (a, b) { return cnt[b] - cnt[a]; }).slice(0, 15);
    VL.$('#sub-issuers').textContent = (nIss > rows.length ? 'Top ' + rows.length + ' of ' + nIss : 'All ' + nIss) +
      ' issuing bodies in the selection; joint documents count for every issuer' +
      (noIss ? '; ' + plural(noIss, 'document has', 'documents have') + ' no issuer recorded' : '') + '.';
    setHeight('c-issuers', Math.max(rows.length, 3), catPitch(rows.map(function (s) { return ISSUERS[s][2]; }), catW(), mob() ? 26 : 24), 40);
    chart('c-issuers').setOption(base({
      grid: { left: 8, right: mob() ? 48 : 60, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) { var r = ISSUERS[rows[p.dataIndex]]; return VL.esc(r[2]) + '<br><i>' + VL.esc(r[1]) + '</i><br>' + VL.fmt(p.value) + ' documents'; } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: rows.map(function (s) { return ISSUERS[s][2]; }), axisLabel: catAxisLabel(), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '64%', data: rows.map(function (s) { return cnt[s]; }), itemStyle: { color: hue('violet') },
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.compact(p.value); } } }]
    }), true);
  }
  function changesChart() {
    var cats = [], yMin = 9999, yMax = 0, ch = X.changes, sel = 0, left = 0, undated = !yearActive();
    for (var c = 0; c < ch.kind.length; c++) { var y = ch.year[c]; if (y > 0) { yMin = Math.min(yMin, y); yMax = Math.max(yMax, y); } }
    var a0 = Math.max(yMin, F.y0), a1 = Math.min(yMax, F.y1);
    for (var yy = a0; yy <= a1; yy++) cats.push(String(yy));
    var nY = cats.length;
    if (undated) cats.push('no date');
    var cnt = KINDS.map(function () { return cats.map(function () { return 0; }); });
    for (var j = 0; j < ch.kind.length; j++) {
      if (!changeOk(j)) continue;
      var yr = ch.year[j];
      if (yr > 0) { if (yr < F.y0 || yr > F.y1) continue; cnt[ch.kind[j]][yr - a0]++; }
      else if (undated) cnt[ch.kind[j]][nY]++;
      else { left++; continue; }
      sel++;
    }
    M.changesSelected = sel;
    NOTE.changes = left;
    var noDate = undated ? cnt.reduce(function (s, r) { return s + r[nY]; }, 0) : 0;
    VL.$('#sub-changes').textContent = 'Year the change takes effect' +
      (noDate ? '; “no date” holds the ' + plural(noDate, 'event', 'events') + ' without an effective date' : '') +
      (left ? '; the year range leaves out ' + plural(left, 'event', 'events') + ' without an effective date' : '') +
      '. Type and area filters apply to the affected document.';
    chart('c-changes').setOption(base({
      legend: legend(),
      grid: { left: 8, right: 16, top: legendTop('c-changes', KINDS.map(function (k) { return VL.CHANGE[k].en; })), bottom: 8, containLabel: true },
      xAxis: yearAxis('c-changes', cats),
      yAxis: valueAxis(),
      series: KINDS.map(function (k, ki) { return { name: VL.CHANGE[k].en, type: 'bar', stack: 'c', data: cnt[ki], itemStyle: { color: VL.CHANGE[k].color } }; })
    }), true);
    return sel;
  }
  function decisionsYear() {
    /* the few decisions dated before 2000 share one bucket; undated decisions get a 'no year' bucket while the range is untouched */
    var CUT = 2000, rows = DB.decisions_by_category_year, undated = !yearActive(), cats = {}, yrs = {}, early = false, left = 0, shown = 0;
    function rowOk(r) { return r.year > 0 ? (r.year >= F.y0 && r.year <= F.y1) : undated; }
    rows.forEach(function (r) {
      if (!rowOk(r)) { if (r.year <= 0) left += r.n; return; }
      if (r.year > 0) { if (r.year < CUT) early = true; else yrs[r.year] = 1; }
      cats[r.category] = (cats[r.category] || 0) + r.n;
      shown += r.n;
    });
    var years = Object.keys(yrs).map(Number).sort(function (a, b) { return a - b; });
    var labels = (early ? ['before ' + CUT] : []).concat(years.map(String));
    var nY = labels.length;
    if (undated && rows.some(function (r) { return r.year <= 0; })) labels.push('no year');
    function col(y) { return y > 0 ? (y < CUT ? 0 : (early ? 1 : 0) + years.indexOf(y)) : nY; }
    var catOrder = Object.keys(cats).sort(function (a, b) { return cats[b] - cats[a]; });
    var pal = hues(['blue', 'pink', 'orange', 'teal', 'violet', 'yellow', 'green', 'red', 'slate']);
    var series = catOrder.map(function (cat, ci) {
      var data = labels.map(function () { return 0; });
      rows.forEach(function (r) { if (r.category === cat && rowOk(r)) data[col(r.year)] += r.n; });
      return { name: cat === 'unknown' ? 'unknown category' : cat, type: 'bar', stack: 'd', data: data, itemStyle: { color: pal[ci % pal.length] } };
    });
    NOTE.decisions = left;
    var noYear = undated ? rows.filter(function (r) { return r.year <= 0; }).reduce(function (s, r) { return s + r.n; }, 0) : 0;
    VL.$('#sub-dec-year').textContent = VL.fmt(shown) + ' decisions from anle.toaan.gov.vn and congbobanan.toaan.gov.vn' +
      (noYear ? '; “no year” holds the ' + plural(noYear, 'decision', 'decisions') + ' without a year' : '') +
      (left ? '; the year range leaves out ' + plural(left, 'decision', 'decisions') + ' without a year' : '') +
      '. Only the year filter applies.';
    chart('c-dec-year').setOption(base({
      legend: legend(),
      grid: { left: 8, right: 16, top: legendTop('c-dec-year', series.map(function (s) { return s.name; })), bottom: 8, containLabel: true },
      xAxis: yearAxis('c-dec-year', labels),
      yAxis: valueAxis(),
      series: series
    }), true);
  }
  function pieLike(id, rows, labelKey, pal) {
    rows = rows.slice().sort(function (a, b) { return b.n - a.n; });
    setHeight(id, rows.length, catPitch(rows.map(function (r) { return r[labelKey]; }), catW(150, 110), mob() ? 28 : 26), 40);
    chart(id).setOption(base({
      grid: { left: 8, right: mob() ? 54 : 66, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) { return VL.esc(p.name) + ': ' + VL.fmt(p.value); } },
      xAxis: valueAxis({ type: 'log', min: 100 }),
      yAxis: { type: 'category', inverse: true, data: rows.map(function (r) { return r[labelKey]; }), axisLabel: catAxisLabel(mob() ? 110 : 150), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '60%', data: rows.map(function (r, i) { return { value: r.n, itemStyle: { color: hue(pal[i % pal.length]) } }; }),
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.compact(p.value); } } }]
    }), true);
  }
  function qaChart() {
    var slugOf = AREAS.map(function (a) { return a[0]; }), labelOf = {};
    AREAS.forEach(function (a) { labelOf[a[0]] = a[2]; });
    var sel = F.area >= 0 ? slugOf[F.area] : null, rows = DB.qas_by_area_year, undated = !yearActive(), tot = {}, yrs = {}, hasUndated = false, left = 0;
    function rowOk(r) {
      if (r.year > 0 ? (r.year < F.y0 || r.year > F.y1) : !undated) return false;
      return !(sel && r.area_id !== sel);
    }
    rows.forEach(function (r) {
      if (!rowOk(r)) { if (r.year <= 0 && !(sel && r.area_id !== sel)) left += r.n; return; }
      if (r.year > 0) yrs[r.year] = 1; else hasUndated = true;
      var a = r.area_id || '';
      tot[a] = (tot[a] || 0) + r.n;
    });
    var years = Object.keys(yrs).map(Number).sort(function (a, b) { return a - b; });
    var labels = years.map(String).concat(hasUndated ? ['no year'] : []);
    function col(y) { return y > 0 ? years.indexOf(y) : labels.length - 1; }
    var named = Object.keys(tot).filter(function (a) { return a; }).sort(function (a, b) { return tot[b] - tot[a]; });
    var keep = named.slice(0, 8), rest = named.slice(8);
    var pal = hues(['green', 'blue', 'orange', 'pink', 'violet', 'teal', 'yellow', 'red']);
    function seriesFor(name, color, test) {
      var data = labels.map(function () { return 0; });
      rows.forEach(function (r) { if (rowOk(r) && test(r.area_id || '')) data[col(r.year)] += r.n; });
      return { name: name, type: 'bar', stack: 'q', data: data, itemStyle: { color: color } };
    }
    var series = keep.map(function (a, i) { return seriesFor(labelOf[a] || a, pal[i], function (x) { return x === a; }); });
    if (rest.length) series.push(seriesFor('other areas', hue('grey-2'), function (x) { return x && rest.indexOf(x) >= 0; }));
    if (tot['']) series.push(seriesFor('no area', hue('grey'), function (x) { return !x; }));
    NOTE.qa = left;
    VL.$('#sub-qa').textContent = 'Year and area filters apply' +
      (tot[''] ? '; “no area” holds the ' + plural(tot[''], 'Q&A', 'Q&As') + ' without a legal area' : '') +
      (left ? '; the year range leaves out ' + plural(left, 'Q&A', 'Q&As') + ' without a year' : '') + '.';
    chart('c-qa').setOption(base({
      legend: legend(),
      grid: { left: 8, right: 16, top: legendTop('c-qa', series.map(function (s) { return s.name; })), bottom: 8, containLabel: true },
      xAxis: yearAxis('c-qa', labels),
      yAxis: valueAxis(),
      series: series
    }), true);
  }
  function termsChart() {
    /* the 14 largest areas, the other areas grouped and the terms without an area: the bars add up to every term */
    var sel = F.area >= 0 ? AREAS[F.area][0] : null;
    var named = DB.terms_by_area.filter(function (r) { return r.area; }).slice().sort(function (a, b) { return b.n - a.n; });
    var noArea = sumCol(DB.terms_by_area.filter(function (r) { return !r.area; }), 'n');
    var top = named.slice(0, 14), rest = named.slice(14);
    var rows = top.map(function (r) { return { label: r.en || r.vi || r.area, sub: r.vi || '', n: r.n, area: r.area }; });
    if (rest.length) rows.push({ label: 'other areas (' + rest.length + ')', n: sumCol(rest, 'n'), area: null, grey: hue('grey-2'),
      sub: rest.slice(0, 5).map(function (r) { return r.en || r.vi || r.area; }).join(', ') + (rest.length > 5 ? ', …' : '') });
    if (noArea) rows.push({ label: 'no area', sub: '', n: noArea, area: null, grey: hue('grey') });
    VL.$('#sub-terms').textContent = (rest.length ? 'The ' + top.length + ' largest of ' + named.length + ' areas of the terminology dataset, the other ' + rest.length + ' grouped'
      : 'Areas of the terminology dataset') + (noArea ? '; “no area” holds the ' + plural(noArea, 'term', 'terms') + ' without one' : '') +
      '. English labels partly machine-translated.';
    setHeight('c-terms', rows.length, catPitch(rows.map(function (r) { return r.label; }), catW(), mob() ? 26 : 24), 40);
    chart('c-terms').setOption(base({
      grid: { left: 8, right: mob() ? 44 : 56, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) { var r = rows[p.dataIndex]; return VL.esc(r.label) + (r.sub ? '<br><i>' + VL.esc(r.sub) + '</i>' : '') + '<br>' + VL.fmt(r.n) + ' terms'; } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: rows.map(function (r) { return r.label; }), axisLabel: catAxisLabel(), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '64%', data: rows.map(function (r) { return { value: r.n, itemStyle: { color: r.grey || (!sel || sel === r.area ? hue('lime') : VL.alpha(hue('lime'), 0.3)) } }; }),
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.compact(p.value); } } }]
    }), true);
  }
  function linksChart() {
    var rows = [];
    DB.legal_basis_by_method.forEach(function (r) { rows.push({ k: 'legal basis · ' + r.method, n: r.n, c: VL.EDGE.basis.color }); });
    DB.citations_by_kind.forEach(function (r) { rows.push({ k: 'citation · ' + r.kind.replace(/_/g, ' '), n: r.edges, c: hue('slate') }); });
    DB.case_links_by_method.forEach(function (r) { rows.push({ k: 'case link · ' + r.method, n: r.n, c: hue('pink') }); });
    DB.qa_article_links_by_method.forEach(function (r) { rows.push({ k: 'Q&A → article · ' + r.method, n: r.n, c: hue('green') }); });
    rows.push({ k: 'applied provisions (court)', n: S.applied_provision_links, c: hue('pink') });
    rows.push({ k: 'change relations', n: S.change_events, c: hue('orange') });
    rows.sort(function (a, b) { return b.n - a.n; });
    setHeight('c-links', rows.length, catPitch(rows.map(function (r) { return r.k; }), catW(260, 140), mob() ? 26 : 24), 40);
    chart('c-links').setOption(base({
      grid: { left: 8, right: mob() ? 46 : 56, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) { return VL.esc(rows[p.dataIndex].k) + ': ' + VL.fmt(p.value); } },
      xAxis: valueAxis({ type: 'log', min: 10 }),
      yAxis: { type: 'category', inverse: true, data: rows.map(function (r) { return r.k; }), axisLabel: catAxisLabel(catW(260, 140)), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '60%', data: rows.map(function (r) { return { value: r.n, itemStyle: { color: r.c } }; }),
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.compact(p.value); } } }]
    }), true);
  }
  function newsChart() {
    var cnt = {}, lab = (DB.labels || {}).news_categories || {};
    DB.news_by_category_month.forEach(function (r) { cnt[r.category] = (cnt[r.category] || 0) + r.n; });
    var rows = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; });
    setHeight('c-news', rows.length, catPitch(rows.map(function (k) { return (lab[k] || {}).en || k; }), catW(170, 120), mob() ? 26 : 24), 40);
    chart('c-news').setOption(base({
      grid: { left: 8, right: mob() ? 40 : 50, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) { var k = rows[p.dataIndex]; return VL.esc((lab[k] || {}).en || k) + '<br><i>' + VL.esc((lab[k] || {}).vi || '') + '</i><br>' + p.value + ' articles'; } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: rows.map(function (k) { return (lab[k] || {}).en || k; }), axisLabel: catAxisLabel(mob() ? 120 : 170), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '60%', data: rows.map(function (k) { return cnt[k]; }), itemStyle: { color: hue('red') },
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg } }]
    }), true);
  }

  /* ------------------------------------------------------------------ most-cited tables */
  var SRC = [['vbpl_citations', 'Legal documents'], ['qa', 'Q&As'], ['court_decisions', 'Court decisions']];
  var tab = { docs: 'vbpl_citations', arts: 'court_decisions' };
  function tabs(id, which) {
    VL.$('#' + id).innerHTML = SRC.map(function (s) {
      return '<button type="button" role="tab" data-src="' + s[0] + '" aria-selected="' + (tab[which] === s[0]) + '">' + VL.esc(s[1]) + '</button>';
    }).join('');
  }
  ['docs', 'arts'].forEach(function (w) {
    VL.$('#tabs-' + w).addEventListener('click', function (e) {
      var b = e.target.closest('[data-src]');
      if (!b) return;
      tab[w] = b.getAttribute('data-src');
      tabs('tabs-' + w, w);
      tables();
    });
  });
  function docLabel(idx) { return X.doc_labels[String(idx)] || ['', '']; }
  function tables() {
    var docs = X.most_cited.documents[tab.docs].filter(function (r) { return docOk(r[0]); }).slice(0, 12);
    var max = docs.length ? docs[0][1] : 1;
    var unit = { vbpl_citations: 'citing documents', qa: 'citing Q&As', court_decisions: 'decisions' }[tab.docs];
    VL.$('#t-docs').innerHTML = docs.length ? '<table class="data rank-table"><thead><tr><th class="num">#</th><th>Document</th><th class="col-opt">Type</th><th class="num">' + VL.esc(unit) + '</th></tr></thead><tbody>' +
      docs.map(function (r, k) {
        var l = docLabel(r[0]), t = TYPES[X.docs.type[r[0]]] || {}, v = VL.VALIDITY[VALID[X.docs.validity[r[0]]]] || VL.VALIDITY.unknown;
        var num = l[2] ? '<a href="network-3d.html#doc=' + encodeURIComponent(l[2]) + '" title="Open in the 3D legal network">' + VL.esc(l[0] || l[2]) + '</a>' : VL.esc(l[0] || '–');
        return '<tr><td class="num rk">' + (k + 1) + '</td><td><span class="nowrap"><span class="swatch" style="background:' + v.v + ';display:inline-block;margin-right:6px;vertical-align:-1px"></span>' + num + '</span> ' +
          '<span lang="vi">' + VL.esc(VL.short(l[1], 90)) + '</span><div class="sub">' + VL.esc(v.en) + (X.docs.year[r[0]] > 0 ? ' · ' + X.docs.year[r[0]] : '') + '</div></td>' +
          '<td class="col-opt">' + VL.esc(t.en || '') + '</td><td class="num">' + VL.fmt(r[1]) + '<div class="bar" style="width:' + Math.max(4, Math.round(100 * r[1] / max)) + '%"></div></td></tr>';
      }).join('') + '</tbody></table>' : '<p style="padding:12px 14px;margin:0" class="muted">No document matches the filters.</p>';
    tabs('tabs-docs', 'docs');
    var arts = X.most_cited.articles[tab.arts].filter(function (r) { return docOk(r[0]); }).slice(0, 12);
    var amax = arts.length ? arts[0][4] : 1;
    var aunit = { vbpl_citations: 'citing documents', qa: 'citing Q&As', court_decisions: 'decisions' }[tab.arts];
    VL.$('#t-arts').innerHTML = arts.length ? '<table class="data rank-table"><thead><tr><th class="num">#</th><th>Article</th><th class="num">' + VL.esc(aunit) + '</th></tr></thead><tbody>' +
      arts.map(function (r, k) {
        var l = docLabel(r[0]);
        return '<tr><td class="num rk">' + (k + 1) + '</td><td><span class="nowrap">Điều ' + VL.esc(r[2]) + '</span> · <span class="nowrap">' + VL.esc(l[0] || '') + '</span> <span lang="vi">' + VL.esc(VL.short(l[1], 60)) + '</span>' +
          (r[3] ? '<div class="sub" lang="vi">' + VL.esc(VL.short(r[3], 110)) + '</div>' : '') + '</td><td class="num">' + VL.fmt(r[4]) +
          '<div class="bar" style="width:' + Math.max(4, Math.round(100 * r[4] / amax)) + '%"></div></td></tr>';
      }).join('') + '</tbody></table>' : '<p style="padding:12px 14px;margin:0" class="muted">No article matches the filters.</p>';
    tabs('tabs-arts', 'arts');
    M.mostCitedRows = docs.length;
  }

  /* ------------------------------------------------------------------ KPIs */
  function kpi(v, k, vi) { return '<div class="kpi"><div class="v">' + v + '</div><div class="k">' + VL.esc(k) + '</div>' + (vi ? '<div class="vi" lang="vi">' + VL.esc(vi) + '</div>' : '') + '</div>'; }
  function kpis(changeSel) {
    /* the four validity figures partition the selection: in force + not yet in force + no longer in force + unknown */
    var n = 0, inForce = 0, notYet = 0, gone = 0, unk = 0;
    for (var i = 0; i < N; i++) {
      if (!docOk(i)) continue;
      n++;
      var v = VALID[X.docs.validity[i]], meta = VL.VALIDITY[v];
      if (!meta || v === 'unknown') unk++;
      else if (meta.inForce === true) inForce++;
      else if (meta.inForce === false) gone++;
      else notYet++;
    }
    M.docsSelected = n;
    M.kpis = { docs: n, inForce: inForce, notYet: notYet, gone: gone, unknown: unk, changes: changeSel };
    VL.$('#kpis-sel').innerHTML = kpi(VL.fmt(n), 'documents in the selection', 'văn bản') + kpi(VL.fmt(inForce), 'in force (derived)', 'còn hiệu lực') +
      kpi(VL.fmt(notYet), 'not yet in force', 'chưa có hiệu lực') + kpi(VL.fmt(gone), 'no longer in force', 'hết hiệu lực / bị thay thế') +
      kpi(VL.fmt(unk), 'validity unknown', 'chưa xác định') + kpi(VL.fmt(changeSel), 'change relations', 'quan hệ thay đổi');
  }
  function kpisAll() {
    VL.$('#kpis-all').innerHTML = kpi(VL.fmt(S.documents), 'legal documents', 'văn bản') + kpi(VL.fmt(S.articles), 'articles', 'điều') +
      kpi(VL.fmt(S.change_events), 'change events', 'sự kiện thay đổi') + kpi(VL.fmt(S.legal_basis_links), 'legal-basis links', 'căn cứ pháp lý') +
      kpi(VL.fmt(S.citation_links), 'citation links', 'trích dẫn') + kpi(VL.fmt(S.court_decisions), 'court decisions', 'bản án, quyết định') +
      kpi(VL.fmt(S.applied_provision_links), 'applied-provision links', 'điều luật được áp dụng') + kpi(VL.fmt(S.legal_questions), 'legal Q&As', 'hỏi đáp pháp luật') +
      kpi(VL.fmt(S.legal_terms), 'legal terms', 'thuật ngữ') + kpi(VL.fmt(S.news_articles), 'news articles', 'tin tức') +
      kpi(VL.fmt(S.courts), 'courts', 'tòa án') + kpi(VL.fmt(S.rdf_triples), 'RDF triples', 'bộ ba RDF');
  }

  /* ------------------------------------------------------------------ update + events */
  function update() {
    typeYear(); validityByType(); ranks(); areasChart(); issuersChart();
    var sel = changesChart();
    decisionsYear(); qaChart(); termsChart(); tables(); kpis(sel);
    noteFilters();
    M.filters = { type: F.type, area: F.area, y0: F.y0, y1: F.y1, yearActive: yearActive() };
    M.undatedLeftOut = { docs: NOTE.docs || 0, changes: NOTE.changes || 0, decisions: NOTE.decisions || 0, qa: NOTE.qa || 0 };
  }
  function staticCharts() {
    pieLike('c-dec-level', DB.decisions_by_court_level, 'court_level', ['blue', 'teal', 'slate', 'violet', 'pink', 'orange']);
    pieLike('c-dec-inst', DB.decisions_by_instance_level, 'instance_level', ['blue', 'slate', 'orange', 'pink', 'violet']);
    linksChart(); newsChart();
  }
  function bindClicks() {
    chart('c-type-year').on('click', function (p) {
      var ti = -1;
      TYPES.forEach(function (t, i) { if (t.en === p.seriesName) ti = i; });
      if (ti >= 0) setFilter('type', F.type === ti ? -1 : ti);
    });
    chart('c-validity').on('click', function (p) { var ti = chart('c-validity').__rows[p.dataIndex]; if (ti != null) setFilter('type', F.type === ti ? -1 : ti); });
    chart('c-areas').on('click', function (p) { var a = chart('c-areas').__rows[p.dataIndex]; if (a != null) setFilter('area', F.area === a ? -1 : a); });
  }
  var rt = null, wasMob = mob();
  /* theme switch: re-read the chart colours and redraw every chart (series palettes are resolved at render time) */
  window.addEventListener('vlonto-theme', function () {
    readTheme();
    if (!Object.keys(charts).length) return;
    update();
    staticCharts();
    M.chartThemeRenders = (M.chartThemeRenders || 0) + 1;
  });
  window.addEventListener('resize', function () {
    clearTimeout(rt);
    rt = setTimeout(function () {
      Object.keys(charts).forEach(function (k) { charts[k].resize(); });
      /* year-axis label thinning and legend rows depend on the width: rebuild the filtered charts on every resize */
      update();
      if (mob() !== wasMob) { wasMob = mob(); staticCharts(); }
    }, 150);
  });
  window.VLApp.setFilter = function (k, v) { setFilter(k, v); return { docs: M.docsSelected, typeYearSum: M.typeYearSum, changes: M.changesSelected, mostCited: M.mostCitedRows }; };
  window.VLApp.dashState = function () {
    var s = 0;
    var o = charts['c-type-year'].getOption();
    o.series.forEach(function (ser, i) { var on = F.type < 0 || TYPES[F.type].en === ser.name; if (on) ser.data.forEach(function (v) { s += (typeof v === 'object' && v ? v.value : v) || 0; }); });
    return { docs: M.docsSelected, typeYearSum: M.typeYearSum, typeYearChartSum: s, changes: M.changesSelected, filters: M.filters, mostCited: M.mostCitedRows };
  };
  /* sums of every chart as drawn (for the tests): with the filters at their defaults they must equal the KG totals */
  window.VLApp.dashTotals = function () {
    function sumSeries(id) {
      var o = charts[id].getOption(), s = 0;
      o.series.forEach(function (ser) {
        (ser.data || []).forEach(function (v) { var x = (v !== null && typeof v === 'object') ? (v.n != null ? v.n : v.value) : v; s += +x || 0; });
      });
      return s;
    }
    var out = { kpis: M.kpis, undatedLeftOut: M.undatedLeftOut, filters: M.filters, caption: VL.$('#f-active').textContent, charts: {} };
    ['c-type-year', 'c-validity', 'c-ranks', 'c-areas', 'c-changes', 'c-dec-year', 'c-dec-level', 'c-dec-inst', 'c-qa', 'c-terms', 'c-news']
      .forEach(function (id) { out.charts[id] = sumSeries(id); });
    out.kg = { documents: S.documents, change_events: S.change_events, court_decisions: S.court_decisions, legal_questions: S.legal_questions,
      legal_terms: S.legal_terms, news_articles: S.news_articles };
    return out;
  };

  VL.fontsReady().then(function () {
    syncControls();
    kpisAll();
    tabs('tabs-docs', 'docs');
    tabs('tabs-arts', 'arts');
    update();
    staticCharts();
    bindClicks();
    setTimeout(function () {
      if (!readySent) { readySent = true; VL.setReady({ charts: total, chartsFinished: finished }); }
    }, 5000);
  });
})();
