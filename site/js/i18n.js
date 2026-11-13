/* VLOnto - language layer: EN · VI · EN–VI (classic script; works from file:// and http://). docs/i18n.md has the API.
   Loaded synchronously in the <head> of every page, right after the theme line, so html[lang] and html[data-lang] are
   set before first paint. The dictionaries js/i18n-3d.js and js/i18n-pages.js are the first scripts at the end of
   <body>; this file holds the core dictionary (header, navigation, menu, footer, footbar, skip links, theme toggle,
   the paper block and the other shared panels of js/common.js).
   Modes: 'en' English only; 'vi' Vietnamese only; 'envi' (the default, the v1 look): navigation, buttons and running
   text in English with the Vietnamese as a tooltip on navigation and buttons, content as pairs "Tiếng Việt · English".
   The mode comes from ?lang=en|vi|envi, else the stored choice (localStorage 'vlonto.lang'), else 'envi', and is kept
   like the theme (js/common.js): stored where storage works, carried as ?lang= on internal links under file:// (Firefox
   and Safari keep file storage per file) or where storage is blocked, and sent to embedded documents (postMessage).
   html[lang] is 'en' in the modes 'en' and 'envi' (the page language of the chrome and the running text; every
   Vietnamese fragment carries lang="vi") and 'vi' in 'vi'. A document that stays in one language whatever the mode
   (the pyLODE reference) loads this file with data-doc-lang="en": its html[lang] stays 'en'. */
(function () {
  'use strict';
  var VL = window.VL = window.VL || {};
  var M = window.__VLONTO_METRICS = window.__VLONTO_METRICS || {};
  var ROOT = document.documentElement, KEY = 'vlonto.lang', DEFAULT = 'envi';
  var MODES = ['en', 'vi', 'envi'];
  var HTML_LANG = { en: 'en', vi: 'vi', envi: 'en' };
  var CODE = { en: 'EN', vi: 'VI', envi: 'EN\u2013VI' };
  var me = document.currentScript;
  var DOC_LANG = (me && me.getAttribute('data-doc-lang')) || null;
  function valid(m) { return m === 'en' || m === 'vi' || m === 'envi'; }
  function nfc(s) { return s == null ? '' : String(s).normalize('NFC'); }
  function esc(s) {
    return nfc(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }

  /* ------------------------------------------------------------------ state, before first paint */
  var langFromUrl = (/[?&]lang=(en|vi|envi)(?:&|$)/.exec(location.search) || [])[1] || null;
  var storageOK = (function () { try { var k = 'vlonto.__probe'; localStorage.setItem(k, '1'); localStorage.removeItem(k); return true; } catch (e) { return false; } })();
  function storedLang() { try { var v = localStorage.getItem(KEY); return valid(v) ? v : null; } catch (e) { return null; } }
  var stored0 = storedLang();
  var chosen = !!(langFromUrl || stored0);
  var mode = langFromUrl || stored0 || DEFAULT;
  function htmlLang(m) { return DOC_LANG || HTML_LANG[m]; }
  function setAttrs(m) {
    ROOT.setAttribute('data-lang', m);
    ROOT.setAttribute('lang', htmlLang(m));
  }
  setAttrs(mode);
  /* while the page loads, declarative elements stay hidden until their text is in (css/site.css, "language layer") */
  ROOT.classList.add('vl-i18n-boot');
  M.lang = mode;
  M.langSource = langFromUrl ? 'url' : (stored0 ? 'storage' : 'default');
  M.langChanges = 0;
  M.langStorageOK = storageOK;

  VL.LANGS = MODES.slice();
  VL.lang = function () { return mode; };

  /* ------------------------------------------------------------------ dictionary
     VL.i18n.add(owner, { key: { en, vi, k, en_one, note } }) - k (kind): 'ui' (navigation, buttons, tabs, labels:
     one language, Vietnamese tooltip in envi), 'text' (headings, sentences, status lines: one language, English in
     envi; the default) or 'pair' (legends, call-outs, panel values, titles, glosses: "vi · en" in envi). Values are
     plain text (NFC); {name} placeholders take values (VL.T(key, { n: 3 })); en_one is the English for { n: 1 }. */
  var DICT = {}, OWNER = {}, missing = {}, dups = [];
  function add(owner, entries) {
    Object.keys(entries || {}).forEach(function (k) {
      var e = entries[k];
      if (Array.isArray(e)) e = { en: e[0], vi: e[1], k: e[2] };
      var x = { en: nfc(e.en), vi: nfc(e.vi), k: e.k || 'text' };
      if (e.en_one) x.en_one = nfc(e.en_one);
      if (DICT[k] && OWNER[k] !== owner) dups.push(k);
      DICT[k] = x;
      OWNER[k] = owner;
      delete missing[k];   /* asked for before its dictionary loaded (i18n-3d.js applies before i18n-pages.js): not missing */
    });
    M.i18nMissing = Object.keys(missing);
    M.i18nKeys = Object.keys(DICT).length;
    M.i18nOwners = M.i18nOwners || {};
    M.i18nOwners[owner] = Object.keys(entries || {}).length;
    if (dups.length) M.i18nDuplicates = dups.slice();
    if (document.body) apply(document);
  }
  function entry(x) {
    if (x == null) return null;
    if (typeof x === 'string') {
      var e = DICT[x];
      if (!e) { missing[x] = true; M.i18nMissing = Object.keys(missing); }
      return e || null;
    }
    return x;   /* a {vi, en} object: VL.MODULES, VL.VALIDITY, a record of the data */
  }
  /* {name} placeholders: a value is text, or a {vi, en} object (another entry, VL.pair(...), a VL.MODULES record) whose
     text of the same language goes in; unknown names stay as they are (VL.UH / VL.TH fill them with opts.html) */
  function fill(s, vars, lang) {
    if (!vars || s.indexOf('{') < 0) return s;
    return s.replace(/\{(\w+)\}/g, function (m0, k) {
      var v = vars[k];
      if (v != null && typeof v === 'object') v = v[lang] != null && v[lang] !== '' ? v[lang] : (v.en != null && v.en !== '' ? v.en : v.vi);
      return v != null ? nfc(v) : m0;
    });
  }
  /* the two texts of an entry, placeholders filled; a missing key gives its name, so a gap shows up in the page */
  function texts(x, vars) {
    var e = entry(x);
    if (!e) return { en: typeof x === 'string' ? x : '', vi: '' };
    var en = (vars && vars.n === 1 && e.en_one) ? e.en_one : (e.en || '');
    return { en: fill(nfc(en), vars, 'en'), vi: fill(nfc(e.vi || ''), vars, 'vi') };
  }
  /* raw HTML for the {name} placeholders that remain after escaping (links, <code>, <kbd> inside a sentence) */
  function rich(h, opts) {
    if (!opts || !opts.html) return h;
    return h.replace(/\{(\w+)\}/g, function (m0, k) { return opts.html[k] != null ? opts.html[k] : m0; });
  }
  /* one language: the mode's ('en' and 'envi' -> English), else the other one; l = the language shown */
  function one(t, m) {
    if ((m || mode) === 'vi') return t.vi ? { t: t.vi, l: 'vi' } : { t: t.en, l: 'en' };
    return t.en ? { t: t.en, l: 'en' } : { t: t.vi, l: 'vi' };
  }
  function both(t) { return mode === 'envi' && t.vi && t.en && t.vi !== t.en; }

  /* plain text of content: "vi · en" in envi, else one language (the other one where the mode's is missing) */
  VL.T = function (x, vars) {
    var t = texts(x, vars);
    return both(t) ? t.vi + ' \u00b7 ' + t.en : one(t).t;
  };
  /* plain text of navigation, buttons, labels and sentences: one language; envi -> English */
  VL.U = function (x, vars) { return one(texts(x, vars)).t; };
  /* the Vietnamese tooltip of a control in envi ('' in the other modes, or when there is no different Vietnamese) */
  VL.tip = function (x, vars) {
    if (mode !== 'envi') return '';
    var t = texts(x, vars);
    return t.vi && t.vi !== t.en ? t.vi : '';
  };
  function span(text, l, cls) {
    var lang = l !== htmlLang(mode) ? ' lang="' + l + '"' : '';
    return cls || lang ? '<span' + (cls ? ' class="' + cls + '"' : '') + lang + '>' + esc(text) + '</span>' : esc(text);
  }
  /* HTML of content: <span lang="vi">vi</span> · <span class="en" lang="en">en</span> (the English muted) in envi,
     else one language, marked with lang="..." where it is not the page language. opts.sep, opts.enClass;
     opts.html = { name: '<a ...>…</a>' } puts raw HTML into {name} placeholders after escaping */
  VL.TH = function (x, vars, opts) {
    var t = texts(x, vars);
    opts = opts || {};
    if (both(t)) {
      return '<span lang="vi">' + rich(esc(t.vi), opts) + '</span>' + (opts.sep != null ? opts.sep : ' \u00b7 ') +
        '<span class="' + (opts.enClass || 'en') + '" lang="en">' + rich(esc(t.en), opts) + '</span>';
    }
    var o = one(t);
    return rich(span(o.t, o.l), opts);
  };
  /* HTML of one-language text (VL.U), marked with lang="..." where it is not the page language; opts.html as VL.TH */
  VL.UH = function (x, vars, opts) { var o = one(texts(x, vars)); return rich(span(o.t, o.l), opts); };
  /* lines of a call-out or 3D label: { primary, secondary, primaryLang, secondaryLang }. envi: Vietnamese above the
     English gloss; en / vi: one line (secondary ''), the other language where the mode's is missing */
  VL.TL = function (x, vars) {
    var t = texts(x, vars);
    if (both(t)) return { primary: t.vi, secondary: t.en, primaryLang: 'vi', secondaryLang: 'en' };
    var o = one(t);
    return { primary: o.t, secondary: '', primaryLang: o.l, secondaryLang: null };
  };
  /* {vi, en} for a pair of data fields, e.g. VL.T(VL.pair(n.label_vi, n.label_en)) */
  VL.pair = function (vi, en) { return { vi: nfc(vi), en: nfc(en) }; };

  /* ------------------------------------------------------------------ declarative markup
     data-i18n="key"             text of the element (an element without child elements): one language, or the pair
                                 HTML for keys of kind 'pair'; kind 'ui' adds the Vietnamese tooltip (title) in envi
     data-i18n-kind="ui|text|pair"  overrides the kind of the key for this element
     data-i18n-title="key"       title (tooltip), as VL.T: "vi · en" in envi
     data-i18n-aria="key"        aria-label, as VL.U
     data-i18n-placeholder / data-i18n-alt / data-i18n-content="key"   placeholder / alt / content, as VL.U
     data-i18n-vars='{"n":3}'    placeholder values (JSON)
     The layer owns the lang attribute of a data-i18n element (set where its text is not in the page language) and the
     title of a 'ui' element without data-i18n-title. VL.i18n.apply(root) after inserting markup that uses them. */
  var SEL = '[data-i18n],[data-i18n-title],[data-i18n-aria],[data-i18n-placeholder],[data-i18n-alt],[data-i18n-content]';
  var ATTRS = [['data-i18n-title', 'title', 'T'], ['data-i18n-aria', 'aria-label', 'U'], ['data-i18n-placeholder', 'placeholder', 'U'],
    ['data-i18n-alt', 'alt', 'U'], ['data-i18n-content', 'content', 'U']];
  function varsOf(el) {
    var v = el.getAttribute('data-i18n-vars');
    if (!v) return null;
    try { return JSON.parse(v); } catch (e) { return null; }
  }
  function applyEl(el) {
    var ok = true, k = el.getAttribute('data-i18n'), vars = varsOf(el), e;
    if (k) {
      e = entry(k);
      if (!e) ok = false;
      else {
        var kind = el.getAttribute('data-i18n-kind') || e.k;
        if (kind === 'pair') {
          el.innerHTML = VL.TH(k, vars);
          el.removeAttribute('lang');
        } else {
          var o = one(texts(k, vars));
          if (el.textContent !== o.t) el.textContent = o.t;
          if (o.l !== htmlLang(mode)) el.setAttribute('lang', o.l); else el.removeAttribute('lang');
        }
        if (kind === 'ui' && !el.hasAttribute('data-i18n-title')) {
          var tip = VL.tip(k, vars);
          if (tip) { el.setAttribute('title', tip); el.setAttribute('data-i18n-tip', ''); }
          else if (el.hasAttribute('data-i18n-tip')) { el.removeAttribute('title'); el.removeAttribute('data-i18n-tip'); }
        }
      }
    }
    ATTRS.forEach(function (a) {
      var key = el.getAttribute(a[0]);
      if (!key) return;
      if (!entry(key)) { ok = false; return; }
      el.setAttribute(a[1], VL[a[2]](key, vars));
    });
    if (ok) el.setAttribute('data-i18n-ok', '');
  }
  function apply(root) {
    root = root || document;
    var list = root.querySelectorAll ? Array.prototype.slice.call(root.querySelectorAll(SEL)) : [];
    if (root.nodeType === 1 && root.matches && root.matches(SEL)) list.unshift(root);
    list.forEach(applyEl);
    M.i18nApplied = (M.i18nApplied || 0) + list.length;
    return list.length;
  }
  function boot() {
    apply(document);
    /* anything still without its text (a key no dictionary has) shows its markup text from now on */
    ROOT.classList.remove('vl-i18n-boot');
    M.i18nBootMs = Math.round(performance.now());
    framesHook();
  }

  /* ------------------------------------------------------------------ switching, persistence, carrying */
  function storeSet(m) { try { localStorage.setItem(KEY, m); return true; } catch (e) { return false; /* storage blocked */ } }
  function carryLang() { return !!langFromUrl || (chosen && (location.protocol === 'file:' || !storageOK)); }
  /* add or replace lang=<m> in a URL's query, keeping its #hash and its other parameters (theme=) */
  VL.withLang = function (href, m) {
    var hash = '', i = href.indexOf('#');
    if (i >= 0) { hash = href.slice(i); href = href.slice(0, i); }
    var q = '', j = href.indexOf('?');
    if (j >= 0) { q = href.slice(j + 1); href = href.slice(0, j); }
    var parts = q ? q.split('&').filter(function (p) { return p && p.indexOf('lang=') !== 0; }) : [];
    parts.push('lang=' + m);
    return href + '?' + parts.join('&') + hash;
  };
  VL.carryLang = carryLang;
  function frames() { return Array.prototype.slice.call(document.querySelectorAll('iframe')); }
  function postLang(win, m) {
    try { if (win) { win.postMessage({ type: 'vlonto-lang', lang: m }, '*'); M.langPosts = (M.langPosts || 0) + 1; } } catch (e) { /* cross-origin frame */ }
  }
  var hooked = typeof WeakSet === 'function' ? new WeakSet() : null;
  function framesHook() {
    frames().forEach(function (f) {
      if (hooked && hooked.has(f)) return;
      if (hooked) hooked.add(f);
      f.addEventListener('load', function () { postLang(f.contentWindow, mode); });
      postLang(f.contentWindow, mode);
    });
  }
  /* opts.store (default true): remember the choice, like the header switch does; false for changes that follow
     another page (storage event, the embedding page) */
  VL.setLang = function (m, opts) {
    opts = opts || {};
    if (!valid(m)) return false;
    var prev = mode, changed = m !== mode;
    mode = m;
    setAttrs(m);
    M.lang = m;
    if (opts.store !== false) {
      chosen = true;
      M.langStored = storeSet(m);
      if (langFromUrl || !storageOK) {
        langFromUrl = m;
        try { history.replaceState(history.state, '', VL.withLang(location.href, m)); } catch (e) { /* file:// may refuse */ }
      }
    }
    syncSwitches();
    if (document.body) apply(document);
    if (!opts.fromParent) frames().forEach(function (f) { postLang(f.contentWindow, m); });
    if (changed) {
      M.langChanges = (M.langChanges || 0) + 1;
      var ev, detail = { lang: m, previous: prev };
      try { ev = new CustomEvent('vl:lang', { detail: detail }); } catch (e) { ev = document.createEvent('CustomEvent'); ev.initCustomEvent('vl:lang', false, false, detail); }
      document.dispatchEvent(ev);
    }
    return changed;
  };
  window.addEventListener('storage', function (e) {
    if (e.key === KEY && valid(e.newValue) && e.newValue !== mode) { chosen = true; VL.setLang(e.newValue, { store: false }); }
  });
  window.addEventListener('message', function (e) {
    var d = e.data;
    if (!d || typeof d !== 'object') return;
    if (d.type === 'vlonto-lang' && window.parent !== window && e.source === window.parent) {
      if (valid(d.lang) && d.lang !== mode) VL.setLang(d.lang, { store: false, fromParent: true });
      return;
    }
    if (d.type === 'vlonto-lang-request' && frames().some(function (f) { return f.contentWindow === e.source; })) {
      M.langRequests = (M.langRequests || 0) + 1;
      postLang(e.source, mode);
    }
  });
  /* an embedded document asks the page for the mode once its listener is in place */
  if (window.parent && window.parent !== window) { try { window.parent.postMessage({ type: 'vlonto-lang-request' }, '*'); } catch (e) { /* ignore */ } }
  /* internal links carry the mode where storage does not (see above) */
  document.addEventListener('click', function (e) {
    if (!carryLang()) return;
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || a.hasAttribute('download')) return;
    var h = a.getAttribute('href');
    if (!h || /^(?:[a-z][a-z0-9+.\-]*:|\/\/|#)/i.test(h) || !/\.html(?:[?#]|$)/i.test(h)) return;
    a.setAttribute('href', VL.withLang(h, mode));
  }, true);

  /* ------------------------------------------------------------------ the switch: EN · VI · EN–VI
     An ARIA radio group (roving tabindex; arrow keys move and select; Tab leaves). opts.labelledby: id of a visible
     label (else aria-label in the current language); opts.className: extra class. Every switch on the page follows
     the mode. */
  var switches = [];
  function syncSwitch(g) {
    if (!g.hasAttribute('aria-labelledby')) g.setAttribute('aria-label', VL.U('chrome.lang.group'));
    Array.prototype.forEach.call(g.querySelectorAll('[data-vl-lang]'), function (b) {
      var m = b.getAttribute('data-vl-lang'), on = m === mode;
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
      b.setAttribute('title', VL.T('chrome.lang.' + m));
    });
  }
  function syncSwitches() { switches.forEach(syncSwitch); }
  VL.langSwitch = function (opts) {
    opts = opts || {};
    var g = document.createElement('div');
    g.className = 'vl-lang' + (opts.className ? ' ' + opts.className : '');
    g.setAttribute('role', 'radiogroup');
    if (opts.labelledby) g.setAttribute('aria-labelledby', opts.labelledby);
    MODES.forEach(function (m) {
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('role', 'radio');
      b.setAttribute('data-vl-lang', m);
      b.textContent = CODE[m];
      b.addEventListener('click', function () { VL.setLang(m); });
      g.appendChild(b);
    });
    g.addEventListener('keydown', function (e) {
      var d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      var b = e.target && e.target.closest ? e.target.closest('[data-vl-lang]') : null;
      if (!d || !b || e.altKey || e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      var bs = Array.prototype.slice.call(g.querySelectorAll('[data-vl-lang]'));
      var n = bs[(bs.indexOf(b) + d + bs.length) % bs.length];
      VL.setLang(n.getAttribute('data-vl-lang'));
      n.focus();
    });
    switches.push(g);
    syncSwitch(g);
    return g;
  };

  VL.i18n = {
    add: add,
    apply: apply,
    has: function (k) { return !!DICT[k]; },
    get: function (k) { return DICT[k] ? { en: DICT[k].en, vi: DICT[k].vi, k: DICT[k].k, owner: OWNER[k] } : null; },
    keys: function (owner) { return Object.keys(DICT).filter(function (k) { return !owner || OWNER[k] === owner; }); },
    missing: function () { return Object.keys(missing); },
    htmlLang: function () { return htmlLang(mode); }
  };

  /* ------------------------------------------------------------------ core dictionary: the chrome of js/common.js,
     js/doc-theme.js and the skip links (the ontology's own Vietnamese labels and the site's existing pairs win) */
  add('i18n', {
    'chrome.nav.main': { en: 'Main', vi: 'Điều hướng chính', k: 'ui' },
    'chrome.nav.index': { en: '3D Ontology', vi: 'Bản thể học 3D', k: 'ui' },
    'chrome.nav.network': { en: '3D Legal Network', vi: 'Mạng pháp lý 3D', k: 'ui' },
    'chrome.nav.sparql': { en: 'SPARQL', vi: 'SPARQL', k: 'ui' },
    'chrome.nav.traces': { en: 'Traces', vi: 'Truy vết', k: 'ui' },
    'chrome.nav.dashboard': { en: 'Dashboard', vi: 'Bảng điều khiển', k: 'ui' },
    'chrome.nav.ontology': { en: 'Ontology docs', vi: 'Tài liệu bản thể học', k: 'ui' },
    'chrome.nav.playbook': { en: 'Playbook', vi: 'Sổ tay', k: 'ui' },
    'chrome.nav.downloads': { en: 'Downloads', vi: 'Tải xuống', k: 'ui' },
    'chrome.nav.about': { en: 'About', vi: 'Giới thiệu', k: 'ui' },
    'chrome.nav.paper': { en: 'Paper', vi: 'Bài báo', k: 'ui' },
    'chrome.nav.paperNewTab': { en: ' (arXiv, opens in a new tab)', vi: ' (arXiv, mở trong thẻ mới)', k: 'ui' },
    'chrome.brand.home': { en: 'VLOnto home: 3D ontology playground', vi: 'Trang chủ VLOnto: khu khám phá bản thể học 3D', k: 'ui' },
    'chrome.brand.tag': { en: 'Vietnamese Legal Ontology', vi: 'Bản thể học pháp luật Việt Nam', k: 'text' },
    'chrome.menu': { en: 'Menu', vi: 'Trình đơn', k: 'ui' },
    'chrome.theme.dark': { en: 'Dark theme', vi: 'Giao diện tối', k: 'ui' },
    'chrome.theme.toLight': { en: 'Switch to light theme', vi: 'Chuyển sang giao diện sáng', k: 'ui' },
    'chrome.theme.toDark': { en: 'Switch to dark theme', vi: 'Chuyển sang giao diện tối', k: 'ui' },
    'chrome.lang.group': { en: 'Language', vi: 'Ngôn ngữ', k: 'ui' },
    'chrome.lang.en': { en: 'English', vi: 'Tiếng Anh', k: 'ui' },
    'chrome.lang.vi': { en: 'Vietnamese', vi: 'Tiếng Việt', k: 'ui' },
    'chrome.lang.envi': { en: 'English and Vietnamese', vi: 'Song ngữ Anh – Việt', k: 'ui' },
    'chrome.skip.content': { en: 'Skip to content', vi: 'Chuyển đến nội dung chính', k: 'ui' },
    'chrome.skip.search': { en: 'Skip to search', vi: 'Chuyển đến ô tìm kiếm', k: 'ui' },
    'chrome.skip.query': { en: 'Skip to the query editor', vi: 'Chuyển đến ô soạn truy vấn', k: 'ui' },
    'chrome.skip.questions': { en: 'Skip to the questions', vi: 'Chuyển đến danh sách câu hỏi', k: 'ui' },
    'chrome.cite': { en: 'Cite: {short}, arXiv:{arxiv}', vi: 'Trích dẫn: {short}, arXiv:{arxiv}', k: 'ui' },
    'chrome.foot.sources': { en: 'Sources and attribution', vi: 'Nguồn dữ liệu và ghi nguồn', k: 'text' },
    'chrome.foot.notAdvice': { en: 'Not legal advice', vi: 'Không phải tư vấn pháp lý', k: 'text' },
    'chrome.foot.disclaimer': { en: 'VLOnto is not an official legal text and is not legal advice.',
      vi: 'VLOnto không phải văn bản pháp luật chính thức và không phải tư vấn pháp lý.', k: 'text' },
    'chrome.foot.validity': { en: 'Validity is derived automatically (as of {date}) and is unknown for many documents. Always read the document at its source before relying on it.',
      vi: 'Tình trạng hiệu lực được suy ra tự động (tính đến ngày {date}) và chưa xác định với nhiều văn bản. Luôn đọc văn bản tại nguồn trước khi sử dụng.', k: 'text' },
    'chrome.foot.licences': { en: 'Ontology and VLOnto\u2019s own data: CC BY 4.0. Fonts: SIL OFL 1.1. Libraries: MIT / Apache-2.0 (see Downloads).',
      vi: 'Bản thể học và dữ liệu riêng của VLOnto: CC BY 4.0. Phông chữ: SIL OFL 1.1. Thư viện: MIT / Apache-2.0 (xem Tải xuống).', k: 'text' },
    'chrome.foot.built': { en: 'built {date}', vi: 'dựng ngày {date}', k: 'text' },
    'chrome.foot.downloads': { en: 'Downloads and checksums', vi: 'Tải xuống và mã kiểm tra', k: 'ui' },
    'chrome.foot.howToCite': { en: 'How to cite', vi: 'Cách trích dẫn', k: 'ui' },
    'chrome.foot.licencesLink': { en: 'Licences', vi: 'Giấy phép', k: 'ui' },
    'chrome.bar.notAdvice': { en: 'Not legal advice.', vi: 'Không phải tư vấn pháp lý.', k: 'text' },
    /* [md:...] [lg:...] [xl:...] = parts the footbar drops on phones / tablets / below 1500 px (css/site.css) */
    'chrome.bar.data': { en: 'Data: [md:four public ]datasets by TMQuan[lg: (thuvienphapluat.vn)][xl:; relations are extracted automatically and may be wrong].',
      vi: 'Dữ liệu: [md:bốn ]bộ dữ liệu do TMQuan công bố[lg: (thuvienphapluat.vn)][xl:; các quan hệ được trích xuất tự động và có thể sai].', k: 'text' },
    'chrome.bar.attribution': { en: 'Attribution', vi: 'Ghi nguồn', k: 'ui' },
    'chrome.doc.back': { en: '\u2190 VLOnto ontology page', vi: '\u2190 Trang bản thể học VLOnto', k: 'ui' },
    'chrome.doc.generated': { en: 'Documentation generated by pyLODE from vlonto.ttl', vi: 'Tài liệu do pyLODE tạo từ vlonto.ttl', k: 'text' },
    'chrome.doc.paper': { en: 'Paper: arXiv:2611.11426', vi: 'Bài báo: arXiv:2611.11426', k: 'ui' },
    'chrome.doc.licences': { en: 'Licences and attribution', vi: 'Giấy phép và ghi nguồn', k: 'ui' },
    'chrome.doc.cite': { en: 'Cite: Bui & Tran Minh (2026), arXiv:2611.11426', vi: 'Trích dẫn: Bui & Tran Minh (2026), arXiv:2611.11426', k: 'ui' },
    'chrome.doc.englishOnly': { en: 'This reference is in English only.', vi: 'Tài liệu tham chiếu này chỉ có bằng tiếng Anh.', k: 'text' },
    'common.copy': { en: 'Copy', vi: 'Sao chép', k: 'ui' },
    'common.copied': { en: 'Copied to clipboard', vi: 'Đã sao chép vào bộ nhớ tạm', k: 'text' },
    'common.selected': { en: 'Text selected: press Ctrl+C (\u2318C on a Mac) to copy', vi: 'Đã chọn văn bản: nhấn Ctrl+C (\u2318C trên máy Mac) để sao chép', k: 'text' },
    'common.noCopy': { en: 'Copying is not available here', vi: 'Không sao chép được ở đây', k: 'text' },
    'common.noMatch': { en: 'No match', vi: 'Không có kết quả', k: 'text' },
    'common.newTab': { en: ' (opens in a new tab)', vi: ' (mở trong thẻ mới)', k: 'ui' },
    'common.paper.cite': { en: 'Cite (BibTeX)', vi: 'Trích dẫn (BibTeX)', k: 'text' },
    'common.paper.bibAria': { en: 'BibTeX for the paper', vi: 'BibTeX của bài báo', k: 'ui' },
    'common.paper.note': { en: 'The approach is described in the paper above; numbers here are computed from the {release} release and can differ from the paper\u2019s.',
      vi: 'Phương pháp được mô tả trong bài báo trên; các con số ở đây được tính từ bản phát hành {release} và có thể khác với số liệu của bài báo.', k: 'text' },
    'common.fromRelease': { en: 'from v{n}', vi: 'từ v{n}', k: 'text' }
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
