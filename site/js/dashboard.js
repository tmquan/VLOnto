/* VLOnto - dashboard (ECharts 6, canvas renderer). Filters (document type, issue-year range, legal area) are applied in the
   browser to per-document columns (data/dash_extra.js) so every document chart, the change chart and the most-cited tables
   stay linked; Q&A, term and news charts use the aggregates of data/dashboard.js and apply the dimensions they have.
   Release v1 has no court data (court decisions join in v2): no court chart, KPI or citing source is drawn, whether or not
   the data files still carry court fields.
   Language (docs/i18n.md; texts in js/i18n-pages.js, dash.*): headings, captions and notes in one language (English in
   EN–VI); chart content in the mode: legends "Tiếng Việt · English" in EN–VI, category labels with the Vietnamese line above
   the English one, tooltips with the Vietnamese name and the English in italics; numbers through VL.fmt / VL.compact. The
   series keep their English names inside (legend and tooltip formatters show the mode's labels), so clicks, filters and the
   test hooks do not depend on the mode. On 'vl:lang' everything is rebuilt in place; the filters and the tabs stay. */
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
  var esc = VL.esc;
  /* One year range for every dated record: the issue year of a document, the effective year of a change event and the year
     of a Q&A. While the range is untouched every chart shows all records - undated ones in their own
     bucket - so the totals equal the knowledge graph; once the user narrows it, undated records are left out and the
     captions say how many. */
  var DY0 = 9999, DY1 = 0;
  X.docs.year.forEach(function (y) { if (y > 0) { if (y < DY0) DY0 = y; if (y > DY1) DY1 = y; } });
  var Y0 = DY0, Y1 = DY1;
  function widen(y) { if (y > 0) { if (y < Y0) Y0 = y; if (y > Y1) Y1 = y; } }
  X.changes.year.forEach(widen);
  DB.qas_by_area_year.forEach(function (r) { widen(r.year); });
  var F = { type: -1, area: -1, y0: Y0, y1: Y1 };
  var charts = {}, finished = 0, total = 0, readySent = false;
  var NOTE = {};   /* undated records left out by a narrowed year range, filled in by the chart builders */
  var ASOF = (S && S.validity_as_of) || '2026-11-08';

  /* ------------------------------------------------------------------ language helpers */
  function langAttr(l) { return l && l !== VL.i18n.htmlLang() ? ' lang="' + l + '"' : ''; }
  /* {n} for the dictionary: the number itself for 1 (the entry's en_one), else in the mode's format */
  function nv(n) { return n === 1 ? 1 : VL.fmt(n); }
  /* a data label with both languages as one line: one language in EN and VI, "Tiếng Việt · English" in EN–VI */
  function pairText(vi, en) { return VL.T(VL.pair(vi || en || '', en || vi || '')); }
  /* a category label: one language in EN and VI; in EN–VI the Vietnamese above the English (two lines) */
  function lines(l) { return l.secondary ? l.primary + '\n' + l.secondary : l.primary; }
  function cat(vi, en) { return lines(VL.TL(VL.pair(vi || en || '', en || vi || ''))); }
  /* the head of a tooltip: the mode's name; in EN–VI the Vietnamese, then the English in italics */
  function tipHead(l) { return esc(l.primary) + (l.secondary ? '<br><i' + langAttr(l.secondaryLang) + '>' + esc(l.secondary) + '</i>' : ''); }
  function tipPair(vi, en) { return tipHead(VL.TL(VL.pair(vi || en || '', en || vi || ''))); }
  /* a data value inside a running sentence: one language; in EN–VI the English with the Vietnamese in brackets (HTML) */
  function inline(vi, en) {
    var m = VL.lang();
    if (m === 'vi') return esc(vi || en);
    if (m === 'en' || !vi || vi === en) return esc(en || vi);
    return esc(en) + ' (<span lang="vi">' + esc(vi) + '</span>)';
  }
  function listJoin(a) { return a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + VL.U('dash.and') + a[a.length - 1]; }
  function typeName(t) { return pairText(t.vi, t.en); }
  function areaName(a) { return pairText(a[1], a[2]); }

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
  var typeSel = VL.$('#f-type'), y0Sel = VL.$('#f-y0'), y1Sel = VL.$('#f-y1'), areaSel = VL.$('#f-area');
  var yearsOpts = '';
  for (var y = Y0; y <= Y1; y++) yearsOpts += '<option value="' + y + '">' + y + '</option>';   /* years are never grouped */
  y0Sel.innerHTML = yearsOpts;
  y1Sel.innerHTML = yearsOpts;
  var areaCount = {};
  X.docs.area.forEach(function (a) { if (a >= 0) areaCount[a] = (areaCount[a] || 0) + 1; });
  var areaIds = Object.keys(areaCount).map(Number);
  /* the type and area lists in the mode's language (areas sorted by the label shown); the selection stays */
  function fillSelects() {
    typeSel.innerHTML = '<option value="-1">' + esc(VL.U('dash.allTypes')) + '</option>' + TYPES.map(function (t, i) {
      return '<option value="' + i + '" data-code="' + esc(t.code) + '"' + '>' + esc(typeName(t)) + '</option>';
    }).join('');
    var loc = VL.lang() === 'en' ? 'en' : 'vi';
    var order = areaIds.slice().sort(function (a, b) { return areaName(AREAS[a]).localeCompare(areaName(AREAS[b]), loc); });
    areaSel.innerHTML = '<option value="-1">' + esc(VL.U('dash.allAreas')) + '</option>' + order.map(function (a) {
      return '<option value="' + a + '" data-area="' + esc(AREAS[a][0]) + '">' + esc(areaName(AREAS[a])) + '</option>';
    }).join('');
    syncControls();
  }
  function syncControls() {
    typeSel.value = String(F.type); areaSel.value = String(F.area); y0Sel.value = String(F.y0); y1Sel.value = String(F.y1);
  }
  /* the line under the filters: what is selected and, while a year range is set, which undated records it leaves out */
  function noteFilters() {
    var parts = [];
    if (F.type >= 0) parts.push(inline(TYPES[F.type].vi, TYPES[F.type].en));
    if (yearActive()) parts.push(esc(VL.U('dash.yearsRange', { a: F.y0, b: F.y1 })));
    if (F.area >= 0) parts.push(inline(AREAS[F.area][1], AREAS[F.area][2]));
    var t = parts.length ? VL.UH('dash.showing', null, { html: { parts: parts.join(' · ') } }) : VL.UH('dash.noFilter', { n: VL.fmt(N) });
    if (yearActive()) {
      var out = [];
      if (NOTE.docs) out.push(VL.U('dash.docsNoYear', { n: nv(NOTE.docs) }));
      if (NOTE.changes) out.push(VL.U('dash.changesNoDate', { n: nv(NOTE.changes) }));
      if (NOTE.qa) out.push(VL.U('dash.qaNoYear', { n: nv(NOTE.qa) }));
      if (out.length) t += VL.UH('dash.leavesOut', { list: listJoin(out) });
    }
    VL.$('#f-active').innerHTML = t;
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
  function widest(s, size) { return Math.max.apply(null, String(s).split('\n').map(function (p) { return textW(p, size); })); }
  function legendFont() { return mob() ? 10.5 : 12; }
  function legendGap() { return mob() ? 8 : 10; }
  /* plain (multi-row) legends: never paginated; returns the grid top that clears all legend rows (names as shown) */
  function legendTop(id, names) {
    var el = VL.$('#' + id), W = Math.max(120, el.clientWidth), size = legendFont(), gap = legendGap(), rows = 1, x = 0;
    names.forEach(function (n) {
      var w = 12 + 5 + textW(n, size) + gap;
      if (x > 0 && x + w - gap > W) { rows++; x = 0; }
      x += w;
    });
    return rows * (Math.ceil(size * 1.3) + gap) + 8;
  }
  /* legend entries keep the series' inner (English) names; disp maps them to the labels of the mode */
  function legend(disp, extra) {
    var l = { type: 'plain', top: 0, left: 0, right: 0, itemWidth: 12, itemHeight: 10, itemGap: legendGap(), inactiveColor: C.axis,
      textStyle: { fontFamily: FONT, fontSize: legendFont(), color: C.fg } };
    if (disp) l.formatter = function (name) { return disp[name] != null ? disp[name] : name; };
    Object.keys(extra || {}).forEach(function (k) { l[k] = extra[k]; });
    return l;
  }
  function shown(disp, names) { return names.map(function (n) { return disp[n] != null ? disp[n] : n; }); }
  /* the tooltip of a stacked chart over years: the year (or bucket) and every series, in the mode's labels and numbers */
  function axisTip(disp, catDisp) {
    return function (ps) {
      if (!ps || !ps.length) return '';
      var c = ps[0].name, s = esc(catDisp && catDisp[c] != null ? catDisp[c].replace('\n', ' · ') : c);
      ps.forEach(function (p) {
        var v = (p.value !== null && typeof p.value === 'object') ? p.value.value : p.value;
        s += '<br>' + p.marker + esc(disp[p.seriesName] != null ? disp[p.seriesName] : p.seriesName) + ': ' + VL.fmt(v || 0);
      });
      return s;
    };
  }
  function catW(desk, phone) { return mob() ? (phone || 140) : (desk || 250); }
  function catAxisLabel(width) {
    return { fontFamily: FONT, fontSize: mob() ? 10.5 : 11.5, color: C.fg, width: width || catW(), overflow: 'break', lineHeight: mob() ? 13 : 14 };
  }
  /* row pitch for a category axis whose labels wrap at `width` (ECharts overflow: 'break' wraps at spaces); a label with
     a line break (EN–VI: Vietnamese line, English line) counts the wrapped lines of each part */
  function catPitch(labels, width, minPitch) {
    var size = mob() ? 10.5 : 11.5, lh = mob() ? 13 : 14, sp = textW(' ', size), mx = 1;
    width -= 14;   /* ECharts wraps a little earlier than the raw text width suggests */
    labels.forEach(function (t) {
      var lines = 0;
      String(t).split('\n').forEach(function (part) {
        var words = part.split(/\s+/), n = 1, cur = 0;
        words.forEach(function (wd) {
          var ww = textW(wd, size);
          if (cur > 0 && cur + sp + ww > width) { n++; cur = ww; } else cur += (cur > 0 ? sp : 0) + ww;
        });
        lines += n;
      });
      mx = Math.max(mx, lines);
    });
    return Math.max(minPitch, mx * lh + 10);
  }
  /* value-axis ticks in the mode's compact format (VL.compact: 40k / 41 N, 1.2M / 1,2 Tr) */
  function axisK(v) { return VL.compact(v); }
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

  /* category axis over years with bucket labels at either end ('no year', 'no date'): year labels are thinned so that
     they never collide with each other or with a bucket label, and bucket labels are always shown. The categories keep
     their inner names; disp gives the bucket labels of the mode. */
  function yearAxis(id, cats, disp) {
    var el = VL.$('#' + id), n = Math.max(1, cats.length), fs = mob() ? 10.5 : 11.5;
    var cw = Math.max(120, el.clientWidth - (mob() ? 56 : 66)) / n, yw = textW('2000', fs) + 10;
    var step = Math.max(1, Math.ceil(yw / cw)), first = -1, special = [];
    cats.forEach(function (c, i) {
      if (/^\d{4}$/.test(c)) { if (first < 0) first = i; } else special.push([i, widest(disp && disp[c] != null ? disp[c] : c, fs)]);
    });
    function show(i) {
      if (!/^\d{4}$/.test(cats[i])) return true;
      if ((i - first) % step) return false;
      for (var k = 0; k < special.length; k++) if (Math.abs(i - special[k][0]) * cw < (special[k][1] + yw) / 2 + 4) return false;
      return true;
    }
    return { type: 'category', data: cats, axisTick: { alignWithLabel: true, interval: show },
      axisLabel: { fontFamily: FONT, fontSize: fs, color: C.muted, hideOverlap: true, interval: show,
        formatter: function (v) { return disp && disp[v] != null ? disp[v] : v; } } };
  }
  function sumCol(rows, col) { return rows.reduce(function (s, r) { return s + (r[col] || 0); }, 0); }
  function docsLine(n) { return esc(VL.U('dash.tip.documents', { n: nv(n) })); }
  /* a caption written by a chart builder: shown from its first text on (css/site.css hides data-vl-text="wait" until then) */
  function caption(id, text) { var el = VL.$('#' + id); el.textContent = text; el.setAttribute('data-vl-text', 'ok'); }

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
    var sum = 0, disp = { 'type not recorded': VL.T('dash.typeNotRecorded') };
    var series = TYPES.map(function (t, ti) {
      var on = F.type < 0 || F.type === ti;
      cnt[ti].forEach(function (v) { if (on) sum += v; });
      disp[t.en] = typeName(t);
      return { name: t.en, type: 'bar', stack: 'docs', barCategoryGap: '18%', data: cnt[ti], itemStyle: { color: fade(VL.TYPE_COLORS[t.code], on) }, emphasis: { focus: 'series' } };
    }).filter(function (s) { return s.data.some(function (v) { return v > 0; }); });
    if (other) {
      series.push({ name: 'type not recorded', type: 'bar', stack: 'docs', data: other, itemStyle: { color: fade(hue('slate'), F.type < 0) } });
      if (F.type < 0) other.forEach(function (v) { sum += v; });
    }
    M.typeYearSum = sum;
    NOTE.docs = left;
    var noYear = undated ? cnt.reduce(function (s, r) { return s + r[nY]; }, 0) + (other ? other[nY] : 0) : 0;
    caption('sub-type-year', VL.U('dash.typeYear.sub', { a: noYear ? VL.U('dash.noYearHolds', { n: nv(noYear) }) : '',
      b: left ? VL.U('dash.leavesOutDocs', { n: nv(left) }) : '' }));
    var catDisp = { 'no year': lines(VL.TL('dash.noYear')) };
    var c = chart('c-type-year');
    c.setOption(base({
      legend: legend(disp),
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true, formatter: axisTip(disp, catDisp) },
      grid: { left: 8, right: 16, top: legendTop('c-type-year', shown(disp, series.map(function (s) { return s.name; }))), bottom: 8, containLabel: true },
      xAxis: yearAxis('c-type-year', cats, catDisp),
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
    var disp = {};
    var series = order.map(function (vi) {
      var name = VALID[vi], meta = VL.VALIDITY[name] || VL.VALIDITY.unknown;
      disp[meta.en] = VL.T(meta);
      return { name: meta.en, type: 'bar', stack: 'v', barWidth: '62%',
        data: rows.map(function (ti) { return { value: tot[ti] ? Math.round(1000 * cnt[ti][vi] / tot[ti]) / 10 : 0, n: cnt[ti][vi], itemStyle: { color: fade(meta.color, F.type < 0 || F.type === ti) } }; }),
        itemStyle: { color: meta.color } };
    });
    var lt = legendTop('c-validity', shown(disp, series.map(function (s) { return s.name; })));
    var tl = rows.map(function (ti) { return cat(TYPES[ti].vi, TYPES[ti].en); }), tw = catW(120, 92);
    setHeight('c-validity', rows.length, catPitch(tl, tw, mob() ? 30 : 28), lt + 40);
    var c = chart('c-validity');
    c.setOption(base({
      legend: legend(disp),
      grid: { left: 8, right: mob() ? 14 : 22, top: lt, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true, textStyle: { fontFamily: FONT, fontSize: 12 },
        formatter: function (ps) {
          var ti = rows[ps[0].dataIndex], l = VL.TL(VL.pair(TYPES[ti].vi, TYPES[ti].en));
          var s = esc(l.primary) + ' (' + VL.fmt(tot[ti]) + ')' + (l.secondary ? '<br><i' + langAttr(l.secondaryLang) + '>' + esc(l.secondary) + '</i>' : '');
          ps.forEach(function (p) { if (p.data.n) s += '<br>' + p.marker + esc(disp[p.seriesName] != null ? disp[p.seriesName] : p.seriesName) + ': ' + VL.fmt(p.data.n) + ' (' + VL.fmt(p.value) + '%)'; });
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
    var full = X.ranks || [];
    /* "0 · Constitution" (EN), "0 · Hiến pháp" (VI); EN–VI: the Vietnamese line above the English one */
    var labels = cnt.map(function (v, r) { var l = VL.TL('dash.rank.' + r); return r + ' · ' + l.primary + (l.secondary ? '\n' + l.secondary : ''); });
    var rw = catW(210, 150);
    setHeight('c-ranks', 6, catPitch(labels, rw, mob() ? 30 : 28), 50);
    chart('c-ranks').setOption(base({
      grid: { left: 8, right: mob() ? 44 : 56, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 },
        formatter: function (p) {
          var f = full[p.dataIndex], name = f && f.en ? VL.pair(f.vi || f.en, f.en) : VL.i18n.get('dash.rank.' + p.dataIndex);
          return tipHead(VL.TL('dash.tip.rank', { r: p.dataIndex, name: name })) + '<br>' + docsLine(p.value);
        } },
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
    function lab(a) { return a < 0 ? lines(VL.TL('dash.noAreaRecorded')) : cat(AREAS[a][1], AREAS[a][2]); }
    var labels = rows.map(lab);
    setHeight('c-areas', rows.length, catPitch(labels, catW(), mob() ? 26 : 24), 40);
    var c = chart('c-areas');
    c.setOption(base({
      grid: { left: 8, right: mob() ? 48 : 60, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) {
        var k = rows[p.dataIndex];
        if (k < 0) return VL.UH('dash.tip.noArea') + '<br>' + docsLine(p.value);
        return tipPair(AREAS[k][1], AREAS[k][2]) + '<br>' + docsLine(p.value); } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: labels, axisLabel: catAxisLabel(), axisTick: { show: false } },
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
    caption('sub-issuers', VL.U('dash.issuers.sub', {
      which: nIss > rows.length ? VL.U('dash.issuers.top', { k: VL.fmt(rows.length), n: VL.fmt(nIss) }) : VL.U('dash.issuers.all', { n: VL.fmt(nIss) }),
      none: noIss ? VL.U('dash.noIssuer', { n: nv(noIss) }) : '' }));
    var labels = rows.map(function (s) { return cat(ISSUERS[s][1], ISSUERS[s][2]); });
    setHeight('c-issuers', Math.max(rows.length, 3), catPitch(labels, catW(), mob() ? 26 : 24), 40);
    chart('c-issuers').setOption(base({
      grid: { left: 8, right: mob() ? 48 : 60, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) {
        var r = ISSUERS[rows[p.dataIndex]]; return tipPair(r[1], r[2]) + '<br>' + docsLine(p.value); } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: labels, axisLabel: catAxisLabel(), axisTick: { show: false } },
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
    caption('sub-changes', VL.U('dash.changes.sub', { a: noDate ? VL.U('dash.noDateHolds', { n: nv(noDate) }) : '',
      b: left ? VL.U('dash.leavesOutEvents', { n: nv(left) }) : '' }));
    var disp = {};
    KINDS.forEach(function (k) { disp[VL.CHANGE[k].en] = VL.T(VL.CHANGE[k]); });
    var catDisp = { 'no date': lines(VL.TL('dash.noDate')) };
    chart('c-changes').setOption(base({
      legend: legend(disp),
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true, formatter: axisTip(disp, catDisp) },
      grid: { left: 8, right: 16, top: legendTop('c-changes', shown(disp, KINDS.map(function (k) { return VL.CHANGE[k].en; }))), bottom: 8, containLabel: true },
      xAxis: yearAxis('c-changes', cats, catDisp),
      yAxis: valueAxis(),
      series: KINDS.map(function (k, ki) { return { name: VL.CHANGE[k].en, type: 'bar', stack: 'c', data: cnt[ki], itemStyle: { color: VL.CHANGE[k].color } }; })
    }), true);
    return sel;
  }
  function qaChart() {
    var slugOf = AREAS.map(function (a) { return a[0]; }), bySlug = {};
    AREAS.forEach(function (a) { bySlug[a[0]] = a; });
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
    /* series are named by the area's slug inside; the legend and the tooltip show the area in the mode's language */
    var disp = { __other: VL.T('dash.otherAreas'), __none: VL.T('dash.noArea') };
    var series = keep.map(function (a, i) {
      disp[a] = bySlug[a] ? areaName(bySlug[a]) : a;
      return seriesFor(a, pal[i], function (x) { return x === a; });
    });
    if (rest.length) series.push(seriesFor('__other', hue('grey-2'), function (x) { return x && rest.indexOf(x) >= 0; }));
    if (tot['']) series.push(seriesFor('__none', hue('grey'), function (x) { return !x; }));
    NOTE.qa = left;
    caption('sub-qa', VL.U('dash.qa.sub', { a: tot[''] ? VL.U('dash.noAreaHolds', { n: nv(tot['']) }) : '',
      b: left ? VL.U('dash.leavesOutQa', { n: nv(left) }) : '' }));
    var catDisp = { 'no year': lines(VL.TL('dash.noYear')) };
    chart('c-qa').setOption(base({
      legend: legend(disp),
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true, formatter: axisTip(disp, catDisp) },
      grid: { left: 8, right: 16, top: legendTop('c-qa', shown(disp, series.map(function (s) { return s.name; }))), bottom: 8, containLabel: true },
      xAxis: yearAxis('c-qa', labels, catDisp),
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
    var rows = top.map(function (r) { return { tl: VL.TL(VL.pair(r.vi || r.en || r.area, r.en || r.vi || r.area)), n: r.n, area: r.area }; });
    if (rest.length) rows.push({ tl: VL.TL('dash.otherAreasN', { n: VL.fmt(rest.length) }), n: sumCol(rest, 'n'), area: null, grey: hue('grey-2'),
      list: rest.slice(0, 5).map(function (r) { return pairText(r.vi || r.en || r.area, r.en || r.vi || r.area); }).join(', ') + (rest.length > 5 ? ', …' : '') });
    if (noArea) rows.push({ tl: VL.TL('dash.noArea'), n: noArea, area: null, grey: hue('grey') });
    caption('sub-terms', (rest.length ? VL.U('dash.terms.subTop', { k: VL.fmt(top.length), n: VL.fmt(named.length), m: VL.fmt(rest.length) })
      : VL.U('dash.terms.subAll')) + (noArea ? VL.U('dash.noAreaTerms', { n: nv(noArea) }) : '') + VL.U('dash.terms.subEnd'));
    var labels = rows.map(function (r) { return lines(r.tl); });
    setHeight('c-terms', rows.length, catPitch(labels, catW(), mob() ? 26 : 24), 40);
    chart('c-terms').setOption(base({
      grid: { left: 8, right: mob() ? 44 : 56, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) {
        var r = rows[p.dataIndex];
        return tipHead(r.tl) + (r.list ? '<br><i>' + esc(r.list) + '</i>' : '') + '<br>' + esc(VL.U('dash.tip.terms', { n: nv(r.n) })); } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: labels, axisLabel: catAxisLabel(), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '64%', data: rows.map(function (r) { return { value: r.n, itemStyle: { color: r.grey || (!sel || sel === r.area ? hue('lime') : VL.alpha(hue('lime'), 0.3)) } }; }),
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.compact(p.value); } } }]
    }), true);
  }
  /* the links chart: the kind of link and its extraction method (the ontology's labels of the method concepts), each in
     the mode's language; an identifier the dictionary does not know stays as it is */
  function rawLine(s) { var envi = VL.lang() === 'envi'; return { primary: s, secondary: envi ? s : '', primaryLang: 'en', secondaryLang: envi ? 'en' : null }; }
  function linkLine(k, m) {
    return { primary: k.primary + ' · ' + m.primary, secondary: k.secondary ? k.secondary + ' · ' + (m.secondary || m.primary) : '',
      primaryLang: k.primaryLang, secondaryLang: k.secondaryLang };
  }
  function linksChart() {
    var rows = [];
    DB.legal_basis_by_method.forEach(function (r) {
      var m = VL.i18n.has('dash.method.' + r.method) ? VL.TL('dash.method.' + r.method) : rawLine(r.method);
      rows.push({ tl: linkLine(VL.TL('dash.link.basis'), m), n: r.n, c: VL.EDGE.basis.color });
    });
    DB.citations_by_kind.forEach(function (r) {
      var m = VL.i18n.has('dash.citeKind.' + r.kind) ? VL.TL('dash.citeKind.' + r.kind) : rawLine(r.kind.replace(/_/g, ' '));
      rows.push({ tl: linkLine(VL.TL('dash.link.citation'), m), n: r.edges, c: hue('slate') });
    });
    DB.qa_article_links_by_method.forEach(function (r) {
      var m = VL.i18n.has('dash.method.' + r.method) ? VL.TL('dash.method.' + r.method) : rawLine(r.method);
      rows.push({ tl: linkLine(VL.TL('dash.link.qa'), m), n: r.n, c: hue('green') });
    });
    rows.push({ tl: VL.TL('dash.link.changes'), n: S.change_events, c: hue('orange') });
    rows.sort(function (a, b) { return b.n - a.n; });
    var labels = rows.map(function (r) { return lines(r.tl); });
    setHeight('c-links', rows.length, catPitch(labels, catW(260, 140), mob() ? 26 : 24), 40);
    chart('c-links').setOption(base({
      grid: { left: 8, right: mob() ? 46 : 56, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) {
        var t = rows[p.dataIndex].tl;
        return t.secondary ? tipHead(t) + '<br>' + VL.fmt(p.value) : esc(t.primary) + ': ' + VL.fmt(p.value); } },
      xAxis: valueAxis({ type: 'log', min: 10 }),
      yAxis: { type: 'category', inverse: true, data: labels, axisLabel: catAxisLabel(catW(260, 140)), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '60%', data: rows.map(function (r) { return { value: r.n, itemStyle: { color: r.c } }; }),
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.compact(p.value); } } }]
    }), true);
  }
  function newsChart() {
    var cnt = {}, lab = (DB.labels || {}).news_categories || {};
    DB.news_by_category_month.forEach(function (r) { cnt[r.category] = (cnt[r.category] || 0) + r.n; });
    var rows = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; });
    var tls = rows.map(function (k) { var l = lab[k] || {}; return VL.TL(VL.pair(l.vi || l.en || k, l.en || l.vi || k)); });
    var labels = tls.map(lines);
    setHeight('c-news', rows.length, catPitch(labels, catW(170, 120), mob() ? 26 : 24), 40);
    chart('c-news').setOption(base({
      grid: { left: 8, right: mob() ? 40 : 50, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', confine: true, textStyle: { fontFamily: FONT, fontSize: 12 }, formatter: function (p) {
        return tipHead(tls[p.dataIndex]) + '<br>' + esc(VL.U('dash.tip.articles', { n: nv(p.value) })); } },
      xAxis: valueAxis(),
      yAxis: { type: 'category', inverse: true, data: labels, axisLabel: catAxisLabel(mob() ? 120 : 170), axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: '60%', data: rows.map(function (k) { return cnt[k]; }), itemStyle: { color: hue('red') },
        label: { show: true, position: 'right', fontFamily: FONT, fontSize: 10.5, color: C.fg, formatter: function (p) { return VL.fmt(p.value); } } }]
    }), true);
  }

  /* ------------------------------------------------------------------ most-cited tables */
  /* citing sources of release v1 (court decisions join in v2) */
  var SRC = [['vbpl_citations', 'dash.src.documents'], ['qa', 'dash.src.qa']];
  var UNIT = { vbpl_citations: 'dash.unit.documents', qa: 'dash.unit.qa' };
  var tab = { docs: 'vbpl_citations', arts: 'qa' };
  function tabs(id, which) {
    VL.$('#' + id).innerHTML = SRC.map(function (s) {
      var tip = VL.tip(s[1]);
      return '<button type="button" role="tab" data-src="' + s[0] + '" aria-selected="' + (tab[which] === s[0]) + '"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' +
        VL.UH(s[1]) + '</button>';
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
    var docs = (X.most_cited.documents[tab.docs] || []).filter(function (r) { return docOk(r[0]); }).slice(0, 12);
    var max = docs.length ? docs[0][1] : 1, open = VL.U('dash.openNetwork');
    VL.$('#t-docs').innerHTML = docs.length ? '<table class="data rank-table"><thead><tr><th class="num">#</th><th>' + VL.UH('dash.th.document') + '</th><th class="col-opt">' +
      VL.UH('dash.th.type') + '</th><th class="num">' + VL.UH(UNIT[tab.docs]) + '</th></tr></thead><tbody>' +
      docs.map(function (r, k) {
        var l = docLabel(r[0]), t = TYPES[X.docs.type[r[0]]] || {}, v = VL.VALIDITY[VALID[X.docs.validity[r[0]]]] || VL.VALIDITY.unknown;
        /* document numbers are Vietnamese notation (NĐ-CP, QĐ-TTg): lang="vi" outside VI */
        var num = l[2] ? '<a href="network-3d.html#doc=' + encodeURIComponent(l[2]) + '" title="' + esc(open) + '"><span' + langAttr('vi') + '>' + esc(l[0] || l[2]) + '</span></a>'
          : '<span' + langAttr('vi') + '>' + esc(l[0] || '–') + '</span>';
        /* document titles are Vietnamese data (no English): shown as they are in every mode, marked lang="vi" */
        return '<tr><td class="num rk">' + (k + 1) + '</td><td><span class="nowrap"><span class="swatch" style="background:' + v.v + ';display:inline-block;margin-right:6px;vertical-align:-1px"></span>' + num + '</span> ' +
          '<span' + langAttr('vi') + '>' + esc(VL.short(l[1], 90)) + '</span><div class="sub">' + VL.TH(v) + (X.docs.year[r[0]] > 0 ? ' · ' + X.docs.year[r[0]] : '') + '</div></td>' +
          '<td class="col-opt">' + (t.en ? VL.TH(VL.pair(t.vi, t.en)) : '') + '</td><td class="num">' + VL.fmt(r[1]) + '<div class="bar" style="width:' + Math.max(4, Math.round(100 * r[1] / max)) + '%"></div></td></tr>';
      }).join('') + '</tbody></table>' : '<p style="padding:12px 14px;margin:0" class="muted">' + VL.UH('dash.noDocument') + '</p>';
    tabs('tabs-docs', 'docs');
    var arts = (X.most_cited.articles[tab.arts] || []).filter(function (r) { return docOk(r[0]); }).slice(0, 12);
    var amax = arts.length ? arts[0][4] : 1;
    VL.$('#t-arts').innerHTML = arts.length ? '<table class="data rank-table"><thead><tr><th class="num">#</th><th>' + VL.UH('dash.th.article') + '</th><th class="num">' +
      VL.UH(UNIT[tab.arts]) + '</th></tr></thead><tbody>' +
      arts.map(function (r, k) {
        var l = docLabel(r[0]);
        return '<tr><td class="num rk">' + (k + 1) + '</td><td><span class="nowrap">' + VL.UH('dash.articleN', { n: r[2] }) + '</span> · <span class="nowrap"' + langAttr('vi') + '>' + esc(l[0] || '') + '</span> ' +
          '<span' + langAttr('vi') + '>' + esc(VL.short(l[1], 60)) + '</span>' +
          (r[3] ? '<div class="sub"' + langAttr('vi') + '>' + esc(VL.short(r[3], 110)) + '</div>' : '') + '</td><td class="num">' + VL.fmt(r[4]) +
          '<div class="bar" style="width:' + Math.max(4, Math.round(100 * r[4] / amax)) + '%"></div></td></tr>';
      }).join('') + '</tbody></table>' : '<p style="padding:12px 14px;margin:0" class="muted">' + VL.UH('dash.noArticle') + '</p>';
    tabs('tabs-arts', 'arts');
    M.mostCitedRows = docs.length;
  }

  /* ------------------------------------------------------------------ KPIs */
  /* a key-figure card: the label in the mode's language; in EN–VI the Vietnamese label with the English gloss below */
  function kpi(v, key) {
    var l = VL.TL(key);
    return '<div class="kpi"><div class="v">' + v + '</div><div class="k"' + langAttr(l.primaryLang) + '>' + esc(l.primary) + '</div>' +
      (l.secondary ? '<div class="k-gloss"' + langAttr(l.secondaryLang) + '>' + esc(l.secondary) + '</div>' : '') + '</div>';
  }
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
    VL.$('#kpis-sel').innerHTML = kpi(VL.fmt(n), 'dash.kpi.docsSel') + kpi(VL.fmt(inForce), 'dash.kpi.inForce') +
      kpi(VL.fmt(notYet), 'dash.kpi.notYet') + kpi(VL.fmt(gone), 'dash.kpi.gone') +
      kpi(VL.fmt(unk), 'dash.kpi.unknown') + kpi(VL.fmt(changeSel), 'dash.kpi.changes');
  }
  function kpisAll() {
    VL.$('#kpis-all').innerHTML = kpi(VL.fmt(S.documents), 'dash.kpi.documents') + kpi(VL.fmt(S.articles), 'dash.kpi.articles') +
      kpi(VL.fmt(S.change_events), 'dash.kpi.changeEvents') + kpi(VL.fmt(S.legal_basis_links), 'dash.kpi.basis') +
      kpi(VL.fmt(S.citation_links), 'dash.kpi.citations') + kpi(VL.fmt(S.legal_questions), 'dash.kpi.qa') +
      kpi(VL.fmt(S.legal_terms), 'dash.kpi.terms') + kpi(VL.fmt(S.news_articles), 'dash.kpi.news') +
      kpi(VL.fmt(S.rdf_triples), 'dash.kpi.triples');
  }
  /* the page's sentences with a release name, a date or numbers from the data */
  function staticTexts() {
    VL.$('#dash-lead').innerHTML = VL.UH('dash.lead', null, { html: { release: '<span data-vl-release>' + esc(VL.releaseLabel()) + '</span>' } });
    VL.$('#sub-validity').innerHTML = VL.UH('dash.validity.sub', null, { html: { date: '<span id="asof">' + esc(ASOF) + '</span>' } });
    var news = DB.news_by_category_month || [];
    var known = sumCol(news.filter(function (r) { return r.month && r.month !== 'unknown'; }), 'n');
    VL.$('#sub-news').textContent = VL.U('dash.news.sub', { n: VL.fmt(sumCol(news, 'n')), k: VL.fmt(known) });
    ['dash-lead', 'sub-validity', 'sub-news'].forEach(function (id) { VL.$('#' + id).setAttribute('data-vl-text', 'ok'); });
  }

  /* ------------------------------------------------------------------ update + events */
  function update() {
    typeYear(); validityByType(); ranks(); areasChart(); issuersChart();
    var sel = changesChart();
    qaChart(); termsChart(); tables(); kpis(sel);
    noteFilters();
    M.filters = { type: F.type, area: F.area, y0: F.y0, y1: F.y1, yearActive: yearActive() };
    M.undatedLeftOut = { docs: NOTE.docs || 0, changes: NOTE.changes || 0, qa: NOTE.qa || 0 };
  }
  function staticCharts() {
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
  /* language switch (js/i18n.js): the lists, sentences, cards, tables and charts again in the new mode; the filters, the
     tabs and the scroll position stay */
  document.addEventListener('vl:lang', function () {
    fillSelects();
    staticTexts();
    kpisAll();
    tabs('tabs-docs', 'docs');
    tabs('tabs-arts', 'arts');
    if (Object.keys(charts).length) { update(); staticCharts(); }
    M.dashLang = VL.lang();
    M.dashLangRenders = (M.dashLangRenders || 0) + 1;
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
    ['c-type-year', 'c-validity', 'c-ranks', 'c-areas', 'c-changes', 'c-qa', 'c-terms', 'c-news']
      .forEach(function (id) { out.charts[id] = sumSeries(id); });
    out.kg = { documents: S.documents, change_events: S.change_events, legal_questions: S.legal_questions,
      legal_terms: S.legal_terms, news_articles: S.news_articles };
    return out;
  };
  /* the text the charts draw on their canvases (legend entries and axis labels as shown, in the current mode), for the
     language tests: canvas text is not in the DOM */
  window.VLApp.dashChartText = function () {
    var out = {};
    Object.keys(charts).forEach(function (id) {
      var o = charts[id].getOption(), lg = (o.legend || [])[0], t = { legend: [], axis: [] };
      if (lg) (o.series || []).forEach(function (s) { t.legend.push(lg.formatter ? lg.formatter(s.name) : s.name); });
      (o.xAxis || []).concat(o.yAxis || []).forEach(function (a) {
        if (a.type !== 'category') return;
        var f = a.axisLabel && typeof a.axisLabel.formatter === 'function' ? a.axisLabel.formatter : null;
        (a.data || []).forEach(function (d) { var v = typeof d === 'object' && d ? d.value : d; t.axis.push(f ? f(v) : v); });
      });
      out[id] = t;
    });
    return out;
  };

  fillSelects();
  staticTexts();
  VL.fontsReady().then(function () {
    syncControls();
    kpisAll();
    tabs('tabs-docs', 'docs');
    tabs('tabs-arts', 'arts');
    update();
    staticCharts();
    bindClicks();
    M.dashLang = VL.lang();
    setTimeout(function () {
      if (!readySent) { readySent = true; VL.setReady({ charts: total, chartsFinished: finished }); }
    }, 5000);
  });
})();
