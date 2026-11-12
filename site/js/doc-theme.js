/* VLOnto - light/dark theme for the pyLODE reference page (site/ontology/vlonto.html, patched by
   scripts/site/build_site.py). The inline <head> script already set html[data-theme] before first paint
   (?theme=, else localStorage 'vlonto.theme', else prefers-color-scheme). This file adds the toggle to the doc bar,
   remembers the choice, follows the ontology page that embeds this file in an iframe (postMessage, both ways),
   follows the system setting while nothing was chosen, and carries the theme on links back to the site where
   storage is not shared (file://). Classic script, no dependencies. */
(function () {
  'use strict';
  var root = document.documentElement, KEY = 'vlonto.theme';
  var fromUrl = (/[?&]theme=(light|dark)(?:&|$)/.exec(location.search) || [])[1] || null;
  var stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) { stored = null; }
  var chosen = !!fromUrl || stored === 'light' || stored === 'dark';
  var embedded = window.parent && window.parent !== window;
  var btn = null, stats = { received: 0, storage: 0, requests: 0 };
  function cur() { return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }
  function sync() {
    if (!btn) return;
    var dark = cur() === 'dark';
    btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    btn.setAttribute('title', dark ? 'Switch to light theme' : 'Switch to dark theme');
  }
  function apply(t, store, tellParent) {
    if (t !== 'light' && t !== 'dark') return;
    root.setAttribute('data-theme', t);
    root.style.colorScheme = t;
    if (store) { chosen = true; try { localStorage.setItem(KEY, t); } catch (e) { /* storage blocked */ } }
    sync();
    if (tellParent && embedded) { try { window.parent.postMessage({ type: 'vlonto-theme', theme: t }, '*'); } catch (e) { /* ignore */ } }
  }
  var bar = document.querySelector('.vl-doc-bar .vl-doc-right') || document.querySelector('.vl-doc-bar');
  if (bar) {
    btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'vl-theme-btn';
    btn.setAttribute('aria-label', 'Dark theme');
    btn.innerHTML = '<svg class="i-sun" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/>' +
      '<path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></svg>' +
      '<svg class="i-moon" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M20.2 14.6A8.3 8.3 0 0 1 9.4 3.8a8.3 8.3 0 1 0 10.8 10.8z"/></svg>';
    btn.addEventListener('click', function () { apply(cur() === 'dark' ? 'light' : 'dark', true, true); });
    bar.appendChild(btn);
    sync();
  }
  window.addEventListener('message', function (e) {
    var d = e.data;
    if (e.source !== window.parent || !d || d.type !== 'vlonto-theme') return;
    stats.received++;
    apply(d.theme, false, false);
  });
  window.addEventListener('storage', function (e) {
    if (e.key === KEY && (e.newValue === 'light' || e.newValue === 'dark')) { chosen = true; stats.storage++; apply(e.newValue, false, false); }
  });
  /* embedded: ask the page for its theme now that the listener is in place (the page may have changed it while this
     long document was still loading; its message would have been missed) */
  if (embedded) { try { window.parent.postMessage({ type: 'vlonto-theme-request' }, '*'); stats.requests++; } catch (e) { /* ignore */ } }
  try {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onSystem = function (e) { if (!chosen && !embedded) apply(e.matches ? 'dark' : 'light', false, false); };
    if (mq.addEventListener) mq.addEventListener('change', onSystem); else if (mq.addListener) mq.addListener(onSystem);
  } catch (e) { /* no matchMedia */ }
  document.addEventListener('click', function (e) {
    if (!(fromUrl || (chosen && location.protocol === 'file:'))) return;
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var h = a.getAttribute('href');
    if (!h || /^(?:[a-z][a-z0-9+.\-]*:|\/\/|#)/i.test(h) || !/\.html(?:[?#]|$)/i.test(h)) return;
    var hash = '', i = h.indexOf('#');
    if (i >= 0) { hash = h.slice(i); h = h.slice(0, i); }
    var q = '', j = h.indexOf('?');
    if (j >= 0) { q = h.slice(j + 1); h = h.slice(0, j); }
    var parts = q ? q.split('&').filter(function (p) { return p && p.indexOf('theme=') !== 0; }) : [];
    parts.push('theme=' + cur());
    a.setAttribute('href', h + '?' + parts.join('&') + hash);
  }, true);
  window.__VLONTO_DOC_THEME = { theme: cur, embedded: embedded, stats: stats };
})();
