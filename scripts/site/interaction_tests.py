#!/usr/bin/env python3
"""interaction_tests.py - Playwright interaction checks for the VLOnto site, over http:// and file://, desktop and mobile.

    $W/python scripts/site/interaction_tests.py --root site --out $V/build/site_tests [--modes http,file] [--viewports 1440x900,390x844]

Checks (each records pass/fail, details, console errors, page errors, failed and external requests, screenshots):
  playground    (index.html, the landing page) search "Article" and "Điều" -> panel shows the class; click a class on the
                canvas -> panel; run a CONSTRUCT example -> the 3D graph changes (overlay) and back; a SELECT in the drawer
                returns rows; label toggle; PNG export; fps
  network-3d    search 45/2019/QH14 -> panel shows Bộ luật Lao động with the replacement chain (10/2012/QH13); year filter;
                colour mode; fps of the default dataset and of the other one
  sparql        the 10 examples return rows_on_core; CONSTRUCT examples (triple counts) and the 3D drawing; syntax error message; CSV export
  dashboard     type / area / year filters change the chart data and the counts; reset
  playbook      renders content or the placeholder without errors
  downloads     every listed download exists and its sha256 matches the page
  about         navigation has the 9 pages (index.html first, traces.html among them) + the Paper link; tool cards link to
                existing pages; paper card
  traces        traces.html: the whole 3D legal network (network-3d.html's documents and links, layers) with all 540
                traces and 27 areas in it, everything at the light alpha, while traces are chosen the other traces at
                the faint alpha (the network stays light); every traced law is its network document; no
                area cells; one list of the 540 questions under 27 area headings with a search (VI / EN, diacritic-
                insensitive; 'n of 540') and arrow keys; three questions chosen: exactly each trace opaque (alphas read
                from the page), its pixels lit, call-outs clean (a must under the open hop panel is occluded), Fig. 5
                hop panel; several: round button / Space / Ctrl-Cmd-click add and remove, All 20 per heading, the
                stepper ('3 of 20'), Clear; a click on a question node chooses it (Ctrl adds); node and document
                clicks; Escape; one static camera (Zoom to selection, Reset view keeps the choice); deep links (#q=a:r,
                #q=a:r1,r2;b:r3, #area=&all=1, #area=&q= per theme, #area=) and the theme switch; EN / VI; no overflow
  redirect      ontology-3d.html#class=... (old playground address) forwards to index.html and keeps the hash
  theme         toggle on every page re-renders canvas / charts / CONSTRUCT view / pyLODE frame; persistence (storage and
                ?theme= carry), system preference, ?theme=dark
  paper         Paper link in header, footer and footbar on every page; BibTeX copy (clipboard and fallback); no overflow
  paper_style   the 3D views drawn like the paper's figures, both themes: tokens and Libertinus Sans on the playground,
                the legal network and the CONSTRUCT view; selecting a class / 45/2019/QH14 draws the traced path (core and
                halo pixels), the network traces the replacement chain; other pages keep their palette; screenshots
Exit 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import http.server
import json
import math
import os
import re
import sys
import threading
import time
import urllib.parse
from pathlib import Path


# Slow CI runners (GitHub: 4 CPUs, WebGL in SwiftShader) set VLONTO_TIMEOUT_SCALE (scripts/site/ci_check.sh: 4); every
# wait and screenshot limit is multiplied by it. The assertions are unchanged; on the build node it stays 1.
TIMEOUT_SCALE = max(1.0, float(os.environ.get("VLONTO_TIMEOUT_SCALE") or 1))


def T_(ms: int) -> int:
    return int(ms * TIMEOUT_SCALE)


HERE = Path(__file__).resolve().parent


def make_server(root: Path):
    class H(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".wasm": "application/wasm",
                          ".woff2": "font/woff2", ".json": "application/json", ".ttl": "text/turtle", ".css": "text/css", ".html": "text/html"}

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Ctx:
    def __init__(self, browser, root: Path, base_http: str, mode: str, vp, out: Path, themes=("light", "dark")):
        self.browser, self.root, self.base_http, self.mode, self.vp, self.out = browser, root, base_http, mode, vp, out
        self.mobile = vp[0] < 700
        self.themes = list(themes)

    def url(self, page: str, query: str = "") -> str:
        """page may carry a #hash; query ('?theme=dark') goes before it, for http:// and file:// alike."""
        path, _, frag = page.partition("#")
        if self.mode == "http":
            return self.base_http + path + query + (("#" + frag) if frag else "")
        return (self.root / path).resolve().as_uri() + query + (("#" + frag) if frag else "")

    def open(self, page: str, ready_timeout=T_(180000), ready=True, scheme="light", query="", init_script=None, permissions=None):
        """New browser context per page: scheme = the emulated system setting (prefers-color-scheme), which is the
        site's default theme when nothing was chosen; query e.g. '?theme=dark'; init_script runs before page scripts."""
        ctx = self.browser.new_context(viewport={"width": self.vp[0], "height": self.vp[1]}, device_scale_factor=2 if self.mobile else 1,
                                       is_mobile=self.mobile, has_touch=self.mobile, accept_downloads=True, color_scheme=scheme)
        if permissions and self.mode == "http":
            ctx.grant_permissions(permissions, origin=self.base_http.rstrip("/"))
        if init_script:
            ctx.add_init_script(init_script)
        pg = ctx.new_page()
        pg.set_default_timeout(T_(30000))
        log = {"console_errors": [], "page_errors": [], "failed_requests": [], "external_requests": []}
        root_prefix = self.base_http if self.mode == "http" else self.root.resolve().as_uri().rstrip("/") + "/"
        pg.on("console", lambda m: log["console_errors"].append(m.text[:300]) if m.type == "error" else None)
        pg.on("pageerror", lambda e: log["page_errors"].append(str(e)[:300]))
        pg.on("requestfailed", lambda r: log["failed_requests"].append(f"{r.url[:160]} :: {r.failure}"))
        pg.on("response", lambda r: log["failed_requests"].append(f"{r.status} {r.url[:160]}") if r.status >= 400 else None)

        def on_req(r):
            u = r.url
            if u.startswith(("data:", "blob:", "about:")) or u.startswith(root_prefix):
                return
            log["external_requests"].append(u[:160])
        pg.on("request", on_req)
        t0 = time.time()
        pg.goto(self.url(page, query), wait_until="load", timeout=T_(120000))
        if ready:
            pg.wait_for_function("window.__VLONTO_READY === true", timeout=ready_timeout)
        log["ready_s"] = round(time.time() - t0, 2)
        return ctx, pg, log

    def shot(self, pg, name: str) -> str:
        p = self.out / "shots" / f"{name}__{self.mode}__{self.vp[0]}x{self.vp[1]}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        # a screenshot waits for a frame: on a software renderer a frame of the full network can take seconds
        pg.screenshot(path=str(p), timeout=T_(60000))
        return str(p.relative_to(self.out))


def fail_details(e, c, pg, name):
    """Error text with Playwright's call-log lines that explain a timeout, a screenshot and app state at failure."""
    lines = [ln for ln in str(e).splitlines() if ln.strip()]
    keys = ("intercepts pointer", "not visible", "not stable", "element is", "outside of the viewport", "waiting for", "did not")
    keep = lines[:1] + [ln.strip()[:220] for ln in lines[1:] if any(k in ln for k in keys)][:6]
    out = {"error": " | ".join(keep)[:1500]}
    try:
        out["shot"] = c.shot(pg, "FAIL_" + re.sub(r"[^a-z0-9]+", "_", name.lower())[:40])
    except Exception as ex:  # noqa
        out["shot_error"] = str(ex)[:120]
    try:
        out["app"] = pg.evaluate("""() => { const m = window.__VLONTO_METRICS || {};
            return {selected: m.selected, hover: m.hover, view: m.view, active: document.activeElement ? document.activeElement.id || document.activeElement.tagName : null}; }""")
    except Exception as ex:  # noqa
        out["app_error"] = str(ex)[:120]
    return out


def no_hscroll(c, pg, where: str):
    """Fail when the page became wider than the device (mobile Chrome would zoom out or scroll sideways)."""
    w = pg.evaluate("() => Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0)")
    if w > c.vp[0] + 1:
        raise RuntimeError(f"{where}: page is {w} px wide at a {c.vp[0]} px viewport")
    return w


def panel_has(pg, *texts, timeout=T_(30000)):
    js = "(t) => { const p = document.getElementById('panel'); return !!p && !p.classList.contains('hidden') && t.every(x => p.textContent.includes(x)); }"
    pg.wait_for_function(js, arg=list(texts), timeout=timeout)
    return True


def set_lang(c: Ctx, pg, mode: str):
    """the header's language switch (js/i18n.js): the bar on wide screens, the menu sheet on phones (closed again after);
    waits for <html data-lang>. The 3D views re-render on the 'vl:lang' event (window.__VLONTO_METRICS.labelsLang)."""
    if c.mobile:
        pg.click(".vl-menu-btn")
        pg.click(f".vl-lang-sheet [data-vl-lang={mode}]")
        if pg.evaluate("() => { const b = document.querySelector('.vl-menu-btn'); return !!b && b.getAttribute('aria-expanded') === 'true'; }"):
            pg.click(".vl-menu-btn")
    else:
        pg.click(f".vl-lang-bar [data-vl-lang={mode}]")
    pg.wait_for_function("(m) => document.documentElement.getAttribute('data-lang') === m", arg=mode, timeout=T_(10000))


def stable_value(pg, js: str, timeout=T_(20000)):
    """a value read twice 400 ms apart without a change (the camera once a flight has ended)"""
    t_end = time.time() + timeout / 1000
    prev = pg.evaluate(js)
    while time.time() < t_end:
        pg.wait_for_timeout(400)
        cur = pg.evaluate(js)
        if cur == prev:
            return cur
        prev = cur
    return prev


def t_ontology(c: Ctx):
    res = {"test": "playground (index.html)", "checks": []}
    ctx, pg, log = c.open("index.html")          # the 3D ontology playground is the landing page
    M = lambda: pg.evaluate("window.__VLONTO_METRICS")
    sel = "#onto-search-m" if c.mobile else "#onto-search"
    base_nodes = M().get("ontologyNodes")

    def check(name, fn):
        t0 = time.time()
        try:
            det = fn()
            res["checks"].append({"name": name, "pass": True, "details": det, "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": fail_details(e, c, pg, name), "s": round(time.time() - t0, 2)})

    def search_article():
        pg.fill(sel, "Article")
        pg.wait_for_selector(("#onto-suggest-m" if c.mobile else "#onto-suggest") + " li[role=option]", timeout=T_(10000))
        first = pg.inner_text(("#onto-suggest-m" if c.mobile else "#onto-suggest") + " li[role=option]")
        pg.press(sel, "Enter")
        panel_has(pg, "Article", "Điều")
        pg.wait_for_timeout(1300)
        no_hscroll(c, pg, "details panel open")
        return {"first_suggestion": first.split("\n")[0], "selected": M().get("selected"), "shot": c.shot(pg, "ontology3d_search_article")}
    check("search 'Article' -> panel shows the class (Article / Điều)", search_article)

    def search_dieu():
        pg.keyboard.press("Escape")
        pg.fill(sel, "Điều")
        pg.wait_for_selector(("#onto-suggest-m" if c.mobile else "#onto-suggest") + " li[role=option]", timeout=T_(10000))
        first = pg.inner_text(("#onto-suggest-m" if c.mobile else "#onto-suggest") + " li[role=option]").split("\n")[0]
        pg.press(sel, "Enter")
        panel_has(pg, "Article")
        return {"first_suggestion": first}
    check("search 'Điều' (Vietnamese) -> Article", search_dieu)

    def click_class():
        pg.keyboard.press("Escape")
        pg.evaluate("() => { document.activeElement && document.activeElement.blur && document.activeElement.blur(); const x = document.querySelector('[data-act=close]'); if (x) x.click(); }")
        pg.click("#btn-reset2")
        pg.wait_for_timeout(1600)
        pg.wait_for_function("!window.__VLONTO_METRICS.flying", timeout=T_(20000))    # the camera's flight back has ended
        tried = []
        cands = ["vlo:Law", "vlo:Decree", "vlo:Circular", "vlo:Article", "vlo:LegalDocument", "vlo:LegalArea", "vlo:Provision", "vlo:LegalChange", "vlo:Code"]
        for cid in cands:
            p = pg.evaluate("id => window.VLApp.screenPos(id)", cid)
            if not (p and p["inside"]):
                tried.append([cid, "off screen"])
                continue
            hit = pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e ? e.tagName : null; }", [p["x"], p["y"]])
            if hit != "CANVAS":
                tried.append([cid, f"covered by {hit}"])
                continue
            if c.mobile:
                # a real tap lasts ~100-200 ms; the playground picks in screen space when the finger lifts (pointerup)
                cdp = pg.context.new_cdp_session(pg)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": p["x"], "y": p["y"]}]})
                pg.wait_for_timeout(180)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                cdp.detach()
            else:
                pg.mouse.move(p["x"] - 30, p["y"] - 30)
                pg.mouse.move(p["x"], p["y"], steps=6)
                pg.wait_for_timeout(600)
                hov = pg.evaluate("window.__VLONTO_METRICS.hover")
                if hov != cid:
                    tried.append([cid, f"hover is {hov}"])
                    continue
                pg.mouse.click(p["x"], p["y"])
            try:
                pg.wait_for_function("id => window.__VLONTO_METRICS.selected === id", arg=cid, timeout=T_(8000))
            except Exception:  # noqa
                tried.append([cid, f"selected {pg.evaluate('window.__VLONTO_METRICS.selected')}"])
                continue
            label = pg.evaluate("id => window.VLApp.state().panelText.slice(0, 120)", cid)
            pg.wait_for_timeout(1200)
            return {"clicked": cid, "x": round(p["x"]), "y": round(p["y"]), "panel_starts": label, "tried": tried, "shot": c.shot(pg, "ontology3d_click_class")}
        raise RuntimeError(f"no class node could be clicked: {tried}")
    check("click a class on the canvas -> panel", click_class)

    # v1.1 redesign: the ontology on hierarchy planes (one per depth of the subClassOf hierarchy, then the concept schemes,
    # then the external vocabularies), links as curves coloured by kind, "Colour by: Module / Kind", the LINKS toggles
    def planes_and_controls():
        pg.keyboard.press("Escape")
        pg.evaluate("() => { const x = document.querySelector('[data-act=close]'); if (x) x.click(); }")
        pg.click("#btn-reset2")
        pg.wait_for_function("!window.__VLONTO_METRICS.flying", timeout=T_(20000))
        r0 = (pg.evaluate(JS_CALLOUTS) or {}).get("runs", 0)
        wait_callouts(pg, r0)
        r = pg.evaluate("""() => {
          const M = window.__VLONTO_METRICS, L = window.VLApp.layout(), OG = window.VLONTO.ontology_graph, hid = new Set(M.releaseScope.hidden || []);
          const kind = {}, par = {}, memo = {};
          OG.nodes.forEach((n) => { if (!hid.has(n.id)) kind[n.id] = n.kind; });
          OG.links.forEach((l) => { if (l.type === 'subClassOf' && kind[l.source] && kind[l.target] && l.source !== l.target) (par[l.source] = par[l.source] || []).push(l.target); });
          const dep = (id) => memo[id] != null ? memo[id] : (memo[id] = Math.max(0, ...(par[id] || []).filter((p) => kind[p] === 'class').map((p) => dep(p) + 1)));
          const ids = Object.keys(kind), maxD = Math.max(...ids.filter((i) => kind[i] === 'class').map(dep));
          const wrong = ids.filter((i) => { const want = kind[i] === 'class' ? dep(i) : kind[i] === 'scheme' ? maxD + 1 : maxD + 2; return !L.nodes[i] || L.nodes[i].plane !== want; });
          const co = M.callouts || {};
          return { planes: (M.planes || []).map((p) => [p.key, p.count, p.shown]), maxD, terms: ids.length, wrong, curves: M.curves, detail: M.curveDetail,
            links: M.ontologyLinks, status: document.getElementById('status').textContent,
            toggles: Array.from(document.querySelectorAll('#link-toggles input[data-link]')).map((i) => i.getAttribute('data-link')),
            planeNames: (co.placed || []).map((p) => p.id).filter((x) => /^plane-/.test(x)) }; }""")
        bad = []
        if r["wrong"] or len(r["planes"]) != r["maxD"] + 3 or not all(p[2] for p in r["planes"]):
            bad.append(f"planes {r['planes']}, terms off their plane {r['wrong'][:6]}")
        cv = r["curves"] or {}
        segs = {"full": 16, "reduced": 8}.get(r["detail"])
        if cv.get("links") != r["links"] or not segs or (cv.get("segs") or {}).get("link") != segs:
            bad.append(f"curves {cv} ({r['detail']}) for {r['links']} links")
        if r["toggles"] != ["subClassOf", "property", "alignment", "inScheme"]:
            bad.append(f"link toggles {r['toggles']}")
        if not re.match(r"^\d+ terms · \d+ links shown", r["status"]):
            bad.append(f"status {r['status']!r}")
        if len(r["planeNames"]) < (1 if c.mobile else 4):
            bad.append(f"plane names placed: {r['planeNames']}")
        # colour switch (the buttons sit in the side panel, closed on a phone: clicked from script)
        k = pg.evaluate("""async () => { const M = window.__VLONTO_METRICS, css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim().toLowerCase();
          document.querySelector('[data-color=kind]').click(); await new Promise((f) => setTimeout(f, 200));
          const kind = { by: M.colorBy, article: window.VLApp.nodeColor('vlo:Article'), want: css('--o3d-kind-class'), legend: document.getElementById('legend').textContent };
          document.querySelector('[data-color=module]').click(); await new Promise((f) => setTimeout(f, 200));
          return { kind, module: { by: M.colorBy, article: window.VLApp.nodeColor('vlo:Article'), want: window.VL.moduleColor('provisions').toLowerCase() } }; }""")
        if k["kind"]["by"] != "kind" or k["kind"]["article"] != k["kind"]["want"] or k["module"]["by"] != "module" or k["module"]["article"] != k["module"]["want"]:
            bad.append(f"colour switch {k}")
        # LINKS: property links off and on again
        t = pg.evaluate("""async () => { const M = window.__VLONTO_METRICS, i = document.querySelector('#link-toggles input[data-link=property]'), n0 = M.statusCounts.links;
          const cnt = +(i.closest('label').querySelector('.count').textContent.replace(/[^0-9]/g, ''));
          i.click(); await new Promise((f) => setTimeout(f, 200)); const off = M.statusCounts.links;
          i.click(); await new Promise((f) => setTimeout(f, 200)); return { n0, cnt, off, on: M.statusCounts.links }; }""")
        if t["off"] != t["n0"] - t["cnt"] or t["on"] != t["n0"] or not t["cnt"]:
            bad.append(f"property toggle {t}")
        if bad:
            raise RuntimeError("; ".join(bad))
        return {"planes": r["planes"], "curves": {"links": cv.get("links"), "detail": r["detail"], "segs": cv.get("segs")}, "status": r["status"][:60],
                "plane_names": r["planeNames"], "colour": k, "toggle": t, "shot": c.shot(pg, "ontology3d_planes")}
    check("hierarchy planes (every term on the plane of its depth), curved links by kind, plane names, colour by module / kind, LINKS toggles", planes_and_controls)

    # release v1 (js/common.js VL.releaseScope): the terms whose scope note says they are populated from VLOnto 2.0 are
    # left out of the playground (the ontology page and its pyLODE reference keep them)
    V2_TERMS = {"vlo:Court", "vlo:JudicialDocument", "vlo:CourtDecision", "vlo:Judgment", "vlo:CourtRuling", "vlo:Precedent", "vlo:CourtLevel",
                "vlo:InstanceLevel", "vlo:CaseCategory", "vlo:CourtLevelScheme", "vlo:InstanceLevelScheme", "vlo:CaseCategoryScheme"}
    V2_PROPS = {"vlo:decidedBy", "vlo:instanceLevel", "vlo:caseCategory", "vlo:selectedFrom", "vlo:appliesProvision", "vlo:appliesDocument",
                "vlo:citesCase", "vlo:appliesPrecedent"}

    def release_scope():
        r = pg.evaluate("""() => { const S = (window.__VLONTO_METRICS || {}).releaseScope || {};
            return { scope: S, chips: Array.from(document.querySelectorAll('#module-chips [data-mod]')).map(b => b.getAttribute('data-mod')),
              note: ((document.querySelector('#module-later') || {}).textContent || '').trim(),
              drawn: ['vlo:CourtDecision', 'vlo:Court', 'vlo:CaseCategoryScheme'].filter(id => window.VLApp.screenPos(id)),
              search: ['tòa án', 'court', 'bản án', 'judgment', 'precedent', 'án lệ', 'decided by'].map(q => window.VLApp.searchIds(q)).flat() }; }""")
        sc, hidden = r["scope"], set(r["scope"].get("hidden") or [])
        bad = []
        if not V2_TERMS <= hidden:
            bad.append(f"not left out: {sorted(V2_TERMS - hidden)}")
        if set(sc.get("hiddenProperties") or []) != V2_PROPS:
            bad.append(f"properties left out {sc.get('hiddenProperties')}")
        if sc.get("laterModules") != {"judiciary": 2} or "judiciary" in r["chips"]:
            bad.append(f"modules: later {sc.get('laterModules')}, chips {r['chips']}")
        if r["note"] != "Tư pháp (tòa án) · Judiciary: from v2":
            bad.append(f"module note {r['note']!r}")
        if r["drawn"]:
            bad.append(f"drawn: {r['drawn']}")
        leaked = sorted(set(x for x in r["search"] if x in hidden or x in V2_PROPS))
        if leaked:
            bad.append(f"search suggests {leaked}")
        if sc.get("nodes") != 75 - len(hidden) or sc.get("links", 0) + sc.get("hiddenLinks", 0) != 104:
            bad.append(f"counts: {sc.get('nodes')} nodes + {len(hidden)} left out (75), {sc.get('links')} links + {sc.get('hiddenLinks')} left out (104)")
        if bad:
            raise RuntimeError("; ".join(bad))
        return {"left_out": sorted(hidden), "properties": len(V2_PROPS), "nodes": sc.get("nodes"), "links": sc.get("links"),
                "chips": len(r["chips"]), "note": r["note"]}
    check("release v1: terms populated from v2 (judiciary module, vlo:Court) left out; the module note", release_scope)

    def construct():
        pg.keyboard.press("Escape")
        pg.evaluate("() => { const a = document.activeElement; if (a && a.blur) a.blur(); const x = document.querySelector('[data-act=close]'); if (x) x.click(); window.scrollTo(0, 0); }")
        pg.wait_for_timeout(300)
        pg.click("#btn-query-m" if c.mobile else "#btn-query")
        pg.wait_for_function("window.__VLONTO_METRICS.storeTriples > 0", timeout=T_(60000))
        no_hscroll(c, pg, "query drawer open")
        pg.select_option("#qd-example", "c0")
        pg.click("#qd-run")
        pg.wait_for_function("(window.__VLONTO_METRICS.view || '').indexOf('construct') === 0", timeout=T_(60000))
        pg.wait_for_timeout(2500)
        m = M()
        st = pg.evaluate("window.VLApp.state()")
        shot = c.shot(pg, "ontology3d_construct")
        if not (m.get("constructTriples", 0) > 0 and st["nodes"] > base_nodes):
            raise RuntimeError(f"graph did not change: {m.get('constructTriples')} triples, nodes {st['nodes']} vs {base_nodes}")
        status = pg.inner_text("#qd-status")
        pg.click("#qd-back")
        pg.wait_for_function("window.__VLONTO_METRICS.view === 'ontology'", timeout=T_(20000))
        back = pg.evaluate("window.VLApp.state()")
        return {"triples": m.get("constructTriples"), "nodes_before": base_nodes, "nodes_after": st["nodes"], "links_after": st["links"],
                "nodes_back": back["nodes"], "store_triples": m.get("storeTriples"), "status": status[:200], "shot": shot}
    check("run a CONSTRUCT example -> 3D graph changes (overlay) and back", construct)

    def select_in_drawer():
        pg.select_option("#qd-example", "s0")
        pg.click("#qd-run")
        pg.wait_for_function("window.__VLONTO_METRICS.lastQuery && window.__VLONTO_METRICS.lastQuery.form === 'SELECT'", timeout=T_(30000))
        lq = M()["lastQuery"]
        rows = pg.evaluate("document.querySelectorAll('#qd-result table tbody tr').length")
        if lq.get("count") != 1 or rows != 1:
            raise RuntimeError(f"expected 1 row, got {lq} / {rows}")
        return {"rows": rows, "ms": lq.get("ms")}
    check("SELECT example in the query drawer -> table (1 row)", select_in_drawer)

    def construct_replace():
        pg.click("[data-cm=replace]")
        pg.select_option("#qd-example", "c4")
        pg.click("#qd-run")
        pg.wait_for_function("window.__VLONTO_METRICS.view === 'construct-replace'", timeout=T_(30000))
        pg.wait_for_timeout(2000)
        st = pg.evaluate("window.VLApp.state()")
        shot = c.shot(pg, "ontology3d_construct_replace")
        pg.click("#qd-back")
        pg.wait_for_function("window.__VLONTO_METRICS.view === 'ontology'", timeout=T_(20000))
        pg.click("#qd-close")
        return {"nodes": st["nodes"], "links": st["links"], "shot": shot}
    check("CONSTRUCT in replace mode (class hierarchy) and back", construct_replace)

    def labels_vi():
        # the playground's own label toggle is gone: the header's language switch (EN / VI / EN–VI) relabels the
        # call-outs (labelsLang, VLApp.labelLines) and the legend, keeps the camera, and EN–VI comes back as before
        if pg.evaluate("document.querySelectorAll('button[data-lang]').length"):
            raise RuntimeError("the per-view label toggle (button[data-lang]) is still on the page")
        pg.click("#btn-reset2")
        pg.wait_for_timeout(1500)
        pg.wait_for_function("!window.__VLONTO_METRICS.flying", timeout=T_(20000))    # M.flying: the reset flight has ended
        cam = stable_value(pg, "() => window.VLApp.camera()")
        r0 = (pg.evaluate(JS_CALLOUTS) or {}).get("runs", 0)
        set_lang(c, pg, "vi")
        pg.wait_for_function("window.__VLONTO_METRICS.labelsLang === 'vi'", timeout=T_(15000))
        co = wait_callouts(pg, r0)
        lines = json.dumps(pg.evaluate("() => window.VLApp.labelLines('vlo:Article')"), ensure_ascii=False)
        if "Điều" not in lines or "Article" in lines:
            raise RuntimeError(f"vlo:Article call-out in VI: {lines}")
        faults = callout_faults(co)
        if faults:
            raise RuntimeError("call-outs in VI: " + "; ".join(faults))
        cam2 = pg.evaluate("() => window.VLApp.camera()")
        if cam2 != cam:
            raise RuntimeError(f"the language switch moved the camera: {cam} -> {cam2}")
        legend = pg.evaluate("document.getElementById('legend').textContent") if not c.mobile else ""
        if not c.mobile and ("Văn bản" not in legend or "Work" in legend):
            raise RuntimeError(f"legend in VI: {legend[:200]}")
        m = M()
        shot = c.shot(pg, "ontology3d_labels_vi")
        r1 = (pg.evaluate(JS_CALLOUTS) or {}).get("runs", 0)
        set_lang(c, pg, "envi")
        pg.wait_for_function("window.__VLONTO_METRICS.labelsLang === 'envi'", timeout=T_(15000))
        wait_callouts(pg, r1)
        back = json.dumps(pg.evaluate("() => window.VLApp.labelLines('vlo:Article')"), ensure_ascii=False)
        if "Điều" not in back or "Article" not in back:
            raise RuntimeError(f"vlo:Article call-out back in EN–VI: {back}")
        return {"labels_shown": m.get("labelsShown"), "labels_hidden": m.get("labelsHidden"), "vi_lines": lines, "envi_lines": back,
                "callouts_vi": callout_summary(co), "shot": shot}
    check("header language switch: call-outs and legend in VI with the camera kept, back to EN–VI; no per-view label toggle", labels_vi)

    def png():
        n = pg.evaluate("window.VLApp.exportPng()")
        if n < 20000:
            raise RuntimeError(f"PNG data URL too small ({n})")
        return {"png_data_url_chars": n}
    check("PNG export", png)

    def fps():
        f = pg.evaluate("ms => window.VLApp.measureFps(ms)", 3000)
        return {"fps": f, "renderer": M().get("webglRenderer")}
    check("frame rate (SwiftShader)", fps)
    res["log"] = log
    ctx.close()
    return res


def t_network(c: Ctx):
    res = {"test": "network-3d", "checks": []}
    ctx, pg, log = c.open("network-3d.html", ready_timeout=T_(240000))
    M = lambda: pg.evaluate("window.__VLONTO_METRICS")
    sel = "#net-search-m" if c.mobile else "#net-search"

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": fail_details(e, c, pg, name), "s": round(time.time() - t0, 2)})

    m0 = M()
    res["dataset_default"] = m0.get("dataset")
    res["ready_fps"] = m0.get("fps")

    def citation_label():
        info = pg.evaluate("""() => {
            const lab = document.querySelector('#edge-toggles input[data-edge=citation]').closest('label');
            const note = document.getElementById('citation-note');
            const kg = ((window.VLONTO || {}).site_meta || {}).kg_counts || {};
            return {label: lab.textContent.replace(/\\s+/g, ' ').trim(), title: lab.getAttribute('title'),
                    note: note ? note.textContent : null, kg: kg.citation_links || null, kg_article: kg.citation_links_article_level || null};
        }""")
        kg = info["kg"]
        if "document pairs" not in info["label"] or not kg or f"{kg:,}" not in (info["note"] or "") or f"{kg:,}" not in (info["title"] or ""):
            raise RuntimeError(f"citation toggle label/note/tooltip: {info}")
        # picture of the link toggles with the note (inside the Filters drawer on phones)
        if c.mobile:
            pg.click("#btn-side-m")
            pg.wait_for_timeout(500)
        p = c.out / "shots" / f"network3d_link_toggles__{c.mode}__{c.vp[0]}x{c.vp[1]}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        pg.locator("#edge-toggles").screenshot(path=str(p))
        no_hscroll(c, pg, "link toggles with the citation note")
        if c.mobile:
            pg.click("#btn-side-m")
            pg.wait_for_timeout(400)
        info["shot"] = str(p.relative_to(c.out))
        return info
    check("citation toggle says document pairs and relates them to the KG citation links", citation_label)

    def search():
        pg.fill(sel, "45/2019/QH14")
        lst = "#net-suggest-m" if c.mobile else "#net-suggest"
        pg.wait_for_selector(lst + " li[role=option]", timeout=T_(15000))
        first = pg.inner_text(lst + " li[role=option]").split("\n")[0]
        pg.press(sel, "Enter")
        panel_has(pg, "Bộ luật Lao động")
        pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '333670'", timeout=T_(60000))
        panel_has(pg, "10/2012/QH13", "Replacement chain")
        no_hscroll(c, pg, "document panel open")
        pg.wait_for_timeout(1500)
        # Read the panel through textContent: innerText applies the CSS text-transform of the uppercase section headings.
        info = pg.evaluate("""() => {
            const p = document.getElementById('panel');
            const hs = [...p.querySelectorAll('h3')];
            const h = hs.find(e => e.textContent.trim() === 'Replacement chain');
            const box = h ? h.nextElementSibling : null;
            return {chain: box ? box.textContent.replace(/\\s+/g, ' ').trim() : null,
                    sections: hs.map(e => e.textContent.trim()),
                    title: (p.querySelector('h2') || {}).textContent || null};
        }""")
        if not info["chain"] or "10/2012/QH13" not in info["chain"] or "45/2019/QH14" not in info["chain"]:
            raise RuntimeError("replacement chain missing or incomplete: %r" % (info["chain"],))
        # change-kind headings carry the relation name in lower case ('replaces (1)'); CSS shows them in capitals
        if not any(s.lower().startswith("replaces") for s in info["sections"]):
            raise RuntimeError("no 'Replaces' section in the panel: %r" % (info["sections"],))
        m = M()
        shot = c.shot(pg, "network3d_search_45_2019")
        return {"first_suggestion": first, "selected": m.get("selected"), "title": info["title"], "chain": info["chain"],
                "sections": info["sections"][:8], "ego_hop1": m.get("egoHop1"), "ego_edges": m.get("egoEdges"),
                "labels_shown": m.get("labelsShown"), "shot": shot}
    check("search 45/2019/QH14 -> panel: Bộ luật Lao động + replacement chain (10/2012/QH13)", search)

    def chain_click():
        pg.click("#panel button.linkish[data-doc='142187']")
        panel_has(pg, "10/2012/QH13")
        pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '142187'", timeout=T_(30000))
        txt = pg.evaluate("document.getElementById('panel').innerText")
        warn = "No longer in force" in txt or "Superseded" in txt
        if not warn:
            raise RuntimeError("no validity warning for the 2012 Labour Code")
        return {"warning_shown": warn, "shot": c.shot(pg, "network3d_chain_2012")}
    check("click 10/2012/QH13 in the chain -> panel with validity warning", chain_click)

    def filters():
        pg.keyboard.press("Escape")
        if c.mobile:
            pg.click("#btn-side-m")
        before = pg.inner_text("#status")
        # the status line ("N documents · M links shown · F fps") changes once the filtered scene is rebuilt,
        # about one frame later; at ~1 fps on SwiftShader that can take longer than a fixed pause
        counts_differ = "b => document.getElementById('status').innerText.split('\\u00b7')[0].trim() !== b.split('\\u00b7')[0].trim()"
        pg.evaluate("() => { const e = document.getElementById('y-from'); e.value = 2015; e.dispatchEvent(new Event('input', {bubbles: true})); }")
        try:
            pg.wait_for_function(counts_differ, arg=before, timeout=T_(15000))
        except Exception:
            pass
        after = pg.inner_text("#status")
        pg.click("[data-color=type]")
        pg.wait_for_timeout(500)
        legend = pg.inner_text("#legend") if pg.is_visible("#legend") else ""
        if c.mobile:
            pg.click("#btn-side-m")
        shot = c.shot(pg, "network3d_filtered")
        pg.evaluate("() => { const e = document.getElementById('y-from'); e.value = e.min; e.dispatchEvent(new Event('input', {bubbles: true})); }")
        try:
            pg.wait_for_function("b => !(" + counts_differ + ")(b)", arg=before, timeout=T_(15000))
        except Exception:
            pass
        if before.split("\u00b7")[0].strip() == after.split("\u00b7")[0].strip():
            raise RuntimeError("year filter did not change the status line")
        return {"before": before, "after": after, "legend": legend[:120], "shot": shot}
    check("issue-year filter and colour by type", filters)

    def lang_switch():
        # the header switch re-renders the details panel, the legend and the call-outs in VI and keeps the selection and
        # the camera; the per-view label toggle is gone; EN–VI comes back with the v1 headings
        pg.evaluate("() => window.VLApp.selectById('333670')")
        pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '333670' && window.__VLONTO_METRICS.chainTraceDocs >= 2", timeout=T_(120000))
        # the selection flies the camera; at ~1 fps (SwiftShader) two reads 400 ms apart can match mid-flight, so wait for its end
        pg.wait_for_function("!window.__VLONTO_METRICS.flying", timeout=T_(120000))
        cam = stable_value(pg, "() => window.VLApp.camera()")
        r0 = (pg.evaluate(JS_CALLOUTS) or {}).get("runs", 0)
        set_lang(c, pg, "vi")
        pg.wait_for_function("window.__VLONTO_METRICS.labelsLang === 'vi'", timeout=T_(30000))
        info = pg.evaluate("""() => ({ heads: Array.from(document.querySelectorAll('#panel h3')).map(e => e.textContent.trim()),
            legend: document.getElementById('legend').textContent, selected: window.VLApp.state().selected, camera: window.VLApp.camera(),
            toggles: document.querySelectorAll('button[data-lang]').length })""")
        heads = " | ".join(info["heads"])
        if "Chuỗi thay thế" not in heads or "Replacement chain" in heads:
            raise RuntimeError(f"panel headings in VI: {heads[:300]}")
        if not c.mobile and (re.search(r"\b(Traced|In force|Legend)\b", info["legend"]) or not re.search("[ăâđêôơưạ-ỹ]", info["legend"], re.I)):
            raise RuntimeError(f"legend in VI: {info['legend'][:200]}")
        if info["selected"] != "333670" or info["camera"] != cam:
            raise RuntimeError(f"the switch lost the selection or moved the camera: {info['selected']}, {cam} -> {info['camera']}")
        if info["toggles"]:
            raise RuntimeError("the per-view label toggle (button[data-lang]) is still on the page")
        co = wait_callouts(pg, r0, "doc-333670", timeout=T_(60000))
        faults = callout_faults(co)
        if faults:
            raise RuntimeError("call-outs in VI: " + "; ".join(faults))
        shot = c.shot(pg, "network3d_lang_vi")
        set_lang(c, pg, "envi")
        pg.wait_for_function("window.__VLONTO_METRICS.labelsLang === 'envi'", timeout=T_(30000))
        panel_has(pg, "Replacement chain", "Bộ luật Lao động")
        return {"headings_vi": info["heads"][:8], "callouts_vi": callout_summary(co), "shot": shot}
    check("header language switch: panel, legend and call-outs in VI, selection and camera kept; back to EN–VI", lang_switch)

    def fps_default():
        f = pg.evaluate("ms => window.VLApp.measureFps(ms)", 3000)
        return {"dataset": M().get("dataset"), "fps": f, "edges": M().get("edges"), "renderer": M().get("webglRenderer")}
    check("frame rate, default dataset (SwiftShader)", fps_default)

    def fps_other():
        other = "lite" if M().get("dataset") == "full" else "full"
        if c.mobile:
            pg.click("#btn-side-m")
        pg.click(f"[data-ds={other}]")
        if c.mobile:
            pg.click("#btn-side-m")
        pg.wait_for_function("ds => window.__VLONTO_METRICS.dataset === ds", arg=other, timeout=T_(180000))
        pg.wait_for_timeout(1000)
        f = pg.evaluate("ms => window.VLApp.measureFps(ms)", 3000)
        m = M()
        return {"dataset": other, "fps": f, "nodes": m.get("nodes"), "edges": m.get("edges"), "load_ms": m.get("loadMs"), "build_ms": m.get("buildMs"),
                "shot": c.shot(pg, "network3d_" + other)}
    check("frame rate, other dataset (SwiftShader)", fps_other)
    res["log"] = log
    ctx.close()
    return res


def t_sparql(c: Ctx, examples):
    res = {"test": "sparql", "checks": []}
    ctx, pg, log = c.open("sparql.html")

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": fail_details(e, c, pg, name), "s": round(time.time() - t0, 2)})

    def selftest():
        r = pg.evaluate("window.VLApp.selfTest()")
        rows = [{"title": x["title"], "expected": x["expected"], "got": x["got"], "ok": x["ok"]} for x in r["rows"]]
        if r["pass"] != r["total"] or r["total"] != len(examples):
            raise RuntimeError(f"{r['pass']} of {r['total']} examples match rows_on_core")
        return {"pass": r["pass"], "total": r["total"], "rows": rows, "construct": r["construct"], "shot": c.shot(pg, "sparql_selftest")}
    check("10 examples return rows_on_core", selftest)

    def construct():
        pg.click("[data-ex=c0]")
        pg.wait_for_function("window.__VLONTO_METRICS.constructDrawn && window.__VLONTO_METRICS.constructDrawn.nodes > 0", timeout=T_(60000))
        pg.wait_for_timeout(2500)
        m = pg.evaluate("window.__VLONTO_METRICS")
        pg.evaluate("document.getElementById('graph-wrap').scrollIntoView()")
        pg.wait_for_timeout(500)
        return {"triples": m["lastQuery"]["count"], "drawn": m["constructDrawn"], "shot": c.shot(pg, "sparql_construct_3d")}
    check("CONSTRUCT example -> 3D view", construct)

    def error():
        lq = pg.evaluate("window.VLApp.run('SELEC ?x WHERE { ?x ?p ?o }', 'core')")
        msg = pg.inner_text("#status")
        if not lq.get("error") or "line 1" not in msg:
            raise RuntimeError(f"no clear syntax error: {msg}")
        return {"message": msg}
    check("syntax error message with line and column", error)

    def construct_scope():
        # release v1: a CONSTRUCT over the ontology shows no term populated from v2 (js/common.js VL.scopeQuads)
        q = "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nCONSTRUCT { ?c rdfs:subClassOf ?d } WHERE { ?c rdfs:subClassOf ?d }"
        lq = pg.evaluate("(q) => window.VLApp.run(q, 'ontology')", q)
        pg.wait_for_function("window.__VLONTO_METRICS.constructDrawn && window.__VLONTO_METRICS.constructDrawn.nodes > 0", timeout=T_(60000))
        ids = pg.evaluate("window.VLApp.constructNodes().map(n => n.id)")
        court = [i for i in ids if any(w in i for w in ("Court", "Judicial", "Judgment", "Precedent", "CaseCategory", "InstanceLevel"))]
        status = pg.inner_text("#status")
        if lq.get("error") or not lq.get("hiddenLater") or court or "not shown" not in status:
            raise RuntimeError(f"CONSTRUCT scope: hidden {lq.get('hiddenLater')}, court nodes {court[:6]}, status {status[:200]!r}, error {lq.get('error')}")
        return {"triples": lq.get("count"), "not_shown": lq.get("hiddenLater"), "nodes_drawn": len(ids)}
    check("release v1: CONSTRUCT results leave out the terms populated from v2", construct_scope)

    def csv():
        # example s1's 27 rows hold on the core subset; the scope check before this one leaves the ontology selected
        pg.evaluate("document.getElementById('dataset').value = 'core'")
        pg.evaluate("window.VLApp.runExample('s1')")
        pg.wait_for_function("window.__VLONTO_METRICS.lastQuery && window.__VLONTO_METRICS.lastQuery.count === 27", timeout=T_(30000))
        with pg.expect_download(timeout=T_(20000)) as d:
            pg.click("#btn-csv")
        dl = d.value
        path = dl.path()
        data = Path(path).read_bytes()
        text = data.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l]
        if lines[0] != "area,laws" or len(lines) != 28:
            raise RuntimeError(f"unexpected CSV: {lines[:2]} ({len(lines)} lines)")
        return {"filename": dl.suggested_filename, "lines": len(lines), "header": lines[0], "first": lines[1], "bom": data[:3] == b"\xef\xbb\xbf"}
    check("CSV export of a SELECT result", csv)

    def know_full():
        # 'Good to know': the full graph's size comes from the data (VLONTO.stats.rdf_triples), in the mode's number
        # format (EN 6,963,753 / VI 6.963.753), never the 0.1.0 figure (31.5 million); the syntax error reads in VI too
        n = pg.evaluate("() => (window.VLONTO.stats || {}).rdf_triples || (((window.VLONTO.site_meta || {}).rdf_dump || {}).triples)")
        en = pg.evaluate("document.getElementById('sq-know-full').textContent")
        if not n or f"{n:,}" not in en or "31.5" in en:
            raise RuntimeError(f"good-to-know full graph: {n} / {en!r}")
        set_lang(c, pg, "vi")
        vi = pg.evaluate("document.getElementById('sq-know-full').textContent")
        lq = pg.evaluate("window.VLApp.run('SELEC ?x WHERE { ?x ?p ?o }', 'core')")
        msg = pg.evaluate("document.getElementById('status').textContent")
        set_lang(c, pg, "envi")
        if f"{n:,}".replace(",", ".") not in vi or "31,5" in vi:
            raise RuntimeError(f"VI number format: {vi!r}")
        if not lq.get("error") or "dòng 1" not in msg:
            raise RuntimeError(f"VI syntax error message: {msg!r}")
        return {"triples": n, "en": en.strip()[:160], "vi": vi.strip()[:160], "vi_error": msg[:160]}
    check("good to know: the full graph's size from the data (EN 6,963,753 / VI 6.963.753); the syntax error in VI", know_full)
    res["log"] = log
    ctx.close()
    return res


def t_dashboard(c: Ctx, stats):
    res = {"test": "dashboard", "checks": []}
    ctx, pg, log = c.open("dashboard.html")
    # texts follow the language mode (html[data-lang]: en, vi, envi = the default, which shows pairs as "vi · en")
    V2_NOTE = ("Court decisions join in v2.", "Bản án và quyết định của tòa án sẽ có trong v2.")
    page_lang = lambda p: p.evaluate("document.documentElement.getAttribute('data-lang') || 'en'")  # noqa: E731

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": fail_details(e, c, pg, name), "s": round(time.time() - t0, 2)})

    def totals():
        # with the filters at their defaults every KPI and chart total must equal the KG totals (undated records included)
        t = pg.evaluate("window.VLApp.dashTotals()")
        kg, ch, k = t["kg"], t["charts"], t["kpis"]
        want = {"c-type-year": kg["documents"], "c-validity": kg["documents"], "c-ranks": kg["documents"], "c-areas": kg["documents"],
                "c-changes": kg["change_events"], "c-qa": kg["legal_questions"], "c-terms": kg["legal_terms"], "c-news": kg["news_articles"]}
        bad = {cid: (round(ch[cid]), w) for cid, w in want.items() if round(ch[cid]) != w}
        if k["docs"] != kg["documents"]:
            bad["KPI documents"] = (k["docs"], kg["documents"])
        if k["changes"] != kg["change_events"]:
            bad["KPI change relations"] = (k["changes"], kg["change_events"])
        part = k["inForce"] + k["notYet"] + k["gone"] + k["unknown"]
        if part != k["docs"]:
            bad["KPI validity partition"] = (part, k["docs"])
        if any(t["undatedLeftOut"].values()):
            bad["undated left out at defaults"] = t["undatedLeftOut"]
        if bad:
            raise RuntimeError(f"totals differ from the KG with default filters: {bad}")
        return {"charts": {cid: round(v) for cid, v in ch.items()}, "kpis": k, "kg": kg, "caption": t["caption"]}
    check("unfiltered KPIs and chart totals equal the KG totals", totals)

    def no_courts():
        # release v1: no court chart, KPI or citing source, whether or not the data files still carry court fields
        d = pg.evaluate("""() => ({ charts: Array.from(document.querySelectorAll('.chart')).map(e => e.id),
            tabs: Array.from(document.querySelectorAll('#tabs-docs [data-src], #tabs-arts [data-src]')).map(b => b.getAttribute('data-src')),
            kpis: Array.from(document.querySelectorAll('#kpis-all .kpi .k, #kpis-sel .kpi .k')).map(e => e.textContent),
            note: (document.querySelector('.v2-note') || {}).textContent || '',
            release: Array.from(document.querySelectorAll('[data-vl-release]')).map(e => e.textContent),
            text: document.querySelector('main').textContent.toLowerCase() })""")
        bad = [x for x in d["charts"] if x.startswith("c-dec")] + [x for x in d["tabs"] if "court" in x] + [k for k in d["kpis"] if "court" in k.lower()]
        words = [w for w in ("anle", "cbba", "toaan", "precedent", "court level", "applied provision") if w in d["text"]]
        # the v2 note follows the language mode: English, Vietnamese, or the pair "Vietnamese · English" (EN–VI, the default)
        if bad or words or not any(s in d["note"] for s in V2_NOTE) or len(d["charts"]) != 10 or set(d["release"]) != {"VLOnto v1"}:
            raise RuntimeError(f"court content or release label: bad {bad}, words {words}, note {d['note']!r}, charts {len(d['charts'])}, "
                               f"release {d['release']}")
        return {"charts": len(d["charts"]), "tabs": d["tabs"], "kpis": d["kpis"], "note": d["note"], "release": d["release"]}
    check("release v1: no court chart, KPI or citing source; the v2 note; the release named VLOnto v1", no_courts)

    def year_note():
        # a year range leaves undated records out and says so; reset brings the undated buckets back
        last2 = "echarts.getInstanceByDom(document.getElementById('{}')).getOption().xAxis[0].data.slice(-2)"
        pg.select_option("#f-y0", "2015")
        pg.wait_for_timeout(500)
        t = pg.evaluate("window.VLApp.dashTotals()")
        cap, lo = t["caption"], t["undatedLeftOut"]
        subs = pg.evaluate("['sub-type-year', 'sub-changes'].map(id => document.getElementById(id).textContent)")
        cats = {cid: pg.evaluate(last2.format(cid)) for cid in ("c-type-year", "c-changes")}
        shot = c.shot(pg, "dashboard_year_range")
        pg.click("#f-reset")
        pg.wait_for_timeout(500)
        t2 = pg.evaluate("window.VLApp.dashTotals()")
        cats2 = {cid: pg.evaluate(last2.format(cid)) for cid in ("c-type-year", "c-changes")}
        problems = []
        if not (lo["docs"] > 0 and lo["changes"] > 0):
            problems.append(f"undated counts {lo}")
        # captions are sentences in the page's language (English in EN and EN–VI); numbers in its format (VI: 1.234)
        vi = page_lang(pg) == "vi"
        for key, words, sub in (("docs", "without an issue year", 0), ("changes", "without an effective date", 1)):
            n = lo[key]
            num = f"{n:,}".replace(",", ".") if vi else f"{n:,}"
            if n and (num not in cap or (not vi and words not in cap)):
                problems.append(f"filter caption lacks the {key}: {cap!r}")
            if n and (num not in subs[sub] or (not vi and "leaves out" not in subs[sub])):
                problems.append(f"chart caption lacks the {key}: {subs[sub]!r}")
        if any(v[-1] in ("no year", "no date") for v in cats.values()):
            problems.append(f"undated bucket still drawn with a year range: {cats}")
        if [v[-1] for v in cats2.values()] != ["no year", "no date"]:
            problems.append(f"undated buckets missing after reset: {cats2}")
        if any(t2["undatedLeftOut"].values()):
            problems.append("undated records still left out after reset")
        if problems:
            raise RuntimeError("; ".join(problems))
        return {"left_out": lo, "caption": cap, "chart_captions": subs, "last_categories_with_range": cats,
                "last_categories_after_reset": cats2, "shot": shot}
    check("a year range states which undated records it leaves out", year_note)

    def filters():
        s0 = pg.evaluate("window.VLApp.dashState()")
        # the option for laws by its type code (its text follows the language mode: Law, Luật, Luật · Law)
        law_val = pg.evaluate("document.querySelector('#f-type option[data-code=\"L\"]').value")
        pg.select_option("#f-type", law_val)
        pg.wait_for_timeout(500)
        s1 = pg.evaluate("window.VLApp.dashState()")
        want = stats["documents_by_type"].get("Luật")
        if s1["docs"] != want or s1["typeYearChartSum"] == s0["typeYearChartSum"]:
            raise RuntimeError(f"type filter: docs {s1['docs']} (want {want}); chart sum {s0['typeYearChartSum']} -> {s1['typeYearChartSum']}")
        shot = c.shot(pg, "dashboard_filter_law")
        area = pg.evaluate("document.querySelector('#f-area option:nth-child(2)').value")
        pg.select_option("#f-area", area)
        pg.wait_for_timeout(400)
        s2 = pg.evaluate("window.VLApp.dashState()")
        pg.select_option("#f-y0", "2015")
        pg.wait_for_timeout(400)
        s3 = pg.evaluate("window.VLApp.dashState()")
        pg.click("#f-reset")
        pg.wait_for_timeout(400)
        s4 = pg.evaluate("window.VLApp.dashState()")
        if not (s2["docs"] <= s1["docs"] and s3["docs"] <= s2["docs"] and s4["docs"] == stats["documents"]):
            raise RuntimeError(f"filters not monotone or reset failed: {s1['docs']} {s2['docs']} {s3['docs']} {s4['docs']}")
        return {"all": s0, "law": s1, "law_area": s2, "law_area_2015": s3, "reset": s4, "shot": shot}
    check("type / area / year filters change chart data and counts", filters)

    def click_area():
        pg.evaluate("document.getElementById('c-areas').scrollIntoView({block: 'center'})")
        pg.wait_for_timeout(400)
        before = pg.evaluate("window.__VLONTO_METRICS.filters.area")
        # middle bar of the chart, located with the ECharts coordinate API (not covered by the sticky filter bar)
        pt = pg.evaluate("""(() => {
            const el = document.getElementById('c-areas'), ch = echarts.getInstanceByDom(el), opt = ch.getOption();
            const data = opt.series[0].data, i = Math.floor(data.length / 2), d = data[i];
            const v = (d !== null && typeof d === 'object') ? (Array.isArray(d.value) ? d.value[0] : d.value) : d;
            const p = ch.convertToPixel({seriesIndex: 0}, [Number(v) / 2, i]), r = el.getBoundingClientRect();
            return {x: r.left + p[0], y: r.top + p[1], i: i, n: data.length};
        })()""")
        pg.mouse.click(pt["x"], pt["y"])
        pg.wait_for_timeout(500)
        after = pg.evaluate("window.__VLONTO_METRICS.filters.area")
        pg.click("#f-reset")
        if after == before:
            raise RuntimeError("clicking a bar did not set the area filter")
        return {"area_before": before, "area_after": after, "click": pt}
    if not c.mobile:
        check("click an area bar -> area filter", click_area)
    res["log"] = log
    ctx.close()
    return res


def t_simple(c: Ctx, root: Path):
    out = []
    # about (the overview; the landing page index.html is the 3D playground)
    ctx, pg, log = c.open("about.html")
    nav = pg.evaluate("Array.from(document.querySelectorAll('#vl-nav a')).map(a => a.getAttribute('href'))")
    tools = pg.evaluate("Array.from(document.querySelectorAll('#tools a')).map(a => a.getAttribute('href'))")
    internal = [h for h in nav if not h.startswith(("http://", "https://"))]
    external = [h for h in nav if h.startswith(("http://", "https://"))]
    missing = [h for h in set(internal + tools) if not (root / h.split('#')[0]).exists()]
    card = pg.evaluate("""() => { const c = document.querySelector('#paper .paper-card, #paper [data-vl-paper]');
        return { title: (document.querySelector('#paper .paper-title') || {}).textContent || '', copy: !!document.querySelector('#paper [data-copy-bib]'),
                 bib: ((document.querySelector('#paper pre.bibtex') || {}).textContent || '').slice(0, 30), brand: (document.querySelector('.vl-brand') || {}).getAttribute('href') }; }""")
    rel = pg.evaluate("""() => ({ release: Array.from(document.querySelectorAll('[data-vl-release]')).map(e => e.textContent),
        version: Array.from(document.querySelectorAll('[data-vl-version]')).map(e => e.textContent),
        note: (document.getElementById('numbers-note') || {}).textContent || '', footer: (document.querySelector('.vl-footer .meta') || {}).textContent || '',
        kpis: Array.from(document.querySelectorAll('#kpis .kpi .k')).map(e => e.textContent),
        sources: Array.from(document.querySelectorAll('#sources tr td:first-child a')).map(a => a.textContent),
        v2: (document.querySelector('.v2-note') || {}).textContent || '', bib: (document.getElementById('bibtex') || {}).textContent || '' })""")
    four = ["thuvienphapluat-vn-vbpl", "thuvienphapluat-vn-hdpl", "thuvienphapluat-vn-tnpl", "thuvienphapluat-vn-htpl"]
    # the v2 note follows the language mode: English, Vietnamese, or "Vietnamese · English" (EN–VI, the default)
    V2_NOTE = ("Court decisions join in v2.", "Bản án và quyết định của tòa án sẽ có trong v2.")
    out.append({"test": "about", "checks": [
        {"name": "navigation (3D Ontology = index.html first, 9 pages incl. traces.html + Paper) and tool cards link to existing pages",
         "pass": len(internal) == 9 and internal[0] == "index.html" and internal[-1] == "about.html" and "traces.html" in internal
                 and external == [PAPER_URL] and not missing,
         "details": {"nav": nav, "tools": tools, "missing": missing}},
        {"name": "about.html renders the paper card with BibTeX and Copy; the logo links to index.html",
         "pass": card["title"].startswith("Vietnamese Legal Ontology") and card["copy"] and card["bib"].startswith("@misc{bui2026vietnamese") and card["brand"] == "index.html",
         "details": card},
        {"name": "release v1: named VLOnto v1 (version 1.0.0), four source datasets, no court KPI, the v2 note",
         "pass": set(rel["release"]) == {"VLOnto v1"} and set(rel["version"]) == {"1.0.0"}
                 and rel["note"].startswith(("VLOnto v1 (this release)", "VLOnto v1 (bản phát hành này)"))
                 and "VLOnto v1" in rel["footer"] and rel["sources"] == four and not [k for k in rel["kpis"] if "court" in k.lower()]
                 and any(s in rel["v2"] for s in V2_NOTE) and "version = {1.0.0}" in rel["bib"],
         "details": rel}], "log": log})
    ctx.close()
    # the old playground address forwards to index.html, keeping the #hash (deep link to a class). Opened from about.html
    # with wait_until=commit: the stub replaces itself while it loads, which would interrupt a goto waiting for 'load'.
    ctx, pg, log = c.open("about.html")
    try:
        pg.goto(c.url("ontology-3d.html#class=vlo:Article"), wait_until="commit", timeout=T_(60000))
        pg.wait_for_url(re.compile(r".*/index\.html(\?[^#]*)?#class=vlo:Article$"), timeout=T_(30000))
        pg.wait_for_function("window.__VLONTO_READY === true", timeout=T_(180000))
        pg.wait_for_function("window.__VLONTO_METRICS.selected === 'vlo:Article'", timeout=T_(60000))
        red = {"pass": True, "details": {"landed": pg.url[-60:], "selected": pg.evaluate("window.__VLONTO_METRICS.selected")}}
    except Exception as e:  # noqa
        red = {"pass": False, "details": {"error": str(e)[:400], "url": pg.url[-80:]}}
    out.append({"test": "redirect", "checks": [dict(name="ontology-3d.html#class=vlo:Article lands on index.html with the hash (class selected)", **red)], "log": log})
    ctx.close()
    # playbook
    out.append(t_playbook(c))
    # downloads
    ctx, pg, log = c.open("downloads.html")
    rows = pg.evaluate("""Array.from(document.querySelectorAll('table.files tbody tr')).map(tr => {
        const a = tr.querySelector('a.file-link'); const h = tr.querySelector('code.hash');
        return {href: a ? a.getAttribute('href') : (tr.querySelector('td') || {}).textContent, hash: h ? h.getAttribute('title') : null};
      }).filter(r => r.hash)""")
    bad = []
    for r in rows:
        p = root / r["href"].strip()
        if not p.exists():
            bad.append({"file": r["href"], "problem": "missing"})
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h != r["hash"]:
            bad.append({"file": r["href"], "problem": "sha256 mismatch"})
    out.append({"test": "downloads", "checks": [{"name": "every listed file exists and its sha256 matches", "pass": bool(rows) and not bad,
                                                 "details": {"files_checked": len(rows), "problems": bad[:20]}}], "log": log})
    ctx.close()
    # ontology docs iframe
    ctx, pg, log = c.open("ontology.html")
    frame_ok = pg.evaluate("window.__VLONTO_METRICS.iframe === true")
    n_frames = len(pg.frames)
    out.append({"test": "ontology", "checks": [{"name": "pyLODE documentation iframe loads", "pass": frame_ok and n_frames >= 2,
                                                "details": {"frames": n_frames}}], "log": log})
    ctx.close()
    return out


def t_playbook(c: Ctx):
    """The real playbook page with the Playbook track's data/playbook_html.js: content, figures, tables and code blocks
    that stay inside the viewport (wide ones scroll inside themselves), and contents links that land below the header."""
    res = {"test": "playbook", "checks": []}
    ctx, pg, log = c.open("playbook.html")

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": fail_details(e, c, pg, name), "s": round(time.time() - t0, 2)})

    def content():
        pb = pg.evaluate("window.__VLONTO_METRICS.playbook")
        if not (pb and pb.get("present") and pb.get("headings", 0) > 20):
            raise RuntimeError(f"playbook not rendered: {pb}")
        imgs = pg.evaluate("""Array.from(document.querySelectorAll('article.prose img')).map(i => ({alt: (i.alt || '').slice(0, 60),
            ok: i.complete && i.naturalWidth > 0, w: Math.round(i.getBoundingClientRect().width)}))""")
        bad = [i for i in imgs if not i["ok"]]
        if bad:
            raise RuntimeError(f"figures that did not decode: {bad}")
        return {"playbook": pb, "figures": len(imgs), "figure_widths": [i["w"] for i in imgs]}
    check("playbook renders with its figures", content)

    def blocks():
        r = pg.evaluate("""() => {
            const W = document.documentElement.clientWidth, out = {tables: 0, pre: 0, scrolling: 0, outside: []};
            const boxes = [...document.querySelectorAll('article.prose .table-wrap')].map(e => ['table', e])
                .concat([...document.querySelectorAll('article.prose pre')].map(e => ['pre', e]));
            for (const [k, e] of boxes) {
                out[k === 'table' ? 'tables' : 'pre']++;
                const r = e.getBoundingClientRect();
                if (e.scrollWidth > e.clientWidth + 1) out.scrolling++;
                if (r.left < -1 || r.right > W + 1) out.outside.push({kind: k, left: Math.round(r.left), right: Math.round(r.right), text: e.textContent.slice(0, 50)});
            }
            out.viewport = W;
            return out; }""")
        if r["outside"]:
            raise RuntimeError(f"blocks outside the viewport: {r['outside'][:5]}")
        # element shots of the widest tables and the longest code blocks, for review
        shots = []
        idx = pg.evaluate("""() => {
            const t = [...document.querySelectorAll('article.prose .table-wrap')].map((e, i) => [e.scrollWidth, i]).sort((a, b) => b[0] - a[0]).slice(0, 2).map(x => x[1]);
            const p = [...document.querySelectorAll('article.prose pre')].map((e, i) => [e.textContent.length, i]).sort((a, b) => b[0] - a[0]).slice(0, 2).map(x => x[1]);
            return {t, p}; }""")
        for kind, sel, ids in (("table", "article.prose .table-wrap", idx["t"]), ("code", "article.prose pre", idx["p"])):
            for j, i in enumerate(ids):
                p = c.out / "shots" / f"playbook_{kind}{j + 1}__{c.mode}__{c.vp[0]}x{c.vp[1]}.png"
                p.parent.mkdir(parents=True, exist_ok=True)
                pg.locator(sel).nth(i).screenshot(path=str(p))
                shots.append(str(p.relative_to(c.out)))
        r["shots"] = shots
        return r
    check("tables and code blocks stay inside the viewport (wide ones scroll inside)", blocks)

    def toc():
        pg.evaluate("() => window.scrollTo(0, 0)")
        if c.mobile:
            pg.click("nav.toc summary")
            pg.wait_for_timeout(200)
        links = pg.evaluate("() => [...document.querySelectorAll('nav.toc li.l2 a')].map(a => a.getAttribute('href'))")
        if len(links) < 6:
            raise RuntimeError(f"only {len(links)} section links in the contents")
        target = links[5]
        pg.click(f"nav.toc a[href='{target}']")
        pg.wait_for_timeout(700)
        st = pg.evaluate("""(h) => { const e = document.getElementById(decodeURIComponent(h.slice(1))); const hd = document.querySelector('.vl-header');
            return {hash: location.hash, top: e ? Math.round(e.getBoundingClientRect().top) : null, header: hd ? Math.round(hd.getBoundingClientRect().bottom) : 0,
                    text: e ? e.textContent.slice(0, 60) : null}; }""", target)
        if st["hash"] != target or st["top"] is None or not (st["header"] - 2 <= st["top"] <= st["header"] + 80):
            raise RuntimeError(f"contents link {target} did not land below the header: {st}")
        st["shot"] = c.shot(pg, "playbook_toc_jump")
        return st
    check("contents link jumps to its section, below the sticky header", toc)
    res["log"] = log
    ctx.close()
    return res


PAPER_URL = "https://arxiv.org/abs/2611.11426"
PAPER_CITE = "Cite: Bui & Tran Minh (2026), arXiv:2611.11426"
PAPER_BIBTEX = ("@misc{bui2026vietnamese,\n"
                "  title         = {Vietnamese Legal Ontology: Every legal answer, traced to the article that grounds it},\n"
                "  author        = {Bui, Khac-Hoai Nam and Tran Minh, Quan},\n"
                "  year          = {2026},\n"
                "  eprint        = {2611.11426},\n"
                "  archivePrefix = {arXiv},\n"
                "  primaryClass  = {cs.CL},\n"
                "  url           = {https://arxiv.org/abs/2611.11426}\n"
                "}")
SITE_PAGES = ["index.html", "about.html", "network-3d.html", "sparql.html", "dashboard.html", "ontology.html",
              "playbook.html", "downloads.html", "traces.html"]
SCENES = ("index.html", "network-3d.html", "traces.html")       # pages with a full-screen WebGL scene
# traces.html in the page loops of the theme group (t_theme, t_paper, t_lang): the lite network with straight links
# (#ds=lite&curves=0; the lite network is what phones load) - those checks are about the theme, the links and the
# language, not the 40,816 documents, and the group runs close to its time limit on slow runners
PAGE_HASH = {"traces.html": "#ds=lite&curves=0"}


def loop_page(page):
    return page + PAGE_HASH.get(page, "")
JS_THEME = """() => { const r = document.documentElement, b = document.querySelector('.vl-header .vl-theme-btn'), M = window.__VLONTO_METRICS || {};
  let ls = null; try { ls = window.localStorage.getItem('vlonto.theme'); } catch (e) { ls = 'blocked'; }
  return { theme: r.getAttribute('data-theme'), pressed: b ? b.getAttribute('aria-pressed') : null, label: b ? b.getAttribute('aria-label') : null,
    title: b ? b.getAttribute('title') : null, stored: ls, source: M.themeSource, bodyBg: getComputedStyle(document.body).backgroundColor,
    sceneBg: getComputedStyle(r).getPropertyValue('--scene-bg').trim(), renders: M.themeRenders || 0, chartRenders: M.chartThemeRenders || 0,
    url: location.href }; }"""
# dominant colour of a PNG (data URL), decoded in the page: 6 bits per channel
JS_MODE = """async (src) => { const img = new Image(); img.src = src; await img.decode();
  const cv = document.createElement('canvas'); cv.width = img.naturalWidth; cv.height = img.naturalHeight;
  const cx = cv.getContext('2d', { willReadFrequently: true }); cx.drawImage(img, 0, 0);
  const d = cx.getImageData(0, 0, cv.width, cv.height).data, h = new Map(); let best = 0, n = 0;
  for (let i = 0; i < d.length; i += 4) { const k = ((d[i] >> 2) << 12) | ((d[i + 1] >> 2) << 6) | (d[i + 2] >> 2);
    const v = (h.get(k) || 0) + 1; h.set(k, v); if (v > n) { n = v; best = k; } }
  return { rgb: [((best >> 12) & 63) * 4 + 2, ((best >> 6) & 63) * 4 + 2, (best & 63) * 4 + 2], share: Math.round(1000 * n / (d.length / 4)) / 1000 }; }"""
JS_CHART = """() => { const el = document.getElementById('c-type-year'), inst = window.echarts && el && echarts.getInstanceByDom(el);
  if (!inst) return null; const o = inst.getOption(), ts = Array.isArray(o.textStyle) ? o.textStyle[0] : o.textStyle;
  return { text: ts && ts.color, legend: o.legend && o.legend[0] && o.legend[0].textStyle && o.legend[0].textStyle.color,
    axis: o.xAxis && o.xAxis[0] && o.xAxis[0].axisLabel && o.xAxis[0].axisLabel.color,
    tok: getComputedStyle(document.documentElement).getPropertyValue('--chart-fg').trim() }; }"""
NO_STORAGE = """(() => { try { Object.defineProperty(window, 'localStorage', { configurable: true,
  get() { throw new DOMException('storage is blocked', 'SecurityError'); } }); } catch (e) {} })();"""
NO_CLIPBOARD = """(() => { try { Object.defineProperty(Navigator.prototype, 'clipboard', { configurable: true, get() { return undefined; } }); } catch (e) {}
  document.execCommand = function () { return false; }; })();"""


def lum(rgb):
    def f(v):
        v = v / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])


def region_mode(pg, sel, w=480, h=300):
    """Dominant colour of the top-left part of an element as rendered (WebGL canvases included). The element is
    scrolled to the middle of the viewport first and the sample stays clear of the sticky header and the fixed footbar
    (both navy in either theme), so only the element itself is measured."""
    loc = pg.locator(sel).first
    loc.evaluate("e => e.scrollIntoView({ block: 'center', inline: 'nearest' })")
    pg.wait_for_timeout(300)
    box = loc.bounding_box()
    if not box:
        raise RuntimeError(f"{sel}: no box")
    bars = pg.evaluate("""() => { const h = document.querySelector('.vl-header'), f = document.querySelector('.vl-footbar');
        return { top: h ? h.getBoundingClientRect().bottom : 0, bottom: f && getComputedStyle(f).display !== 'none' ? f.getBoundingClientRect().top : innerHeight }; }""")
    x0, y0 = box["x"] + 2, max(box["y"] + 2, bars["top"] + 2)
    x1 = min(box["x"] + box["width"] - 2, x0 + w - 4)
    y1 = min(box["y"] + box["height"] - 2, bars["bottom"] - 2, y0 + h - 4)
    if x1 - x0 < 8 or y1 - y0 < 8:
        raise RuntimeError(f"{sel}: not visible between the header and the footbar ({box})")
    clip = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
    png = pg.screenshot(clip=clip)
    return pg.evaluate(JS_MODE, "data:image/png;base64," + base64.b64encode(png).decode())


def click_theme(pg, want):
    pg.locator(".vl-header .vl-theme-btn").click()
    pg.wait_for_function("(t) => document.documentElement.getAttribute('data-theme') === t", arg=want, timeout=T_(15000))


def nav_to(c, pg, href):
    """Follow a header navigation link like a visitor (the menu opens first on phones)."""
    if c.mobile:
        pg.locator(".vl-menu-btn").click()
        pg.wait_for_timeout(250)
    with pg.expect_navigation(wait_until="load", timeout=T_(120000)):
        pg.locator(f'#vl-nav a[href^="{href}"]').first.click()
    pg.wait_for_function("window.__VLONTO_READY === true", timeout=T_(180000))


def doc_frame(pg):
    for f in pg.frames:
        if "ontology/vlonto.html" in f.url:
            return f
    raise RuntimeError("pyLODE iframe not found")


def t_theme(c: Ctx):
    """Light and dark themes: the system setting is the default, the header toggle switches every page (3D scenes
    re-render their background, nodes and labels; charts re-render), the choice persists across pages and reloads
    (localStorage, or ?theme= on internal links where storage is not available), ?theme= forces a theme, a system
    change is followed until a choice is made, and the pyLODE iframe follows its page both ways."""
    res = {"test": "theme", "checks": []}
    logs = {"console_errors": [], "page_errors": [], "failed_requests": [], "external_requests": []}

    def merge(log):
        for k in logs:
            logs[k] += log.get(k, [])

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": {"error": str(e)[:1200]}, "s": round(time.time() - t0, 2)})

    def extras(pg, page):
        x = {}
        if page in SCENES:
            x["canvas"] = region_mode(pg, "#canvas-host")
        if page == "sparql.html":
            x["construct"] = region_mode(pg, "#graph-view")
        if page == "dashboard.html":
            x["chart"] = pg.evaluate(JS_CHART)
        if page == "ontology.html":
            f = doc_frame(pg)
            x["frame"] = f.evaluate("() => ({ theme: document.documentElement.getAttribute('data-theme'), bg: getComputedStyle(document.body).backgroundColor })")
        return x

    def compare(page, a, b, want):
        """problems when the view did not follow the switch to `want`"""
        p = []
        for key in ("canvas", "construct"):
            if key in b:
                L = lum(b[key]["rgb"])
                if (want == "dark" and L > 0.08) or (want == "light" and L < 0.6):
                    p.append(f"{key} background {b[key]['rgb']} (luminance {L:.2f}) after switching to {want}")
        if "chart" in b:
            ch = b["chart"] or {}
            if not ch or ch.get("text") != ch.get("tok") or ch.get("text") == (a.get("chart") or {}).get("text"):
                p.append(f"chart colours did not follow: {a.get('chart')} -> {ch}")
        if "frame" in b and b["frame"]["theme"] != want:
            p.append(f"pyLODE iframe is {b['frame']['theme']}")
        return p

    def toggle_page(page):
        def fn():
            ctx, pg, log = c.open(loop_page(page), scheme="light", ready_timeout=T_(240000))
            try:
                if page == "sparql.html":    # draw a CONSTRUCT result so the 3D view is part of the switch
                    pg.locator("#ex-construct button").first.click()
                    pg.wait_for_function("!!window.__VLONTO_METRICS.constructDrawn", timeout=T_(120000))
                    pg.wait_for_timeout(1500)
                pg.wait_for_timeout(1500 if page in SCENES else 400)
                s0 = pg.evaluate(JS_THEME)
                if s0["theme"] != "light" or s0["source"] != "system" or s0["pressed"] != "false" or s0["label"] != "Dark theme":
                    raise RuntimeError(f"system default (light) not applied: {s0}")
                x0 = extras(pg, page)
                click_theme(pg, "dark")
                pg.wait_for_timeout(1500 if page in SCENES or page == "sparql.html" else 600)
                s1, x1 = pg.evaluate(JS_THEME), extras(pg, page)
                prob = []
                if s1["pressed"] != "true":
                    prob.append(f"aria-pressed {s1['pressed']}")
                if s1["stored"] != "dark":
                    prob.append(f"stored {s1['stored']}")
                if s1["bodyBg"] == s0["bodyBg"] and page not in SCENES:
                    prob.append("page background unchanged")
                if page in SCENES and s1["renders"] < 1:
                    prob.append("scene did not re-render")
                prob += compare(page, x0, x1, "dark")
                click_theme(pg, "light")
                pg.wait_for_timeout(1500 if page in SCENES or page == "sparql.html" else 600)
                s2, x2 = pg.evaluate(JS_THEME), extras(pg, page)
                if s2["bodyBg"] != s0["bodyBg"]:
                    prob.append("page background not restored")
                prob += compare(page, x1, x2, "light")
                if prob:
                    raise RuntimeError("; ".join(prob))
                return {"light": s0["bodyBg"], "dark": s1["bodyBg"], "extras": [x0, x1, x2]}
            finally:
                merge(log)
                ctx.close()
        check(f"toggle switches {page} and back", fn)

    for page in SITE_PAGES:
        toggle_page(page)

    def persistence(init, label):
        def fn():
            ctx, pg, log = c.open("about.html", scheme="light", init_script=init)
            try:
                click_theme(pg, "dark")
                nav_to(c, pg, "dashboard.html")
                a = pg.evaluate(JS_THEME)
                pg.reload(wait_until="load")
                pg.wait_for_function("window.__VLONTO_READY === true", timeout=T_(120000))
                b = pg.evaluate(JS_THEME)
                click_theme(pg, "light")
                nav_to(c, pg, "playbook.html")
                d = pg.evaluate(JS_THEME)
                if (a["theme"], b["theme"], d["theme"]) != ("dark", "dark", "light"):
                    raise RuntimeError(f"themes after navigate/reload/toggle+navigate: {a['theme']}, {b['theme']}, {d['theme']} ({a['url']}, {d['url']})")
                return {"after_nav": [a["theme"], a["source"], a["url"][-40:]], "after_reload": [b["theme"], b["source"]],
                        "after_toggle_nav": [d["theme"], d["source"], d["url"][-40:]], "stored": a["stored"]}
            finally:
                merge(log)
                ctx.close()
        check(f"choice persists across pages and reload ({label})", fn)

    persistence(None, "localStorage")
    persistence(NO_STORAGE, "storage blocked: ?theme= carried on links")

    def system():
        ctx, pg, log = c.open("about.html", scheme="dark")
        try:
            a = pg.evaluate(JS_THEME)
            pg.emulate_media(color_scheme="light")
            pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=T_(10000))
            click_theme(pg, "dark")
            pg.emulate_media(color_scheme="light")
            pg.wait_for_timeout(400)
            b = pg.evaluate(JS_THEME)
            if a["theme"] != "dark" or a["source"] != "system" or b["theme"] != "dark":
                raise RuntimeError(f"system default {a['theme']}/{a['source']}, after choice + system change {b['theme']}")
            return {"default": [a["theme"], a["source"]], "followed_system_change": True, "choice_kept": b["theme"]}
        finally:
            merge(log)
            ctx.close()
    check("follows prefers-color-scheme until a choice is made", system)

    def query():
        ctx, pg, log = c.open("about.html", scheme="light", query="?theme=dark")
        try:
            a = pg.evaluate(JS_THEME)
            nav_to(c, pg, "sparql.html")
            b = pg.evaluate(JS_THEME)
            if a["theme"] != "dark" or a["source"] != "url" or b["theme"] != "dark" or "theme=dark" not in b["url"]:
                raise RuntimeError(f"?theme=dark: {a['theme']}/{a['source']}, next page {b['theme']} {b['url']}")
            return {"forced": a["theme"], "next_page": b["url"][-30:]}
        finally:
            merge(log)
            ctx.close()
    check("?theme=dark forces the theme and travels on links", query)

    def iframe():
        """The frame is a 680 kB document whose theme script (js/doc-theme.js) runs at its very end; the page is ready
        earlier. Under file:// the frame is cross-origin, and Chromium throttles the rendering (requestAnimationFrame)
        of cross-origin frames outside the viewport, so a wait in the frame polls by interval, not per animation frame
        (Playwright's default), and starts once the frame's script is in place. A failing step reports the page and
        frame state (theme, readyState, messages sent and received, frame position)."""
        ctx, pg, log = c.open("ontology.html", scheme="light")
        steps, holder = [], {}
        is_theme = "(t) => document.documentElement.getAttribute('data-theme') === t"

        def state():
            out = {"done": steps[:]}
            try:
                out["page"] = pg.evaluate("""() => { const M = window.__VLONTO_METRICS || {}, f = document.querySelector('#doc-frame');
                    const r = f ? f.getBoundingClientRect() : null;
                    return { theme: document.documentElement.getAttribute('data-theme'), posts: M.themePosts || 0,
                      requests: M.themeRequests || 0, frame_top_bottom_vh: r ? [Math.round(r.top), Math.round(r.bottom), innerHeight] : null }; }""")
            except Exception as e:  # noqa
                out["page"] = str(e)[:160]
            if "f" in holder:
                try:
                    out["frame"] = holder["f"].evaluate("""() => ({ theme: document.documentElement.getAttribute('data-theme'),
                        ready: document.readyState, script: window.__VLONTO_DOC_THEME ? window.__VLONTO_DOC_THEME.stats || true : null })""")
                except Exception as e:  # noqa
                    out["frame"] = str(e)[:160]
            return out

        def step(name, fn):
            try:
                fn()
            except Exception as e:  # noqa
                first = (str(e).strip().splitlines() or [""])[0][:200]
                raise RuntimeError(f"step '{name}': {first}; state {json.dumps(state(), ensure_ascii=False)}")
            steps.append(name)

        try:
            step("find the frame", lambda: holder.setdefault("f", doc_frame(pg)))
            f = holder["f"]
            step("frame loaded", lambda: f.wait_for_load_state("load", timeout=T_(60000)))
            step("frame script ready", lambda: f.wait_for_function("() => !!window.__VLONTO_DOC_THEME", timeout=T_(15000), polling=100))
            step("frame light at start", lambda: f.wait_for_function(is_theme, arg="light", timeout=T_(15000), polling=100))
            step("header toggle: page dark", lambda: click_theme(pg, "dark"))
            step("frame follows: dark", lambda: f.wait_for_function(is_theme, arg="dark", timeout=T_(15000), polling=100))
            bg = f.evaluate("getComputedStyle(document.body).backgroundColor")
            step("frame toggle", lambda: f.locator(".vl-theme-btn").click())
            step("page follows the frame: light", lambda: pg.wait_for_function(is_theme, arg="light", timeout=T_(15000)))
            step("frame light", lambda: f.wait_for_function(is_theme, arg="light", timeout=T_(15000), polling=100))
            return {"frame_dark_bg": bg, "frame_toggle_switched_page": True, "state": state()}
        finally:
            merge(log)
            ctx.close()
    check("pyLODE iframe follows the page, and its own toggle switches the page", iframe)

    def doc_standalone():
        ctx, pg, log = c.open("ontology/vlonto.html", scheme="dark", ready=False)
        try:
            pg.wait_for_function("!!window.__VLONTO_DOC_THEME", timeout=T_(30000))
            a = pg.evaluate("document.documentElement.getAttribute('data-theme')")
            pg.locator(".vl-theme-btn").click()
            pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=T_(10000))
            st = pg.evaluate("(() => { try { return localStorage.getItem('vlonto.theme'); } catch (e) { return 'blocked'; } })()")
            if a != "dark" or st != "light":
                raise RuntimeError(f"pyLODE page default {a}, stored after toggle {st}")
            return {"default": a, "stored": st}
        finally:
            merge(log)
            ctx.close()
    check("pyLODE page alone: system default and its own toggle", doc_standalone)
    res["log"] = logs
    return res


def t_paper(c: Ctx):
    """The paper: the arXiv link (exact URL) in the header and footer of every page, in the playground panel, the home
    card and the network/SPARQL panels; BibTeX copy works or falls back to selecting the text, without errors;
    nothing overflows at 390 px; screenshots of the home card and the playground panel in both themes (http)."""
    res = {"test": "paper", "checks": []}
    logs = {"console_errors": [], "page_errors": [], "failed_requests": [], "external_requests": []}

    def merge(log):
        for k in logs:
            logs[k] += log.get(k, [])

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": {"error": str(e)[:1200]}, "s": round(time.time() - t0, 2)})

    def open_side(pg):
        if c.mobile:
            pg.locator("#btn-side-m").click()
            pg.wait_for_timeout(400)

    forbidden = {}

    def links():
        found, prob = {}, []
        for page in SITE_PAGES + ["ontology/vlonto.html"]:
            ctx, pg, log = c.open(loop_page(page), ready=not page.startswith("ontology/"), ready_timeout=T_(240000))
            try:
                if page.startswith("ontology/"):
                    pg.wait_for_timeout(800)
                found[page] = pg.evaluate("""(u) => Array.from(document.querySelectorAll('a')).filter(a => a.href === u).map(a => ({
                    where: a.getAttribute('data-paper-link'), rel: a.rel, target: a.target, text: a.textContent.trim().replace(/\\s+/g, ' ') }))""", PAPER_URL)
                bad = pg.evaluate("""() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
                    .filter(h => /huggingface\\.co\\/spaces\\/|huggingface\\.co\\/datasets\\/tmquan\\/VLOnto(?:[\\/?#]|$)/i.test(h))""")
                if bad:
                    forbidden[page] = sorted(set(bad))
            finally:
                merge(log)
                ctx.close()
        extra = {"about.html": "card", "index.html": "panel", "network-3d.html": "side", "sparql.html": "side"}
        for page, L in found.items():
            wh = {x["where"] for x in L}
            need = {"doc-bar", "footer"} if page.startswith("ontology/") else {"nav", "footer"}
            if page in extra:
                need.add(extra[page])
            if not need <= wh:
                prob.append(f"{page}: missing {sorted(need - wh)}")
            for x in L:
                if x["target"] == "_blank" and "noopener" not in x["rel"]:
                    prob.append(f"{page}: {x['where']} link without rel=noopener")
            foot = [x["text"] for x in L if x["where"] == "footer"]
            if foot and foot[0] != PAPER_CITE:
                prob.append(f"{page}: footer text {foot[0]!r}")
        if prob:
            raise RuntimeError("; ".join(prob))
        # links without data-paper-link (e.g. the arXiv id inside the card or panel) are listed as 'in-text'
        return {p: sorted({x["where"] or "in-text" for x in L}) for p, L in found.items()}
    check("paper link (exact arXiv URL) on every page: header, footer, card and panels", links)

    def no_hf_space():
        if forbidden:
            raise RuntimeError(f"links to a Hugging Face Space or to the withdrawn tmquan/VLOnto dataset: {forbidden}")
        return {"pages_checked": len(SITE_PAGES) + 1, "forbidden_links": 0}
    check("no page links a Hugging Face Space or the withdrawn tmquan/VLOnto dataset", no_hf_space)

    def copy(page, variant):
        def fn():
            init = NO_CLIPBOARD if variant == "fallback" else None
            perms = ["clipboard-read", "clipboard-write"] if variant == "clipboard" else None
            ctx, pg, log = c.open(page, init_script=init, permissions=perms, ready_timeout=T_(180000))
            try:
                if page == "index.html":
                    open_side(pg)
                btn = pg.locator("[data-copy-bib]").first
                btn.scroll_into_view_if_needed()
                btn.click()
                pg.wait_for_function("!!window.__VLONTO_METRICS.lastCopy", timeout=T_(10000))
                pg.wait_for_timeout(200)
                how = pg.evaluate("window.__VLONTO_METRICS.lastCopy")
                got = None
                if how == "clipboard" and c.mode == "http":
                    got = pg.evaluate("navigator.clipboard.readText()")
                elif how == "selected":
                    got = pg.evaluate("String(window.getSelection())")
                if variant == "fallback" and how != "selected":
                    raise RuntimeError(f"fallback expected 'selected', got {how}")
                if got is not None and got.strip() != PAPER_BIBTEX.strip():
                    raise RuntimeError(f"copied/selected text differs: {got[:160]!r}")
                errs = log["console_errors"] + log["page_errors"]
                if errs:
                    raise RuntimeError(f"errors: {errs[:3]}")
                toast = pg.evaluate("Array.from(document.querySelectorAll('[role=status]')).map(e => e.textContent).join(' | ')")
                return {"path": how, "text_verified": got is not None, "toast": toast}
            finally:
                merge(log)
                ctx.close()
        check(f"BibTeX copy on {page} ({variant})", fn)

    for page in ("about.html", "index.html"):
        copy(page, "clipboard")
        copy(page, "fallback")

    def overflow():
        out = {}
        for page in ("about.html", "index.html"):
            ctx, pg, log = c.open(page)
            try:
                if page == "index.html":
                    open_side(pg)
                    pg.locator("#paper-section").scroll_into_view_if_needed()
                w = no_hscroll(c, pg, page)
                r = pg.evaluate("""() => { const vw = document.documentElement.clientWidth;
                    const pre = Array.from(document.querySelectorAll('pre.bibtex')).map(p => { const b = p.getBoundingClientRect();
                      return { right: Math.round(b.right), vw: vw, scrolls_inside: p.scrollWidth > p.clientWidth }; });
                    const titles = Array.from(document.querySelectorAll('.paper-title')).map(t => ({ fits: t.scrollWidth <= t.clientWidth + 1,
                      right: Math.round(t.getBoundingClientRect().right), vw: vw }));
                    return { pre: pre, titles: titles }; }""")
                bad = [x for x in r["pre"] if x["right"] > x["vw"] + 1 or x["scrolls_inside"]] + \
                      [x for x in r["titles"] if not x["fits"] or x["right"] > x["vw"] + 1]
                if bad:
                    raise RuntimeError(f"{page}: overflow {bad}")
                out[page] = {"page_width": w, **r}
            finally:
                merge(log)
                ctx.close()
        return out
    check("paper title and BibTeX wrap inside their boxes (no page overflow, no hidden horizontal scroll)", overflow)

    def shots():
        if c.mode != "http":
            return {"skipped": "screenshots are taken over http"}
        rec = []
        for theme in c.themes:
            ctx, pg, log = c.open("about.html", scheme=theme)
            try:
                el = pg.locator("#paper")
                el.scroll_into_view_if_needed()
                pg.wait_for_timeout(250)
                p = c.out / "gallery" / f"paper_about__{theme}__{c.vp[0]}x{c.vp[1]}.png"
                p.parent.mkdir(parents=True, exist_ok=True)
                el.screenshot(path=str(p))
                rec.append(str(p.relative_to(c.out)))
            finally:
                merge(log)
                ctx.close()
            ctx, pg, log = c.open("index.html", scheme=theme)
            try:
                open_side(pg)
                sec = pg.locator("#paper-section")
                sec.scroll_into_view_if_needed()
                pg.wait_for_timeout(1200)
                p1 = c.out / "gallery" / f"paper_playground__{theme}__{c.vp[0]}x{c.vp[1]}.png"
                pg.screenshot(path=str(p1))
                p2 = c.out / "gallery" / f"paper_playground_panel__{theme}__{c.vp[0]}x{c.vp[1]}.png"
                sec.screenshot(path=str(p2))
                rec += [str(p1.relative_to(c.out)), str(p2.relative_to(c.out))]
            finally:
                merge(log)
                ctx.close()
        return rec
    check("screenshots: about-page paper card and playground paper panel, both themes", shots)
    res["log"] = logs
    return res


# Paper style of the 3D views (css/site.css "paper style", js/paper3d.js): expected tokens per theme, the colours of the
# traced path, and the old palette of the pages outside the 3D views.
PAPER_EXPECT = {
    "light": {"scene_bg": "#ffffff", "core": "#2c3a47", "halo": "#ecc890", "work": "#7dbe8e", "callout_line": "#d3d7dc"},
    "dark": {"scene_bg": "#0f131a", "core": "#f6f1e6", "halo": "#ecc890", "work": "#7dbe8e", "callout_line": "#3a4350"},
}
OTHER_PAGES_EXPECT = {"light": {"mod_documents": "#2563eb", "scene_bg": "#f3f6fb"}, "dark": {"mod_documents": "#4f8ef7", "scene_bg": "#0a0f1e"}}
JS_PAPER = """(sel) => { const el = sel ? document.querySelector(sel) : document.documentElement, cs = getComputedStyle(el), M = window.__VLONTO_METRICS || {};
  const t = n => cs.getPropertyValue(n).trim().toLowerCase();
  const lib = [...document.fonts].filter(f => f.family.replace(/["']/g, '') === 'Libertinus Sans').map(f => f.weight + '/' + f.style + ':' + f.status);
  return { scope: el.getAttribute('data-style'), theme: document.documentElement.getAttribute('data-theme'), scene_bg: t('--scene-bg'),
    core: t('--paper-trace-core'), halo: t('--paper-trace-halo'), work: t('--cls-work'), callout_line: t('--paper-callout-line'),
    font_paper: t('--vlo-font-paper'), libertinus: lib, paperStyle: !!M.paperStyle }; }"""
# pixels of the traced path in a screenshot, decoded in the page (like JS_MODE): the raw counts of core- and halo-coloured
# pixels (within a colour tolerance), and two counts that leave out the call-out boxes (the selected node's call-out uses
# the core colour for its border on the light theme and the halo colour on the dark one): core pixels, and gold pixels
# (R >= G >= B, R - B >= 40: the halo family, i.e. halo, outer halo and their blends with the ground or the core) within
# `radius` device px of a core pixel, i.e. the halo band that flanks the core whatever the trace width, antialiasing or
# the view behind it
JS_TRACE_PX = """async (arg) => { const img = new Image(); img.src = arg.src; await img.decode();
  const W = img.naturalWidth, H = img.naturalHeight, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const cx = cv.getContext('2d', { willReadFrequently: true }); cx.drawImage(img, 0, 0);
  const d = cx.getImageData(0, 0, W, H).data, n = W * H, skip = new Uint8Array(n), core = new Uint8Array(n), s = W / arg.cssW;
  for (const b of arg.boxes) {
    const x0 = Math.max(0, Math.floor((b[0] + arg.ox - 3) * s)), y0 = Math.max(0, Math.floor((b[1] + arg.oy - 3) * s));
    const x1 = Math.min(W - 1, Math.ceil((b[2] + arg.ox + 3) * s)), y1 = Math.min(H - 1, Math.ceil((b[3] + arg.oy + 3) * s));
    for (let y = y0; y <= y1; y++) skip.fill(1, y * W + x0, y * W + x1 + 1); }
  const [cr, cg, cb, ct] = arg.core, [hr, hg, hb, ht] = arg.halo;
  let rawCore = 0, rawHalo = 0, coreOut = 0, near = 0;
  for (let p = 0, i = 0; p < n; p++, i += 4) {
    const r = d[i], g = d[i + 1], b = d[i + 2]; let dr = r - cr, dg = g - cg, db = b - cb;
    if (dr * dr + dg * dg + db * db <= ct * ct) { rawCore++; if (!skip[p]) { core[p] = 1; coreOut++; } }
    dr = r - hr; dg = g - hg; db = b - hb; if (dr * dr + dg * dg + db * db <= ht * ht) rawHalo++; }
  const R = arg.radius, row = new Uint8Array(n), ps = new Int32Array(Math.max(W, H) + 1);
  for (let y = 0; y < H; y++) { const o = y * W; for (let x = 0; x < W; x++) ps[x + 1] = ps[x] + core[o + x];
    for (let x = 0; x < W; x++) row[o + x] = ps[Math.min(W, x + R + 1)] - ps[Math.max(0, x - R)] > 0 ? 1 : 0; }
  for (let x = 0; x < W; x++) { for (let y = 0; y < H; y++) ps[y + 1] = ps[y] + row[y * W + x];
    for (let y = 0; y < H; y++) { const p = y * W + x; if (skip[p] || core[p] || ps[Math.min(H, y + R + 1)] === ps[Math.max(0, y - R)]) continue;
      const i = 4 * p, r = d[i], g = d[i + 1], b = d[i + 2];
      if (r >= g && g >= b && r - b >= 40 && g - b >= 0.3 * (r - b)) near++; } }
  return [rawCore, rawHalo, coreOut, near]; }"""
JS_TRACE_PX_GEOM = """(sel) => { const el = document.querySelector(sel), co = (window.__VLONTO_METRICS || {}).callouts || {};
  return { cssW: el.getBoundingClientRect().width, ox: el.clientLeft, oy: el.clientTop, dpr: window.devicePixelRatio || 1,
    boxes: (co.placed || []).map(p => p.box) }; }"""


# call-out placement of the 3D views (js/paper3d.js VL.Callouts -> window.__VLONTO_METRICS.callouts) and the cap of the
# trace widths in CSS px (VL.TRACE_W)
JS_CALLOUTS = "() => window.__VLONTO_METRICS.callouts || null"
TRACE_CAP = {"core": 2.8, "halo": 6.4, "halo2": 9.2}
# the overlays on the stage of a 3D view (legend, status line, hint, stage tools) do not meet: the paper legend can be
# 720 px wide and the status line moves left when the details panel opens, so the legend moves up above it
# (VL.fitLegend in js/paper3d.js); returns the pairs that meet
JS_OVERLAYS = """() => { const R = {}, out = [];
  [['legend', '#legend'], ['status', '#status'], ['hint', '#hint'], ['tools', '.stage-tools']].forEach(([k, s]) => {
    const e = document.querySelector(s);
    if (!e || e.offsetParent === null) return;
    const r = e.getBoundingClientRect();
    if (r.width > 1 && r.height > 1) R[k] = r;
  });
  const ks = Object.keys(R);
  for (let i = 0; i < ks.length; i++) for (let j = i + 1; j < ks.length; j++) {
    const a = R[ks[i]], b = R[ks[j]];
    if (a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) out.push(ks[i] + ' meets ' + ks[j]);
  }
  return out; }"""


def callout_faults(co, must=True):
    """the paper's rule for one placement run: no two visible call-outs intersect, no visible call-out covers a projected
    node centre (the nodes the run saw: every visible node in the playground and the CONSTRUCT view, the highlighted
    documents in the legal network), no call-out is cut by the canvas edge (the run's W x H, 0.5 px tolerance; longer
    or shorter text per language mode changes the boxes), and no selected or traced call-out was dropped (must=False:
    the caller judges that by its own geometry, as the traces page does with its hop panel)"""
    if not co:
        return ["no call-out placement recorded"]
    boxes = [(p["id"], p["box"]) for p in co.get("placed", [])]
    inter = [(a[0], b[0]) for i, a in enumerate(boxes) for b in boxes[i + 1:]
             if a[1][0] < b[1][2] and b[1][0] < a[1][2] and a[1][1] < b[1][3] and b[1][1] < a[1][3]]
    covered = [(pid, nid) for pid, b in boxes for nid, x, y in co.get("nodes", []) if b[0] < x < b[2] and b[1] < y < b[3]]
    W, H = co.get("W"), co.get("H")
    cut = [pid for pid, b in boxes if W and H and (b[0] < -0.5 or b[1] < -0.5 or b[2] > W + 0.5 or b[3] > H + 0.5)]
    faults = []
    if inter:
        faults.append(f"{len(inter)} pairs of intersecting call-outs, e.g. {inter[:3]}")
    if covered:
        faults.append(f"{len(covered)} node centres under call-outs, e.g. {covered[:3]}")
    if cut:
        faults.append(f"{len(cut)} call-outs cut by the canvas edge ({W}x{H}), e.g. {cut[:3]}")
    if must and co.get("mustHidden"):
        faults.append(f"{co['mustHidden']} selected or traced call-outs hidden")
    return faults


def wait_callouts(pg, after_runs=0, must_id=None, timeout=T_(15000)):
    """wait for a placement run newer than after_runs (with must_id: one that shows that call-out); returns the run"""
    pg.wait_for_function("""(a) => { const c = window.__VLONTO_METRICS.callouts;
        return !!c && c.runs > a.runs && (!a.id || c.placed.some(p => p.id === a.id)); }""", arg={"runs": after_runs, "id": must_id}, timeout=timeout)
    pg.wait_for_timeout(400)
    return pg.evaluate(JS_CALLOUTS)


def callout_summary(co):
    return {k: co.get(k) for k in ("runs", "shown", "hidden", "mustOffscreen", "forced", "ms", "W", "H")} if co else None


def hex_rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def trace_pixels(pg, sel, theme):
    """navy (light) or off-white (dark) core pixels and gold halo pixels in the element's screenshot; the overlays (details
    panel, hint, tooltip and the legend with its own trace swatch) are hidden while capturing, so only WebGL is counted.
    core / halo: raw counts; core_out: core pixels outside the call-out boxes; halo_near_core: gold pixels next to those
    (within the trace's half width at the cap, 3.2 CSS px, plus 2 device px), outside the call-out boxes (JS_TRACE_PX)"""
    e = PAPER_EXPECT[theme]
    hide = "#panel, #hint, #tip, .legend, .vl-footbar"
    pg.evaluate("(q) => document.querySelectorAll(q).forEach(e => { e.dataset.ccVis = e.style.visibility; e.style.visibility = 'hidden'; })", hide)
    pg.wait_for_timeout(120)
    try:
        png = pg.locator(sel).first.screenshot()
        geo = pg.evaluate(JS_TRACE_PX_GEOM, sel)
    finally:
        pg.evaluate("(q) => document.querySelectorAll(q).forEach(e => { e.style.visibility = e.dataset.ccVis || ''; delete e.dataset.ccVis; })", hide)
    radius = math.ceil(TRACE_CAP["halo2"] / 2 * geo["dpr"] - TRACE_CAP["core"] / 2 * geo["dpr"]) + 2
    core, halo, core_out, near = pg.evaluate(JS_TRACE_PX, {
        "src": "data:image/png;base64," + base64.b64encode(png).decode(), "cssW": geo["cssW"], "ox": geo["ox"], "oy": geo["oy"],
        "boxes": geo["boxes"], "radius": radius, "core": hex_rgb(e["core"]) + [12], "halo": hex_rgb(e["halo"]) + [16]})
    return {"core": core, "halo": halo, "core_out": core_out, "halo_near_core": near, "callout_boxes": len(geo["boxes"])}


def t_paper_style(c: Ctx):
    """The 3D views follow the paper's figures (arXiv:2611.11426, Fig. 1 / Fig. 6): per theme the scene ground, class
    colours, call-out border and trace colours come from the paper-style tokens and Libertinus Sans is loaded; selecting a
    class in the playground and 45/2019/QH14 in the legal network draws the traced path (core and halo pixels appear);
    a selection with many links traces only its chain (the network: the replacement chain) and a hovered link, its other
    links are thin coloured lines; a CONSTRUCT result on the SPARQL page is traced when small and traces the hovered
    node's links when large, with the paper's legend row. In every view and state the call-outs never intersect, never
    cover a node centre, and the selected / traced ones stay (window.__VLONTO_METRICS.callouts, js/paper3d.js
    VL.Callouts). Pages outside the 3D views keep their palette. Screenshots of each view in both themes."""
    res = {"test": "paper style (3D views)", "checks": []}
    logs = {"console_errors": [], "page_errors": [], "failed_requests": [], "external_requests": []}

    def merge(log):
        for k in logs:
            logs[k] += log.get(k, [])

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": {"error": str(e)[:1200]}, "s": round(time.time() - t0, 2)})

    def tokens_ok(got, theme, where):
        want = PAPER_EXPECT[theme]
        bad = [f"{k} {got.get(k)} != {v}" for k, v in want.items() if got.get(k) != v]
        if got.get("theme") != theme:
            bad.append(f"theme {got.get('theme')}")
        if "libertinus sans" not in (got.get("font_paper") or "").lower():  # JS_PAPER lower-cases every token
            bad.append(f"--vlo-font-paper {got.get('font_paper')}")
        if not any(s.endswith(":loaded") for s in got.get("libertinus") or []):
            bad.append(f"Libertinus Sans not loaded: {got.get('libertinus')}")
        if bad:
            raise RuntimeError(f"{where}: " + "; ".join(bad))

    def shot(pg, name, theme):
        if c.mode != "http":
            return None
        p = c.out / "gallery" / f"paper_style_{name}__{theme}__{c.vp[0]}x{c.vp[1]}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(p))
        return str(p.relative_to(c.out))

    for theme in c.themes:
        def playground(theme=theme):
            ctx, pg, log = c.open("index.html", scheme=theme)
            try:
                pg.wait_for_timeout(1500)
                got = pg.evaluate(JS_PAPER, None)
                tokens_ok(got, theme, "index.html")
                legend = pg.evaluate("document.getElementById('legend').textContent") if not c.mobile else ""
                if not c.mobile and not all(x in legend for x in ("Văn bản · Documents", "Điều khoản · Provisions", "Đường truy vết")):
                    raise RuntimeError(f"legend row: {legend[:200]}")
                cap = pg.evaluate("() => window.VL.TRACE_W")
                if cap != TRACE_CAP:
                    raise RuntimeError(f"trace width cap {cap} != {TRACE_CAP}")
                co0 = wait_callouts(pg)
                faults = callout_faults(co0)
                if faults:
                    raise RuntimeError("default view: " + "; ".join(faults))
                before = trace_pixels(pg, "#canvas-host", theme)
                runs = co0["runs"]
                pg.evaluate("() => window.VLApp.select('vlo:Article')")
                pg.wait_for_function("window.__VLONTO_METRICS.selected === 'vlo:Article' && window.__VLONTO_METRICS.traceSegments > 0", timeout=T_(15000))
                pg.wait_for_timeout(1800)
                co1 = wait_callouts(pg, runs, "vlo:Article")
                faults = callout_faults(co1)
                if faults:
                    raise RuntimeError("Article selected: " + "; ".join(faults))
                after = trace_pixels(pg, "#canvas-host", theme)
                m = pg.evaluate("window.__VLONTO_METRICS")
                if m.get("highlightChain", 0) < 1:
                    raise RuntimeError(f"no superclass chain in the highlight: {m.get('highlightChain')}")
                # the trace's own pixels: its core outside the call-out boxes, and the gold halo band flanking that core
                # (a raw count of gold pixels also follows pastel nodes that leave the view when the camera flies in)
                d_core = after["core_out"] - before["core_out"]
                d_halo = after["halo_near_core"] - before["halo_near_core"]
                need_halo = max(60, d_core // 2)
                if d_core < 30 or d_halo < need_halo:
                    raise RuntimeError(f"traced path not drawn: core pixels +{d_core} (need 30), halo pixels next to the core "
                                       f"+{d_halo} (need {need_halo}); {before} -> {after}")
                shot_article = shot(pg, "playground_article", theme)
                # a class with more than 6 links (NormativeLegalDocument: 11): only its chain up the hierarchy is traced, the
                # other links are thin coloured lines; hovering a neighbour traces its link and keeps its call-out
                r0 = pg.evaluate("window.__VLONTO_METRICS.callouts.runs")
                pg.evaluate("() => window.VLApp.select('vlo:NormativeLegalDocument')")
                pg.wait_for_function("window.__VLONTO_METRICS.selected === 'vlo:NormativeLegalDocument'", timeout=T_(15000))
                pg.wait_for_timeout(1800)
                co2 = wait_callouts(pg, r0, "vlo:NormativeLegalDocument")
                faults = callout_faults(co2)
                if faults:
                    raise RuntimeError("NormativeLegalDocument selected: " + "; ".join(faults))
                clash = pg.evaluate(JS_HINT_CLASH)
                if clash:
                    raise RuntimeError(f"NormativeLegalDocument selected: the first-visit hint overlaps the stage tools: {clash}")
                m2 = pg.evaluate("window.__VLONTO_METRICS")
                if m2.get("emphLinks", 0) < 5 or not (1 <= m2.get("traceLinks", 0) <= 2):
                    raise RuntimeError(f"many links: expected the chain traced (1-2 links) and the rest thin, got traceLinks {m2.get('traceLinks')}, emphLinks {m2.get('emphLinks')}")
                hover = None
                for p in sorted(co2["placed"], key=lambda q: q["id"] == "vlo:LegalDocument"):
                    if p["id"] == "vlo:NormativeLegalDocument":
                        continue
                    r1 = pg.evaluate("window.__VLONTO_METRICS.callouts.runs")
                    n = pg.evaluate("(id) => window.VLApp.hover(id)", p["id"])
                    if n:
                        hover = {"node": p["id"], "links": n, "trace_links": pg.evaluate("window.__VLONTO_METRICS.traceLinks")}
                        co3 = wait_callouts(pg, r1, p["id"])
                        faults = callout_faults(co3)
                        if faults:
                            raise RuntimeError(f"hovering {p['id']}: " + "; ".join(faults))
                        hover["shot"] = shot(pg, "playground_many_links", theme)
                        break
                pg.evaluate("() => window.VLApp.hover(null)")
                if not hover:
                    raise RuntimeError("hovering a neighbour of NormativeLegalDocument traced no link")
                if hover["node"] != "vlo:LegalDocument" and hover["trace_links"] <= m2.get("traceLinks", 0):
                    raise RuntimeError(f"the hovered link was not added to the trace: {m2.get('traceLinks')} -> {hover['trace_links']}")
                if pg.evaluate("window.__VLONTO_METRICS.hoverTrace"):
                    raise RuntimeError("the hover trace stayed after the hover ended")
                return {"tokens": {k: got[k] for k in ("scene_bg", "core", "halo", "work")}, "libertinus": got["libertinus"], "trace_links": m.get("traceLinks"),
                        "trace_segments": m.get("traceSegments"), "chain": m.get("highlightChain"), "pixels_before": before, "pixels_after": after,
                        "many_links": {"trace_links": m2.get("traceLinks"), "emphasised_links": m2.get("emphLinks"), "hover": hover},
                        "callouts_default": callout_summary(co0), "callouts_article": callout_summary(co1), "callouts_many": callout_summary(co2),
                        "legend_entries": m.get("legendEntries"), "shot": shot_article}
            finally:
                merge(log)
                ctx.close()
        check(f"playground ({theme}): tokens, Libertinus, legend row; call-outs clear of ink and of each other; selecting Article traces its chain, a hover traces a link", playground)

        def network(theme=theme):
            ctx, pg, log = c.open("network-3d.html", scheme=theme, ready_timeout=T_(240000))
            try:
                got = pg.evaluate(JS_PAPER, None)
                tokens_ok(got, theme, "network-3d.html")
                before = trace_pixels(pg, "#canvas-host", theme)
                runs = (pg.evaluate(JS_CALLOUTS) or {}).get("runs", 0)
                pg.evaluate("() => window.VLApp.selectById('333670')")
                pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '333670' && window.__VLONTO_METRICS.chainTraceDocs >= 2", timeout=T_(120000))
                pg.wait_for_timeout(1800)
                co1 = wait_callouts(pg, runs, "doc-333670", timeout=T_(60000))
                faults = callout_faults(co1)
                if faults:
                    raise RuntimeError("45/2019/QH14 selected: " + "; ".join(faults))
                after = trace_pixels(pg, "#canvas-host", theme)
                m = pg.evaluate("window.__VLONTO_METRICS")
                # the hub's own links are thin lines in their link-type colours; only the replacement chain is traced
                if m.get("traceSegments"):
                    raise RuntimeError(f"{m.get('traceSegments')} links of the selection traced without a hover (only the chain may be)")
                if not m.get("egoLines"):
                    raise RuntimeError("the selection's links are not drawn as thin coloured lines")
                if after["core"] - before["core"] < 30 or after["halo"] - before["halo"] < 60:
                    raise RuntimeError(f"replacement chain not traced: core/halo pixels {before} -> {after}")
                # hovering the other document of the chain (10/2012/QH13, replaced by 45/2019/QH14) traces their link
                r0 = pg.evaluate("window.__VLONTO_METRICS.callouts.runs")
                hovered = pg.evaluate("() => window.VLApp.hoverDoc('142187')")
                if not hovered:
                    raise RuntimeError("hovering 10/2012/QH13 traced no link")
                co2 = wait_callouts(pg, r0, "doc-142187", timeout=T_(60000))
                faults = callout_faults(co2)
                if faults:
                    raise RuntimeError("10/2012/QH13 hovered: " + "; ".join(faults))
                pg.evaluate("() => window.VLApp.hoverDoc(null)")
                if pg.evaluate("window.__VLONTO_METRICS.traceSegments"):
                    raise RuntimeError("the hover trace stayed after the hover ended")
                legend = pg.evaluate("document.getElementById('legend').textContent") if not c.mobile else ""
                if not c.mobile and "Đường truy vết" not in legend:
                    raise RuntimeError(f"legend: {legend[:200]}")
                # links are curves drawn on the GPU (several segments per link), and the swatches of the legend and of the
                # link toggles are curves too; the trace swatch keeps its navy core over the gold halo
                cost = pg.evaluate("window.__VLONTO_METRICS.edgeCost") or {}
                sw = pg.evaluate("""() => ({ legend: document.querySelectorAll('#legend svg.swatch-curve').length,
                    trace: document.querySelectorAll('#legend svg.swatch-curve.trace path').length,
                    toggles: document.querySelectorAll('#edge-toggles svg.swatch-curve').length })""")
                if not cost.get("curves") or cost.get("vertices", 0) < 3 * cost.get("links", 1) or not sw["toggles"] \
                        or (not c.mobile and (sw["legend"] < 2 or sw["trace"] != 2)):
                    raise RuntimeError(f"curved links: cost {cost}, swatches {sw}")
                return {"chain_docs": m.get("chainTraceDocs"), "ego_edges": m.get("egoEdges"), "ego_lines": m.get("egoLines"), "hover_trace_segments": hovered,
                        "pixels_before": before, "pixels_after": after, "callouts_selected": callout_summary(co1), "callouts_hover": callout_summary(co2),
                        "edge_cost": cost, "curve_swatches": sw, "shot": shot(pg, "network_45_2019", theme)}
            finally:
                merge(log)
                ctx.close()
        check(f"legal network ({theme}): tokens; 45/2019/QH14: only the replacement chain traced, a hovered link traced, call-outs clear", network)

        def construct(theme=theme):
            ctx, pg, log = c.open("sparql.html", scheme=theme)
            try:
                pg.locator("#ex-construct button").first.click()
                pg.wait_for_function("!!window.__VLONTO_METRICS.constructDrawn && !!window.__VLONTO_METRICS.callouts", timeout=T_(120000))
                pg.wait_for_timeout(2000)
                got = pg.evaluate(JS_PAPER, "#graph-wrap")
                tokens_ok(got, theme, "sparql.html #graph-wrap")
                page_bg = pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--mod-documents').trim().toLowerCase()")
                if page_bg != OTHER_PAGES_EXPECT[theme]["mod_documents"]:
                    raise RuntimeError(f"the SPARQL page outside the CONSTRUCT view changed its palette: --mod-documents {page_bg}")
                m = pg.evaluate("window.__VLONTO_METRICS")
                hover, must, runs = None, None, m["callouts"]["runs"]
                if m.get("constructMode") == "lines":
                    # more than 12 links: thin lines in the colours of their predicates; hovering a node traces its links
                    if m.get("constructTrace"):
                        raise RuntimeError("a large CONSTRUCT result is traced without a hover")
                    if not m.get("constructLines"):
                        raise RuntimeError("the links of a large CONSTRUCT result are not drawn as thin lines")
                    nodes = pg.evaluate("() => window.VLApp.constructNodes()")
                    leaf = next((n["id"] for n in sorted(nodes, key=lambda n: n["links"]) if n["links"] >= 1), None)
                    hover = pg.evaluate("(id) => window.VLApp.constructHover(id)", leaf)
                    if not hover:
                        raise RuntimeError(f"hovering {leaf} traced no link")
                    must = leaf
                    pg.wait_for_timeout(800)
                px = trace_pixels(pg, "#graph-view", theme)
                if px["core"] < 30 or px["halo"] < 60:
                    raise RuntimeError(f"CONSTRUCT result (or the hovered node's links) not drawn as a trace: {px}")
                co = wait_callouts(pg, runs if must else runs - 1, must)
                faults = callout_faults(co)
                if faults:
                    raise RuntimeError("CONSTRUCT view: " + "; ".join(faults))
                legend = pg.evaluate("(document.getElementById('construct-legend') || {}).textContent || ''")
                if "Đường truy vết" not in legend:
                    raise RuntimeError(f"CONSTRUCT legend: {legend[:200]}")
                pg.locator("#graph-view").scroll_into_view_if_needed()
                return {"mode": m.get("constructMode"), "pixels": px, "legend": legend[:160], "trace": pg.evaluate("window.__VLONTO_METRICS.constructTrace"),
                        "lines": m.get("constructLines"), "hover": {"node": must, "trace_segments": hover} if must else None,
                        "callouts": callout_summary(co), "shot": shot(pg, "sparql_construct", theme)}
            finally:
                merge(log)
                ctx.close()
        check(f"SPARQL CONSTRUCT view ({theme}): scoped tokens, result traced (large: hovered node traced), call-outs clear, legend row", construct)

        def others(theme=theme):
            out = {}
            for page in ("about.html", "dashboard.html"):
                ctx, pg, log = c.open(page, scheme=theme)
                try:
                    got = pg.evaluate("""() => { const cs = getComputedStyle(document.documentElement);
                        return { scope: document.documentElement.getAttribute('data-style'), mod_documents: cs.getPropertyValue('--mod-documents').trim().toLowerCase(),
                                 scene_bg: cs.getPropertyValue('--scene-bg').trim().toLowerCase() }; }""")
                    want = OTHER_PAGES_EXPECT[theme]
                    if got["scope"] or got["mod_documents"] != want["mod_documents"] or got["scene_bg"] != want["scene_bg"]:
                        raise RuntimeError(f"{page} is not in its old look: {got}")
                    out[page] = got
                finally:
                    merge(log)
                    ctx.close()
            return out
        check(f"pages outside the 3D views keep their palette ({theme})", others)

    # the call-outs in EN and in VI (one language, other widths than EN–VI) follow the same rule in each view: the
    # playground's default view, 45/2019/QH14 in the legal network, the first CONSTRUCT example (light theme)
    for mode in ("en", "vi"):
        def placement(mode=mode):
            out, q = {}, f"?lang={mode}"
            ctx, pg, log = c.open("index.html", query=q)
            try:
                pg.wait_for_timeout(1500)
                co = wait_callouts(pg)
                faults = callout_faults(co)
                lang = pg.evaluate("window.__VLONTO_METRICS.labelsLang")
                if faults or lang != mode:
                    raise RuntimeError(f"playground default view ({mode}, call-outs {lang}): " + "; ".join(faults))
                out["playground"] = callout_summary(co)
            finally:
                merge(log)
                ctx.close()
            ctx, pg, log = c.open("network-3d.html", query=q, ready_timeout=T_(240000))
            try:
                runs = (pg.evaluate(JS_CALLOUTS) or {}).get("runs", 0)
                pg.evaluate("() => window.VLApp.selectById('333670')")
                pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '333670' && window.__VLONTO_METRICS.chainTraceDocs >= 2", timeout=T_(120000))
                pg.wait_for_timeout(1800)
                co = wait_callouts(pg, runs, "doc-333670", timeout=T_(60000))
                faults = callout_faults(co)
                lang = pg.evaluate("window.__VLONTO_METRICS.labelsLang")
                if faults or lang != mode:
                    raise RuntimeError(f"45/2019/QH14 ({mode}, call-outs {lang}): " + "; ".join(faults))
                out["network"] = callout_summary(co)
            finally:
                merge(log)
                ctx.close()
            ctx, pg, log = c.open("sparql.html", query=q)
            try:
                pg.locator("#ex-construct button").first.click()
                pg.wait_for_function("!!window.__VLONTO_METRICS.constructDrawn && !!window.__VLONTO_METRICS.callouts", timeout=T_(120000))
                pg.wait_for_timeout(2000)
                co = pg.evaluate(JS_CALLOUTS)
                faults = callout_faults(co)
                lang = pg.evaluate("window.__VLONTO_METRICS.labelsLang")
                if faults or lang != mode:
                    raise RuntimeError(f"CONSTRUCT ({mode}, call-outs {lang}): " + "; ".join(faults))
                out["construct"] = callout_summary(co)
            finally:
                merge(log)
                ctx.close()
            return out
        check(f"call-outs in {mode.upper()} (light): playground default view, 45/2019/QH14, CONSTRUCT clear of the ink, of each other and of the canvas edge", placement)

    # with the details panel open the status line moves left and meets the paper legend (up to 720 px wide; EN–VI rows
    # are the longest): the legend moves up above it (VL.fitLegend), in each mode
    def overlays():
        out = {}
        for mode in ("en", "vi", "envi"):
            q = f"?lang={mode}"
            ctx, pg, log = c.open("network-3d.html", query=q, ready_timeout=T_(240000))
            try:
                pg.evaluate("() => window.VLApp.selectById('333670')")
                pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '333670'", timeout=T_(120000))
                pg.wait_for_timeout(1200)
                meets = pg.evaluate(JS_OVERLAYS)
                if meets:
                    raise RuntimeError(f"45/2019/QH14 ({mode}): " + "; ".join(meets))
                out[f"network {mode}"] = "apart"
            finally:
                merge(log)
                ctx.close()
            ctx, pg, log = c.open("index.html", query=q)
            try:
                pg.wait_for_timeout(1200)
                pg.evaluate("() => window.VLApp.select('vlo:Article')")
                pg.wait_for_function("window.__VLONTO_METRICS.selected === 'vlo:Article'", timeout=T_(30000))
                pg.wait_for_timeout(1200)
                meets = pg.evaluate(JS_OVERLAYS)
                if meets:
                    raise RuntimeError(f"playground, vlo:Article open ({mode}): " + "; ".join(meets))
                out[f"playground {mode}"] = "apart"
            finally:
                merge(log)
                ctx.close()
        return out
    check("legend, status line, hint and stage tools apart with the details panel open (45/2019/QH14, the playground's vlo:Article) in EN, VI and EN–VI", overlays)
    res["log"] = logs
    return res


# ------------------------------------------------------------------ question traces (traces.html)
# the page's state as the tests read it (js/traces3d.js, window.__VLONTO_METRICS.traces): T.selected = the chosen traces'
# keys '<area>:<rank>' in the list's order; T.current = the trace the hop panel shows (key, question, provision, law,
# term and area nodes); T.panel = the key whose hop panel is open (its area file loaded); T.network = the network drawn
# (dataset, documents, the traced laws the lite network lacks); M.nodes / M.edges = the points and links of the network
JS_TRACES = """() => { const M = window.__VLONTO_METRICS || {}, T = M.traces || {}, pn = document.getElementById('panel'), l = document.getElementById('tr-list');
  const items = Array.from(l.querySelectorAll('.tr-item')), groups = Array.from(l.querySelectorAll('.tr-group')), st = pn.querySelector('.tr-step-n');
  const key = b => b.getAttribute('data-area') + ':' + b.getAttribute('data-rank'), clr = document.getElementById('tr-clear');
  return { available: T.available, webgl: T.webgl, fallback: T.fallback, graph: T.graph, network: T.network || null, loaded: (T.loaded || []).slice(),
    listItems: items.length, groups: groups.length, groupSizes: groups.map(s => s.querySelectorAll('.tr-item').length),
    groupOrder: groups.map(s => s.getAttribute('data-area')), shownItems: items.filter(b => !b.closest('li').hidden).length,
    picks: l.querySelectorAll('.tr-pick').length, alls: l.querySelectorAll('.tr-head .tr-all').length,
    tabs: document.querySelectorAll('[role=tab]').length, query: T.query, count: (document.getElementById('tr-count') || {}).textContent || '',
    clearShown: !!clr && !clr.hidden, current: items.filter(b => b.getAttribute('aria-current') === 'true').map(b => b.id),
    chosenRows: items.filter(b => b.closest('li').classList.contains('is-chosen')).map(key),
    pressed: Array.from(l.querySelectorAll('.tr-pick[aria-pressed="true"]')).map(key),
    allPressed: Array.from(l.querySelectorAll('.tr-all[aria-pressed="true"]')).map(b => b.getAttribute('data-area')),
    selected: (T.selected || []).slice(), cur: T.current || null, panelKey: T.panel || null, step: st ? st.textContent.trim() : null,
    segments: T.traceSegments, verified: T.traceVerified, structural: T.traceStructural, hops: T.hops, edgeCost: T.edgeCost || null,
    nodes: M.nodes, edges: M.edges, light: T.light, writes: T.selectionWrites, labels: T.labels, flights: T.flights, fps: T.fps,
    themeRenders: T.themeRenders, clicked: T.clicked || null, hover: T.hover || null, scrolledTo: T.scrolledTo || null,
    sideOpen: document.getElementById('app').classList.contains('side-open'), panelOpen: !pn.classList.contains('hidden'),
    panelHops: pn.querySelectorAll('.hop').length, hash: decodeURIComponent(location.hash),
    active: document.activeElement ? (document.activeElement.id || document.activeElement.className || document.activeElement.tagName) : null,
    traceScripts: Array.from(document.scripts).map(s => s.getAttribute('src') || '').filter(s => s.indexOf('data/traces/') === 0).sort(),
    netScripts: Array.from(document.scripts).map(s => s.getAttribute('src') || '').filter(s => s.indexOf('data/legal_network') === 0).sort() }; }"""
# what the network file the page drew holds: its documents, the links drawn under network-3d.html's policy (change and
# basis links; the citation links on the lite network only), site_meta's document count
JS_NET_WANT = """() => { const T = window.__VLONTO_METRICS.traces, full = (T.network || {}).dataset === 'full', V = window.VLONTO;
  const data = V[full ? 'legal_network' : 'legal_network_lite'] || {}, de = data.edges || {};
  return { full, meta: ((V.site_meta || {}).kg_counts || {}).documents, fileDocs: (data.nodes || []).length,
    links: (de.change || []).length + (de.basis || []).length + (full ? 0 : (de.citation || []).length) }; }"""
# the traced laws (VLApp.traces.laws()): each one's node, the network document it is, the position drawn, the network's
# position of that document and graph.js's own (tenths); the four laws the mapping names
JS_LAWS = """() => { const L = window.VLApp.traces.laws(), T = window.__VLONTO_METRICS.traces, n = T.network || {}, ZS = window.VL.NetScene.ZS;
  const inData = L.filter(l => !l.extra), same = inData.filter(l => l.docId === l.doc && l.pos.every((v, k) => v === l.docPos[k]));
  const dev = Math.max(...L.map(l => Math.max(Math.abs(l.data[0] - l.pos[0]), Math.abs(l.data[2] * ZS - l.pos[1]), Math.abs(l.data[1] - l.pos[2]))));
  const known = { 'wk:45/2019/QH14': '333670', 'wk:10/2012/QH13': '142187', 'wk:02/2011/QH13': '132446', 'wk:vbpl-115263': '115263' }, by = {};
  L.forEach(l => { by[l.node] = l; });
  return { laws: L.length, graphLaws: Object.keys(window.VLONTO.traces_graph.d).length, inData: inData.length, same: same.length,
    extra: L.length - inData.length, lawsInDataset: n.lawsInDataset, maxDev: Math.round(dev * 1000) / 1000,
    known: Object.keys(known).map(k => [k, known[k], (by[k] || {}).doc || null, (by[k] || {}).docId || null, !!(by[k] || {}).extra]),
    sample: inData.filter((l, i) => i % 60 === 0).map(l => [l.node, l.docId, l.pos, l.docPos]) }; }"""
# the scene's layers and planes: the six legal-force layers of network-3d.html (z_by_rank x ZS) with their names, the
# answers' and questions' planes under the lowest; graph.js's Q&A classes on their planes, the provision fans between
# the layers, one name node per area; no area cells (graph.js has no cell keys, the page no cell elements)
JS_LAYERS = """() => { const g = window.VLONTO.traces_graph, A = window.VLApp.traces, s = A.snapshot(), pl = g.planes, zOf = i => g.p[3 * i + 2] / 10;
  const onPlane = (c, z) => g.c.every((ci, i) => g.classes[ci] !== c || Math.abs(zOf(i) - z) < 0.06), ids = s.labels.map(l => l.id);
  const top = Math.max(...Object.values(g.net.z_by_rank)), fan = ['chapter', 'section', 'article', 'clause', 'point'];
  return { layers: s.layers.map(Math.round), want: [0, 1, 2, 3, 4, 5].map(r => Math.round(g.net.z_by_rank[r] * window.VL.NetScene.ZS)),
    qaPlanes: s.qaPlanes.map(Math.round), planes: pl,
    missingLabels: ['rank-0', 'rank-1', 'rank-2', 'rank-3', 'rank-4', 'rank-5', 'plane-answers', 'plane-questions'].filter(x => ids.indexOf(x) < 0),
    onPlanes: ['question', 'answer', 'term', 'other_question', 'area'].filter(c => !onPlane(c, pl[{ question: 'z_question', answer: 'z_answer',
      term: 'z_term', other_question: 'z_other', area: 'z_area' }[c]])),
    fanOutside: g.c.filter((ci, i) => fan.indexOf(g.classes[ci]) >= 0 && !(zOf(i) < top && zOf(i) > pl.z_answer)).length,
    belowLayers: pl.z_answer < Math.min(...Object.values(g.net.z_by_rank)), areaNodes: g.areas.length,
    areaClass: g.areas.every(a => g.classes[g.c[a.n]] === 'area'), cellKeys: ['h', 'ext', 'cols', 'cells', 'H'].filter(k => k in g),
    areaCellFields: g.areas.filter(a => 'c' in a || 'r' in a || 'cell' in a).length, cellElements: document.querySelectorAll('[data-cell], .tr-cell, .area-cell').length }; }"""
# the alphas the page holds for a choice (VLApp.traces.alphaState(): every alpha buffer's values and their counts, the
# link materials' opacities), two levels: exactly the chosen traces' nodes (graph.js t[].n) and the links among them at
# 1; with nothing chosen every document, trace node, link and stroke at the light alpha (T.light); while something is
# chosen every other trace node, trace link and the thin strokes at the faint alpha (T.faint) and the documents at the
# light one; each network link kind at its network-3d.html opacity times the light alpha, always; the bold paths and
# foreground nodes only while something is chosen. The materials (VLApp.traces.materials()): the trace nodes, the
# traces' and the network's links and the strokes transparent without depth write, the fragment's alpha the per-vertex
# alpha (strokes: their uniform opacity); the point size attributes the same as at the page's first call
JS_ALPHA = """(keys) => { const A = window.VLApp.traces, st = A.alphaState(), g = window.VLONTO.traces_graph, ids = A.areas();
  if (!st) return null;
  const r3 = x => Math.round(x * 1000) / 1000, L = st.light, F = st.faint, lk = String(r3(L)), fk = String(r3(F)), want = new Set(), NG = g.i.length;
  const any = keys.length > 0, R = any ? F : L, rk = any ? fk : lk;
  keys.forEach(k => { const [a, r] = k.split(':'); g.t.find(t => ids[t.a] === a && t.r === +r).n.forEach(i => want.add(i)); });
  if (!window.__vlTraceCtx) { const traced = new Set(), key = (a, b) => (a < b ? a * NG + b : b * NG + a), ctx = [];
    g.t.forEach(t => { for (let j = 0; j < t.e.length; j += 3) traced.add(key(t.e[j], t.e[j + 1])); });
    (g.kinds || Object.keys(g.e)).forEach(k => { const a = g.e[k] || []; for (let j = 0; j < a.length; j += 2) if (!traced.has(key(a[j], a[j + 1]))) ctx.push([a[j], a[j + 1]]); });
    window.__vlTraceCtx = { ctx, traced: traced.size }; }
  const C = window.__vlTraceCtx, works = Array.from(want).filter(i => g.classes[g.c[i]] === 'work').length;
  const ctxSolid = C.ctx.filter(([a, b]) => want.has(a) && want.has(b)).length;
  const only = (h, ks) => Object.keys(h).every(k => ks.indexOf(k) >= 0), n1 = h => h['1'] || 0;
  const net = Object.keys(st.netLinks).map(k => [k, st.netLinks[k].opacity, st.netLinks[k].base, Object.keys(st.netLinks[k].alphas).join()]);
  const netOk = net.every(x => Math.abs(x[1] - r3(x[2] * L)) < 2e-3 && x[3] === '1');
  const mats = A.materials(), M = {};
  mats.list.forEach(m => { M[m.name] = m; });
  const see = n => !!M[n] && M[n].transparent && !M[n].depthWrite, netMats = Object.keys(M).filter(n => n.indexOf('networkLinks.') === 0);
  const matOk = see('traceNodes') && M.traceNodes.alpha === 'vAlpha' && see('contextLinks') && /vAlpha/.test(M.contextLinks.alpha) &&
    ['halo2', 'halo', 'core'].every(k => see('strokes.' + k) && /uOpacity/.test(M['strokes.' + k].alpha)) &&
    netMats.length > 0 && netMats.every(n => see(n) && /vAlpha/.test(M[n].alpha));
  if (!window.__vlTraceSizes) window.__vlTraceSizes = JSON.stringify(mats.sizes);
  const sizeOk = JSON.stringify(mats.sizes) === window.__vlTraceSizes;
  const pass = st.chosenNodes === want.size && st.solidNodes === want.size && st.mismatched === 0 && st.untracedDocsNotLight === 0 &&
    only(st.docs, ['1', lk]) && only(st.traceNodes, ['1', rk]) && only(st.traceLinks, ['1', rk]) && (st.traceNodes[rk] || 0) > 0 &&
    n1(st.docs) === works && n1(st.traceNodes) === want.size - works && n1(st.traceLinks) === ctxSolid && netOk &&
    st.rest === r3(R) && st.strokes.opacity === r3(R) && st.strokes.traced === C.traced && matOk && sizeOk &&
    (keys.length ? st.bold.verified + st.bold.structural > 0 && st.fg > 0 : st.bold.verified + st.bold.structural === 0 && st.fg === 0);
  return { pass, light: L, faint: F, rest: st.rest, want: want.size, works, ctxSolid, docs: st.docs, traceNodes: st.traceNodes, traceLinks: st.traceLinks,
    mismatched: st.mismatched, untracedDocsNotLight: st.untracedDocsNotLight, netLinks: net, strokes: st.strokes, bold: st.bold, fg: st.fg, writes: st.writes,
    matOk, sizeOk, sizes: mats.sizes, materials: mats.list.map(m => [m.name, m.transparent, m.depthWrite, m.alpha]) }; }"""
TRACE_LIGHT = 0.3       # js/traces3d.js LIGHT: everything with nothing chosen, the network always (the v1.2 report's model renders)
TRACE_FAINT = 0.12      # js/traces3d.js FAINT: the traces not chosen while some are chosen (the v1.3 report's model renders)
# the choice is `keys` (any order) with `cur` shown in the hop panel (its area file loaded) and the scene settled
JS_CHOICE = """(a) => { const T = window.__VLONTO_METRICS.traces, s = T.selected || [], c = T.current;
  return s.length === a.keys.length && a.keys.every(k => s.indexOf(k) >= 0) && (!a.cur || (!!c && c.key === a.cur && T.panel === a.cur)) &&
    window.VLApp.traces.settle(); }"""
# a selection is complete when the hop panel shows it (five hops), the scene has settled and a call-out run newer than
# `runs` shows the question's call-out (or the question's node lies under the open hop panel: occluded, no call-out to
# wait for - the page's map is static and the panel may cover its right part; the panel's box grown by the 4 px the
# page keeps call-outs clear of overlays)
JS_TRACE_DONE = """(a) => { const M = window.__VLONTO_METRICS, T = M.traces, S = T.current, C = M.callouts;
  if (!(!!S && S.area === a.area && S.rank === a.rank && T.panel === a.area + ':' + a.rank && T.traceSegments > 0 && T.hops === 5 &&
    window.VLApp.traces.settle() && !!C && C.runs > a.runs)) return false;
  if (C.placed.some(p => p.id === S.q && p.sel)) return true;
  const pt = window.VLApp.traces.project(S.q), h = document.getElementById('canvas-host').getBoundingClientRect(), pn = document.getElementById('panel');
  const r = pn && !pn.classList.contains('hidden') ? pn.getBoundingClientRect() : null;
  return !!pt && !!r && r.width > 1 && pt.x >= r.left - h.left - 4 && pt.x <= r.right - h.left + 4 && pt.y >= r.top - h.top - 4 && pt.y <= r.bottom - h.top + 4; }"""
# Zoom to selection: every foreground node of the chosen traces projected inside the free part of the canvas
JS_ZOOM_FIT = """() => { const A = window.VLApp.traces, g = window.VLONTO.traces_graph, ids = A.areas(), v = A.view(), T = window.__VLONTO_METRICS.traces;
  const fg = new Set(); (T.selected || []).forEach(k => { const [a, r] = k.split(':'); g.t.find(x => ids[x.a] === a && x.r === +r).f.forEach(i => fg.add(i)); });
  const f = v.free, out = Array.from(fg).filter(i => { const p = A.project(g.i[i]);
    return !(p && p.inside && p.x >= f.x0 - 2 && p.x <= f.x1 + 2 && p.y >= f.y0 - 2 && p.y <= f.y1 + 2); });
  return { fg: fg.size, outside: out.length, examples: out.slice(0, 5).map(i => g.i[i]), free: f }; }"""
HOME_CAM = "() => { const v = window.VLApp.traces.view(); return [v.homeView.pos, v.homeView.target].map(a => a.map(x => Math.round(x * 100) / 100)); }"
# the must-show call-outs of the shown trace (the question; the provision; on wide screens the law): each one's node on
# the canvas (VLApp.traces.project, CSS px in the canvas host), placed or not, and the open hop panel's box in the same
# coordinates (getBoundingClientRect)
JS_TRACE_MUSTS = """() => { const A = window.VLApp.traces, s = A.snapshot(), C = window.__VLONTO_METRICS.callouts || {};
  const h = document.getElementById('canvas-host').getBoundingClientRect(), pn = document.getElementById('panel');
  const r = pn && !pn.classList.contains('hidden') ? pn.getBoundingClientRect() : null, placed = new Set((C.placed || []).map(p => p.id));
  return { canvas: [h.width, h.height], panel: r && r.width > 1 ? [r.left - h.left, r.top - h.top, r.right - h.left, r.bottom - h.top] : null,
    musts: s.labels.filter(l => l.must).map(l => { const p = A.project(l.id);
      return { id: l.id, placed: placed.has(l.id), x: p ? p.x : null, y: p ? p.y : null, inside: !!(p && p.inside) }; }) }; }"""
PANEL_PAD = 4      # px: the page keeps call-outs this far from overlays (traces3d.js obstacles()), so a node this close
                   # to the hop panel is under it too


def trace_musts(pg):
    """the shown trace's must-show call-outs by geometry: (occluded, hidden on the free canvas, geometry). A must whose
    node lies under the open hop panel's box is occluded - the static map lets the panel cover its right part - and is
    not a fault; every other must without a place is (a node off the canvas included: the whole map is framed in view)."""
    g = pg.evaluate(JS_TRACE_MUSTS)
    P, (cw, ch) = g["panel"], g["canvas"]

    def under(m):
        return (P is not None and m["x"] is not None and m["inside"] and 0 <= m["x"] <= cw and 0 <= m["y"] <= ch
                and P[0] - PANEL_PAD <= m["x"] <= P[2] + PANEL_PAD and P[1] - PANEL_PAD <= m["y"] <= P[3] + PANEL_PAD)
    occluded = [m["id"] for m in g["musts"] if not m["placed"] and under(m)]
    free_hidden = [m["id"] for m in g["musts"] if not m["placed"] and not under(m)]
    return occluded, free_hidden, g


# the search as the page runs it (js/traces3d.js fold / words / hasWord / applySearch), checked against what the list
# shows: in every shown entry each word of the query (no case, no diacritics, đ -> d, its edge punctuation dropped) starts
# a word (letters and digits) of its title, gloss, law names or number or area names, and in no hidden entry
JS_SEARCH_CHECK = """(q) => { const fold = s => String(s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();
  const A = {}; (window.VLONTO.traces_index.areas || []).forEach(a => { A[a.id] = a.label_vi + ' ' + a.label_en; });
  const toks = fold(q).split(/\\s+/).map(w => w.replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, '')).filter(Boolean), items = Array.from(document.querySelectorAll('#tr-list .tr-item'));
  const starts = (hay, w) => { for (let i = hay.indexOf(w); i >= 0; i = hay.indexOf(w, i + 1)) if (i === 0 || !/[a-z0-9]/.test(hay[i - 1])) return true; return false; };
  const hit = b => { const a = b.getAttribute('data-area'), x = window.VLApp.traces.question(a, +b.getAttribute('data-rank'));
    const hay = fold([x.vi, x.en, x.law.vi, x.law.en, x.law.number, A[a]].join(' ')); return toks.every(t => starts(hay, t)); };
  const shown = items.filter(b => !b.closest('li').hidden), hidden = items.filter(b => b.closest('li').hidden), none = document.getElementById('tr-none');
  return { n: shown.length, wrong: shown.filter(b => !hit(b)).slice(0, 3).map(b => b.id), missed: hidden.filter(hit).slice(0, 3).map(b => b.id),
    heads: Array.from(document.querySelectorAll('#tr-list .tr-group')).filter(s => !s.hidden).length, ids: shown.map(b => b.id),
    count: (document.getElementById('tr-count') || {}).textContent || '', none: none && !none.hidden ? none.textContent : null }; }"""
TRACE_PICKS = [("lao-dong-tien-luong", 3), ("thue-phi-le-phi", 5), ("bao-hiem", 8)]
# the language of what traces3d.js writes: list entries (title .tr-q, gloss .tr-g), the area headings (name, spoken
# count), the search (placeholder, label), the live count line, hop headings, legend
JS_TRACES_LANG = """() => { const M = window.__VLONTO_METRICS || {}, items = Array.from(document.querySelectorAll('#tr-list .tr-item')).slice(0, 20);
  const s = document.getElementById('tr-search'), c = document.getElementById('tr-count'), A = {};
  ((window.VLONTO.traces_index || {}).areas || []).forEach(a => { A[a.id] = [a.label_vi, a.label_en]; });
  return { lang: document.documentElement.getAttribute('data-lang'), labelsLang: M.labelsLang, items: items.length,
    glosses: items.filter(b => b.querySelector('.tr-g')).length,
    viTitles: items.filter(b => { const q = b.querySelector('.tr-q'); return !!q && q.getAttribute('lang') === 'vi'; }).length,
    hops: Array.from(document.querySelectorAll('#panel .hop h3')).map(e => e.textContent.replace(/\\s+/g, ' ').trim()),
    legend: (document.getElementById('legend') || {}).textContent || '',
    heads: Array.from(document.querySelectorAll('#tr-list .tr-group')).slice(0, 3).map(g => ({ area: g.getAttribute('data-area'),
      name: g.querySelector('.tr-head-name').textContent.replace(/\\s+/g, ' ').trim(), viPart: !!g.querySelector('.tr-head-name [lang=vi]'),
      spoken: (g.querySelector('.tr-head .sr-only') || {}).textContent || '', labels: A[g.getAttribute('data-area')],
      all: (g.querySelector('.tr-all') || {}).textContent || '' })),
    placeholder: s ? s.getAttribute('placeholder') : null, searchLabel: s ? s.getAttribute('aria-label') : null,
    clear: (document.getElementById('tr-clear') || {}).textContent || '',
    count: c ? c.textContent : '', countLive: c ? c.getAttribute('aria-live') : null }; }"""
# the side's strings in each mode (js/i18n-pages.js traces.search.* / traces.clear, js/i18n-3d.js tr3d.count /
# tr3d.chosen / tr3d.groupCount / tr3d.all; EN–VI shows the English of these ui / text keys)
TRACES_UI = {"en": {"placeholder": "Search questions, laws, areas", "count": "{n} of 540 questions", "chosen": "{n} chosen",
                    "spoken": "{n} questions", "all": "All 20", "clear": "Clear"},
             "vi": {"placeholder": "Tìm câu hỏi, văn bản, lĩnh vực", "count": "{n} trên 540 câu hỏi", "chosen": "đã chọn {n}",
                    "spoken": "{n} câu hỏi", "all": "Cả 20", "clear": "Bỏ chọn"}}


def traces_side_lang(s, mode, chosen=0):
    """faults of the headings, search, count line and Clear of a JS_TRACES_LANG state in a mode (chosen: the questions
    chosen, which the count line adds as '· n chosen')"""
    ui, bad = TRACES_UI["vi" if mode == "vi" else "en"], []
    for h in s["heads"]:
        vi, en = h["labels"]
        want = en if mode == "en" else vi if mode == "vi" else f"{vi} · {en}"
        if h["name"] != want or (mode == "envi" and not h["viPart"]):
            bad.append(f"heading {h['area']}: {h['name']!r}, expected {want!r}")
        if h["spoken"] != ui["spoken"].format(n=20):
            bad.append(f"heading {h['area']} count reads {h['spoken']!r}")
        if h["all"].strip() != ui["all"]:
            bad.append(f"heading {h['area']} button reads {h['all']!r}")
    if s["placeholder"] != ui["placeholder"]:
        bad.append(f"search placeholder {s['placeholder']!r}")
    want_count = ui["count"].format(n=540) + (" · " + ui["chosen"].format(n=chosen) if chosen else "")
    if s["count"] != want_count or s["countLive"] != "polite":
        bad.append(f"count line {s['count']!r} (aria-live {s['countLive']}), expected {want_count!r}")
    if s["clear"].strip() != ui["clear"]:
        bad.append(f"Clear reads {s['clear']!r}")
    return bad


# the first-visit hint and the stage tools (top right) never overlap: null = hint not shown (nothing to check)
JS_HINT_CLASH = """() => {
  const h = document.getElementById('hint'), t = document.querySelector('.stage-tools');
  if (!h || !t || h.classList.contains('hidden') || getComputedStyle(h).display === 'none') return null;
  const a = h.getBoundingClientRect(), b = t.getBoundingClientRect();
  const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), v = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return (w > 0 && v > 0) ? {hint: [a.left, a.top, a.right, a.bottom].map(Math.round), tools: [b.left, b.top, b.right, b.bottom].map(Math.round)} : false;
}"""
# the trace's own pixels (trace_pixels): its navy (light) / off-white (dark) core outside the call-out boxes and the gold
# band next to that core; after a choice from the list as the difference to the same view with nothing chosen, for a deep
# link as they are. Lower bounds re-derived for the v1.2 scene (the bold trace over the whole network, its core 4.2 px)
# from model renders of the CI views (tools_lang3d/px12.py, render12.py): the three picks add 1,380-1,660 core and
# 2,741-3,597 gold pixels at 1440 x 900 (full network, light) and 1,549-2,073 / 3,893-3,997 on a 390 x 844 phone (lite,
# 2 device px per CSS px); the deep link counts 1,769-3,953 core and 3,396-7,309 gold pixels (both themes); about a fifth
# of the smallest, for rendering differences (antialiasing, SwiftShader's line rasteriser, call-outs over the trace)
TRACE_PX_MIN = {"core": 250, "halo": 500}


def t_traces(c: Ctx):
    """traces.html (v1.3): the whole 3D legal network of network-3d.html with all 540 traced answers and 27 areas in it,
    everything at the light alpha with nothing chosen; the chosen traces opaque, the other traces at the faint alpha and
    the network at the light one while some are chosen (js/traces3d.js; data/traces/graph.js and the
    network's data file: data/legal_network.js on wide screens, data/legal_network_lite.js on phones, as network-3d.html).
    The scene: the network's documents (site_meta's count; on phones the lite file's, plus the traced laws it lacks) and
    links, its six layers and the answers' and questions' planes, no area cells; every traced law is its network document
    at the network's coordinates (all of them, a sample shown). One side list of the 540 questions under 27 area headings
    with a search (VI / EN, diacritic-insensitive; 'n of 540') and arrow keys, a round button per row, the heading's
    All 20, Clear. Load: nothing chosen, everything at the light alpha; the trace layer's materials see-through (no depth
    write, the per-vertex alpha). Three questions chosen from the list: exactly each one's trace opaque, the other traces
    faint, the point sizes as at load, its pixels lit, call-outs clean (the must-show ones on the free canvas; under the open hop
    panel occluded), the hop panel's five boxes. Several: the round button, Space and Ctrl/Cmd-click add and remove, the
    heading's All 20 chooses exactly its 20, the stepper walks them ('3 of 20') without writing the alphas again; Zoom to
    selection frames every chosen trace, Reset view returns home and keeps the choice; Clear. A click on a question node
    chooses it (hover: its question), Ctrl-click adds one, a click on another node opens its details; Escape clears;
    deep links (#q=a:r, #q=a:r1,r2;b:r3, #area=a&all=1[&q=r], v1's #area=a&q=r per theme with the theme switch, #area=a
    alone: the list at the area, nothing chosen); one static camera (choosing, searching and the list leave it); EN and
    VI; no page wider than the screen, no console errors; screenshots. The main load draws the full network on wide
    screens; the per-theme and per-language loads ask for the lite network (#ds=lite, what phones get anyway)."""
    res = {"test": "traces", "checks": []}
    logs = {"console_errors": [], "page_errors": [], "failed_requests": [], "external_requests": []}
    CAM = "() => { const c = window.VLApp.traces.camera(); return c ? [c.pos, c.target].map(v => v.map(x => Math.round(x * 100) / 100)) : null; }"
    MOVES = "() => window.__VLONTO_METRICS.traces.cameraMoves || 0"
    LITE = "ds=lite"       # the extra loads: the lite network (6,000 documents, what phones load) keeps the group's time

    def merge(log):
        for k in logs:
            logs[k] += log.get(k, [])

    def check(name, fn, pg=None):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            det = fail_details(e, c, pg, name) if pg is not None else {"error": str(e)[:1200]}
            res["checks"].append({"name": name, "pass": False, "details": det, "s": round(time.time() - t0, 2)})

    def runs(pg):
        return (pg.evaluate(JS_CALLOUTS) or {}).get("runs", 0)

    def side(pg, open_):
        """phones: the list (with its search) is a sheet behind the 'Questions' button"""
        if c.mobile and pg.evaluate("() => document.getElementById('app').classList.contains('side-open')") != open_:
            pg.locator("#btn-list-m").click()

    def clear(pg):
        """nothing chosen (Escape; on phones it first closes an open sheet)"""
        for _ in range(2):
            if not pg.evaluate("() => (window.__VLONTO_METRICS.traces.selected || []).length > 0 || document.getElementById('app').classList.contains('side-open')"):
                break
            pg.keyboard.press("Escape")
        pg.wait_for_function("() => !(window.__VLONTO_METRICS.traces.selected || []).length && window.VLApp.traces.settle()", timeout=T_(30000))

    def choice(pg, keys, cur=None, timeout=T_(90000)):
        pg.wait_for_function(JS_CHOICE, arg={"keys": list(keys), "cur": cur}, timeout=timeout)

    def select(pg, area, rank):
        """a click on the question's row: it alone is chosen"""
        r0 = runs(pg)
        side(pg, True)
        pg.locator(f"#tr-item-{area}-{rank}").click()
        pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": r0}, timeout=T_(90000))
        return pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS)

    def alpha(pg, keys, where):
        a = pg.evaluate(JS_ALPHA, list(keys))
        if not a or not a["pass"] or abs(a["light"] - TRACE_LIGHT) > 1e-9 or abs(a["faint"] - TRACE_FAINT) > 1e-9:
            raise RuntimeError(f"{where}: alphas {json.dumps(a)[:1200]}")
        return {k: a[k] for k in ("light", "faint", "rest", "want", "works", "ctxSolid", "docs", "traceNodes", "traceLinks", "netLinks", "bold", "fg",
                                  "sizes", "materials")}

    def judge(s, co, where, pg):
        """the shown trace: drawn, five hops, list entry marked, call-outs clean (the question's never forced on desktop).
        The must-show call-outs (question, provision; the law on wide screens) are judged by geometry: one whose node
        lies under the open hop panel is occluded, not a fault (the static map lets the panel cover its right part);
        every must on the free canvas has its call-out (trace_musts)"""
        S = s["cur"] or {}
        faults = callout_faults(co, must=False)
        occluded, free_hidden, geo = trace_musts(pg)
        if free_hidden:
            faults.append(f"{len(free_hidden)} must-show call-outs hidden on the free canvas: {free_hidden[:4]}")
        q = [p for p in co.get("placed", []) if p["id"] == S.get("q")]
        if S.get("q") not in occluded and (not q or (q[0]["forced"] and not c.mobile)):
            faults.append(f"question call-out {'forced' if q else 'missing'}")
        if co.get("shown", 0) < len(geo["musts"]) - len(occluded):
            faults.append(f"only {co.get('shown')} call-outs shown for {len(geo['musts']) - len(occluded)} must-show ones on the free canvas")
        hash_ = re.sub(r"&ds=\w+", "", s["hash"])          # one chosen: its deep link (several: the caller checks it)
        one = len(s["selected"]) == 1 and hash_ not in (f"#q={S.get('area')}:{S.get('rank')}", f"#area={S.get('area')}&q={S.get('rank')}")
        if (s["segments"] < 3 or s["panelHops"] != 5 or not s["panelOpen"] or s["current"] != [f"tr-item-{S.get('area')}-{S.get('rank')}"]
                or one):
            faults.append(f"segments {s['segments']}, hops {s['panelHops']}, panel {s['panelOpen']}, list {s['current']}, hash {s['hash']}")
        if faults:
            raise RuntimeError(f"{where}: {'; '.join(faults)}; call-outs {callout_summary(co)}")
        return {"current": {k: S.get(k) for k in ("key", "q", "provision", "law", "term", "areaNode", "fg", "segments")},
                "verified_segments": s["verified"], "structural_segments": s["structural"], "callouts": callout_summary(co),
                "placed": [p["id"] for p in co["placed"]], "occluded_by_panel": occluded, "panel": geo["panel"]}

    def pixels_lit(before, after, where):
        """the trace's own pixels: its core outside the call-out boxes and the gold band next to that core, against the
        same view with nothing chosen (a raw gold count also follows the pale answer nodes)"""
        d_core = after["core_out"] - before["core_out"]
        d_halo = after["halo_near_core"] - before["halo_near_core"]
        if d_core < TRACE_PX_MIN["core"] or d_halo < max(TRACE_PX_MIN["halo"], d_core // 2):
            raise RuntimeError(f"{where}: trace pixels {before} -> {after} (core +{d_core}, halo +{d_halo}; minimum {TRACE_PX_MIN})")
        return {"core": d_core, "halo": d_halo}

    ctx, pg, log = c.open("traces.html", ready_timeout=T_(240000))
    try:
        clash0 = pg.evaluate(JS_HINT_CLASH)
        if clash0:
            raise RuntimeError(f"on load the first-visit hint overlaps the stage tools: {clash0}")
        cam_load, home_load = pg.evaluate(CAM), pg.evaluate(HOME_CAM)     # framed as loaded (with the hint shown)
        if pg.evaluate("() => { const h = document.getElementById('hint'); return !!h && !h.classList.contains('hidden'); }"):
            pg.locator("#hint-close").click()             # the first-visit hint: dismissed like a visitor would

        def network():
            s, w = pg.evaluate(JS_TRACES), pg.evaluate(JS_NET_WANT)
            n, full, prob = s["network"] or {}, not c.mobile, []
            if n.get("dataset") != ("full" if full else "lite") or w["full"] != full:
                prob.append(f"dataset {n.get('dataset')}")
            if n.get("docs") != w["fileDocs"] or (full and n.get("docs") != w["meta"]):
                prob.append(f"{n.get('docs')} documents drawn; the file holds {w['fileDocs']}, site_meta counts {w['meta']}")
            if n.get("points") != n.get("docs", 0) + n.get("extra", 0) or s["nodes"] != n.get("points"):
                prob.append(f"points {n.get('points')} (documents {n.get('docs')} + traced laws the file lacks {n.get('extra')}), drawn {s['nodes']}")
            if (n.get("extra") != 0) if full else (n.get("extra", 0) <= 0 or n.get("extra") != n.get("laws", 0) - n.get("lawsInDataset", 0)):
                prob.append(f"extra law nodes {n.get('extra')} (traced laws {n.get('laws')}, in the file {n.get('lawsInDataset')})")
            if s["edges"] != w["links"] or (s["edgeCost"] or {}).get("links") != w["links"]:
                prob.append(f"{s['edges']} links drawn, {w['links']} in the file under network-3d.html's policy")
            if s["netScripts"] != ["data/legal_network.js" if full else "data/legal_network_lite.js"]:
                prob.append(f"network scripts {s['netScripts']}")
            if prob:
                raise RuntimeError("; ".join(prob))
            return {"network": n, "file": w, "links": s["edges"], "edge_cost": s["edgeCost"], "fps": s["fps"]}
        check("the scene is the whole legal network of network-3d.html: its documents (site_meta's count on wide screens; the "
              "lite file's on phones, plus the traced laws it lacks) and its links under the same policy", network, pg)

        def laws():
            r = pg.evaluate(JS_LAWS)
            bad = [k for k in r["known"] if k[2] != k[1] or not (k[4] or k[3] == k[1])]
            if (r["laws"] != r["graphLaws"] or r["same"] != r["inData"] or r["inData"] != r["lawsInDataset"]
                    or (not c.mobile and r["extra"] != 0) or r["maxDev"] >= 0.12 or bad):
                raise RuntimeError(f"laws {json.dumps({k: v for k, v in r.items() if k != 'sample'})}; known laws wrong: {bad}")
            return r
        check("every traced law is its network document (one node; by the trace data's document id where numbers repeat) at the "
              "network's coordinates: all of them counted, a sample listed", laws, pg)

        def layers():
            r = pg.evaluate(JS_LAYERS)
            if (r["layers"] != r["want"] or r["missingLabels"] or r["onPlanes"] or r["fanOutside"] or not r["belowLayers"]
                    or r["areaNodes"] != 27 or not r["areaClass"] or r["cellKeys"] or r["areaCellFields"] or r["cellElements"]
                    or not r["qaPlanes"][0] > r["qaPlanes"][1]):
                raise RuntimeError(json.dumps(r)[:900])
            return r
        check("the six legal-force layers with their names and, under the lowest, the answers' and questions' planes; Q&A nodes "
              "on their planes, provision fans under their laws, one name node per area; no area cells", layers, pg)

        def one_place():
            s = pg.evaluate(JS_TRACES)
            areas = pg.evaluate("window.VLApp.traces.areas()")
            a0 = alpha(pg, [], "load")
            cam, home = cam_load, home_load
            ok = (s["available"] and s["webgl"] and not s["fallback"] and s["tabs"] == 0 and s["listItems"] == 540 and s["groups"] == 27
                  and s["groupSizes"] == [20] * 27 and s["groupOrder"] == areas and s["shownItems"] == 540 and s["picks"] == 540
                  and s["alls"] == 27 and s["count"] == "540 of 540 questions" and not s["clearShown"]
                  and (s["graph"] or {}).get("traces") == 540 and (s["graph"] or {}).get("nodes", 0) > 10000
                  and (s["edgeCost"] or {}).get("curves") and s["edgeCost"]["segments"] > s["edgeCost"]["links"]
                  and not s["selected"] and not s["cur"] and not s["panelOpen"] and s["labels"] == 27 + 8 and cam == home)
            if not ok:
                raise RuntimeError(f"state {json.dumps({k: v for k, v in s.items() if k not in ('network',)}, ensure_ascii=False)[:900]}; camera {cam}, home {home}")
            return {"list": s["listItems"], "groups": s["groups"], "count": s["count"], "graph": s["graph"], "fps": s["fps"],
                    "edge_cost": s["edgeCost"], "callouts": s["labels"], "alpha": a0, "camera": cam}
        check("load: one list of the 540 questions under 27 area headings (a round button per row, All 20 per heading, no tabs, "
              "'540 of 540'); nothing chosen; every document, trace node, link and stroke at the light alpha (the trace layer "
              "drawn see-through: transparent, no depth write, the per-vertex alpha); the 27 areas, "
              "six layers and two planes named; the camera at the home view", one_place, pg)

        def side_scroll():
            side(pg, True)
            box = pg.evaluate("""() => { const sd = document.getElementById('side'), items = sd.querySelectorAll('.tr-item'), last = items[items.length - 1];
                last.scrollIntoView({ block: 'nearest' });
                const r = last.getBoundingClientRect(), s = sd.getBoundingClientRect(), hd = sd.querySelector('.tr-side-head').getBoundingClientRect();
                return { inside: r.top >= s.top - 1 && r.bottom <= s.bottom + 1, overflowY: getComputedStyle(sd).overflowY, scroll: sd.scrollHeight,
                         client: sd.clientHeight, headAtTop: Math.abs(hd.top - s.top) <= 1.5, last: last.id }; }""")
            w = no_hscroll(c, pg, "traces")
            pg.evaluate("() => { document.getElementById('side').scrollTop = 0; }")
            side(pg, False)
            if box["overflowY"] not in ("auto", "scroll") or box["scroll"] <= box["client"] or not box["inside"] or not box["headAtTop"]:
                raise RuntimeError(f"side {box}")
            return {"side": box, "page_width": w}
        check("the list scrolls inside the side (the last entry reachable, the search head stays on top); the page is no wider "
              "than the screen", side_scroll, pg)

        def lazy():
            s = pg.evaluate(JS_TRACES)
            want = sorted(["data/traces/index.js", "data/traces/graph.js", "data/traces/questions.js"])
            if s["traceScripts"] != want or s["loaded"]:
                raise RuntimeError(f"scripts {s['traceScripts']}, area files {s['loaded']}")
            return {"scripts": s["traceScripts"] + s["netScripts"]}
        check("on load the index, the graph, the questions file and the network's file are loaded (an area's file when one of "
              "its questions is chosen)", lazy, pg)

        def loading():
            # a choice waits for its area's file: the hop panel says so at once; closing the panel (its x, or Escape)
            # drops the choice, so it does not land when the file arrives
            clear(pg)          # on phones Escape first closes the list sheet: start with it closed
            out = pg.evaluate("""async () => {
              const A = window.VLApp.traces, pn = document.getElementById('panel'), M = window.__VLONTO_METRICS.traces;
              const fresh = A.areas().filter((a) => (M.loaded || []).indexOf(a) < 0), r = {};
              for (const [how, area] of [['close', fresh[0]], ['escape', fresh[1]]]) {
                const p = A.select(area, 1), st = pn.querySelector('.tr-status');
                const x = { area, open: !pn.classList.contains('hidden'), status: st ? st.textContent.trim() : null };
                if (how === 'close') pn.querySelector('[data-close]').click();
                else document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                await p;
                Object.assign(x, { selected: (M.selected || []).slice(), closed: pn.classList.contains('hidden'), segments: M.traceSegments, hash: location.hash });
                r[how] = x;
              }
              return r; }""")
            bad = [f"{k}: {v}" for k, v in out.items() if not v["open"] or "Loading" not in (v["status"] or "") or v["selected"]
                   or not v["closed"] or v["segments"] or "q=" in v["hash"]]
            if bad:
                raise RuntimeError("; ".join(bad))
            return out
        check("a question whose area file is not loaded yet: the hop panel says 'Loading' at once; closing it (x or Escape) drops "
              "the choice", loading, pg)

        def legend():
            if c.mobile:
                pg.locator("#btn-legend").click()
            L = pg.evaluate("""() => { const l = document.querySelector('[data-legend]'); if (!l) return null; const r = l.getBoundingClientRect();
                return { entries: l.querySelectorAll('li').length, text: l.textContent.replace(/\\s+/g, ' '), visible: r.width > 0 && r.height > 0,
                  flat: Array.from(l.querySelectorAll('.swatch:not(.trace)')).every(s => getComputedStyle(s).backgroundImage === 'none') }; }""")
            if c.mobile:
                pg.locator("#btn-legend").click()
            need = ("Văn bản", "Document", "Liên kết", "Links", "Đường truy vết", "Traced answer", "Structure only", "Not chosen (light)")
            if not L or not L["visible"] or L["entries"] != 11 or not L["flat"] or any(n not in L["text"] for n in need):
                raise RuntimeError(f"legend {L}")
            return {"entries": L["entries"], "flat_swatches": L["flat"]}
        check("flat bilingual legend: documents, their links, provisions, terms, Q&A, area, other answers, the traced and the "
              "structural path, the light rest", legend, pg)

        def search():
            side(pg, True)
            c0, m0 = pg.evaluate(CAM), pg.evaluate(MOVES)
            out = {}
            for k, q in (("vi", "thue"), ("vi_marks", "thuế"), ("en", "retirement"), ("none", "zzqxv")):
                pg.fill("#tr-search", q)
                pg.wait_for_function("(q) => window.__VLONTO_METRICS.traces.query === q", arg=q, timeout=T_(15000))
                r = pg.evaluate(JS_SEARCH_CHECK, q)
                out[k] = {"q": q, "n": r["n"], "count": r["count"], "heads": r["heads"], "wrong": r["wrong"], "missed": r["missed"], "none": r["none"], "ids": r["ids"]}
            pg.fill("#tr-search", "")
            pg.wait_for_function("() => window.__VLONTO_METRICS.traces.query === '' && window.__VLONTO_METRICS.traces.shown === 540", timeout=T_(15000))
            c1, m1 = pg.evaluate(CAM), pg.evaluate(MOVES)
            side(pg, False)
            bad = [k for k, v in out.items() if v["wrong"] or v["missed"] or v["count"] != f"{v['n']} of 540 questions"]
            if (bad or not 0 < out["vi"]["n"] < 540 or out["vi"]["ids"] != out["vi_marks"]["ids"] or not 0 < out["en"]["n"] < 540
                    or out["none"]["n"] != 0 or out["none"]["heads"] != 0 or not out["none"]["none"] or "zzqxv" not in out["none"]["none"]
                    or c0 != c1 or m0 != m1):
                raise RuntimeError(f"search {json.dumps({k: {x: y for x, y in v.items() if x != 'ids'} for k, v in out.items()}, ensure_ascii=False)}; "
                                   f"faults {bad}; camera {c0} -> {c1}, moves {m0} -> {m1}")
            return {k: {x: y for x, y in v.items() if x != "ids"} for k, v in out.items()}
        check("search: a Vietnamese word with or without its diacritics, an English word and a query with no hit filter the list "
              "('n of 540' live line, empty headings hidden); the camera stays", search, pg)

        def three():
            out = []
            for area, rank in TRACE_PICKS:
                clear(pg)
                before = trace_pixels(pg, "#canvas-host", "light")
                s, co = select(pg, area, rank)
                d = judge(s, co, f"{area} #{rank}", pg)
                d["alpha"] = alpha(pg, [f"{area}:{rank}"], f"{area} #{rank}")
                after = trace_pixels(pg, "#canvas-host", "light")
                d["pixels"] = pixels_lit(before, after, f"{area} #{rank}")
                d.update({"area": area, "rank": rank, "raw_pixels": [before, after]})
                if area == TRACE_PICKS[0][0]:
                    d["shot"] = c.shot(pg, "traces_selected")
                out.append(d)
            return {"traces": out, "page_width": no_hscroll(c, pg, "traces with a trace selected")}
        check("three questions from the one list (three areas), one at a time: exactly its trace opaque (its nodes and the links "
              "among them at 1), the other traces' nodes, links and strokes at the faint alpha, the network's documents and "
              "links at the light one (each link kind at its network-3d.html opacity times it), point sizes as at load; its "
              "trace pixels lit; call-outs clean; five hops", three, pg)

        def node_click():
            S = pg.evaluate("window.__VLONTO_METRICS.traces.current")
            # the first of provision, law, term, area node whose projected centre is on the canvas itself (not under an overlay)
            hit = pg.evaluate("""(ids) => { const host = document.getElementById('canvas-host'), b = host.getBoundingClientRect();
                for (const id of ids) { if (!id) continue; const p = window.VLApp.traces.project(id);
                  if (!p || !p.inside) continue; const e = document.elementFromPoint(b.left + p.x, b.top + p.y);
                  if (e && e.tagName === 'CANVAS' && host.contains(e)) return { id, x: b.left + p.x, y: b.top + p.y }; }
                return null; }""", [S["provision"], S["law"], S["term"], S["areaNode"]])
            if not hit:
                raise RuntimeError(f"no node of the trace is clickable on the canvas: {S}")
            pg.mouse.click(hit["x"], hit["y"])
            pg.wait_for_function("() => !!window.__VLONTO_METRICS.traces.clicked && !!document.querySelector('#panel .kv')", timeout=T_(30000))
            s = pg.evaluate(JS_TRACES)
            # a document of the network no trace reaches: its details and its link to network-3d.html
            doc = pg.evaluate("""() => { const A = window.VLApp.traces, host = document.getElementById('canvas-host'), b = host.getBoundingClientRect();
                for (let gy = 0.15; gy < 0.85; gy += 0.035) for (let gx = 0.06; gx < 0.62; gx += 0.03) {
                  const x = b.left + gx * b.width, y = b.top + gy * b.height, e = document.elementFromPoint(x, y);
                  if (!e || e.tagName !== 'CANVAS' || !host.contains(e)) continue;
                  const id = A.pick(x, y); if (id && id.indexOf('doc:') === 0) return { id, x, y }; }
                return null; }""")
            if not doc:
                raise RuntimeError("no document of the network is clickable on the canvas")
            pg.mouse.click(doc["x"], doc["y"])
            pg.wait_for_function("(id) => window.__VLONTO_METRICS.traces.clicked === id && !!document.querySelector('#panel a[href*=\"network-3d.html#doc=\"]')",
                                 arg=doc["id"], timeout=T_(30000))
            return {"target": hit["id"], "clicked": s["clicked"], "same": s["clicked"] == hit["id"], "document": doc["id"]}
        check("a click on a node of the trace opens its details; a click on a document of the network opens its details with "
              "its link to the 3D legal network", node_click, pg)

        JS_Q_HIT = """(picks) => { const A = window.VLApp.traces, host = document.getElementById('canvas-host'), b = host.getBoundingClientRect();
            for (const [area, rank] of picks) { const q = A.question(area, rank), p = q && A.project(q.node);
              if (!p || !p.inside) continue;
              for (const [dx, dy] of [[0, 0], [2, 0], [-2, 0], [0, 2], [0, -2]]) { const x = b.left + p.x + dx, y = b.top + p.y + dy, e = document.elementFromPoint(x, y);
                if (e && e.tagName === 'CANVAS' && host.contains(e) && A.pick(x, y) === q.node) return { area, rank, node: q.node, x, y, vi: q.vi, en: q.en }; } }
            return null; }"""

        def click_question():
            clear(pg)
            c0, m0 = pg.evaluate(CAM), pg.evaluate(MOVES)
            # a question node on the canvas itself (not under an overlay) where the pick finds that question node
            hit = pg.evaluate(JS_Q_HIT, [list(p) for p in reversed(TRACE_PICKS)])
            if not hit:
                raise RuntimeError("no question node of the picks is clickable on the canvas")
            pg.mouse.move(hit["x"], hit["y"])
            pg.wait_for_function("(id) => window.__VLONTO_METRICS.traces.hover === id && !document.getElementById('tip').classList.contains('hidden')",
                                 arg=hit["node"], timeout=T_(15000))
            tip = pg.evaluate("() => document.getElementById('tip').querySelector('b').textContent")
            if hit["vi"][:30] not in tip or hit["en"][:30] not in tip:       # EN–VI: the title and its gloss
                raise RuntimeError(f"tooltip {tip!r} for {hit}")
            r0 = runs(pg)
            pg.mouse.click(hit["x"], hit["y"])
            pg.wait_for_function(JS_TRACE_DONE, arg={"area": hit["area"], "rank": hit["rank"], "runs": r0}, timeout=T_(90000))
            s = pg.evaluate(JS_TRACES)
            out = {"chose": [hit["area"], hit["rank"]], "tooltip": tip[:160], "hash": s["hash"]}
            if s["hash"] != f"#q={hit['area']}:{hit['rank']}" or s["selected"] != [f"{hit['area']}:{hit['rank']}"]:
                raise RuntimeError(f"after the click: hash {s['hash']}, chosen {s['selected']}")
            if not c.mobile:     # Ctrl-click on another question node adds it (phones have no Ctrl; their hop sheet covers the plane)
                others = [[a, r] for a, r in TRACE_PICKS if (a, r) != (hit["area"], hit["rank"])] + [["giao-duc", r] for r in range(1, 21)]
                hit2 = pg.evaluate(JS_Q_HIT, others)
                if not hit2:
                    raise RuntimeError("no other question node is clickable on the canvas")
                pg.keyboard.down("Control")
                pg.mouse.click(hit2["x"], hit2["y"])
                pg.keyboard.up("Control")
                keys = [f"{hit['area']}:{hit['rank']}", f"{hit2['area']}:{hit2['rank']}"]
                choice(pg, keys, keys[1])
                out["ctrl_click"] = {"added": keys[1], "alpha": alpha(pg, keys, "Ctrl-click in the scene")}
            c1, m1 = pg.evaluate(CAM), pg.evaluate(MOVES)
            if c0 != c1 or m0 != m1:
                raise RuntimeError(f"the camera moved: {c0} -> {c1}, moves {m0} -> {m1}")
            return out
        check("hover on a question node shows its question; a click on it chooses that question alone, Ctrl-click on another adds "
              "it (wide screens); the camera stays", click_question, pg)

        def keyboard():
            clear(pg)
            side(pg, True)
            first, second, last = pg.evaluate("() => { const it = Array.from(document.querySelectorAll('#tr-list .tr-item')); return [it[0].id, it[1].id, it[it.length - 1].id]; }")
            pg.focus("#tr-search")
            seen = []
            for key in ("ArrowDown", "ArrowDown", "End", "Home", "ArrowUp"):
                pg.keyboard.press(key)
                seen.append(pg.evaluate("() => document.activeElement && document.activeElement.id"))
            pg.keyboard.press("ArrowDown")
            pg.keyboard.press("ArrowDown")
            r0 = runs(pg)
            area0 = second.split("tr-item-")[1].rsplit("-", 1)[0]
            pg.keyboard.press("Enter")
            pg.wait_for_function(JS_TRACE_DONE, arg={"area": area0, "rank": 2, "runs": r0}, timeout=T_(90000))
            clear(pg)
            s3 = pg.evaluate(JS_TRACES)
            if seen != [first, second, last, first, "tr-search"] or s3["segments"] != 0 or "q=" in s3["hash"] or s3["current"] or s3["selected"]:
                raise RuntimeError(f"keys -> {seen} (want {[first, second, last, first, 'tr-search']}); after Escape {s3['segments']} segments, "
                                   f"hash {s3['hash']}, list {s3['current']}, chosen {s3['selected']}")
            return {"keys": seen, "chose": [area0, 2], "after_escape": s3["hash"]}
        check("keyboard: ArrowDown from the search into the list, arrows / End / Home, ArrowUp back to the search, Enter chooses, "
              "Escape clears", keyboard, pg)

        def several():
            clear(pg)
            c0, m0 = pg.evaluate(CAM), pg.evaluate(MOVES)
            s1, _ = select(pg, "lao-dong-tien-luong", 3)
            k1 = ["lao-dong-tien-luong:3"]
            if (s1["chosenRows"] != k1 or s1["pressed"] != k1 or s1["step"] is not None or not s1["clearShown"]
                    or s1["count"] != "540 of 540 questions · 1 chosen"):
                raise RuntimeError(f"one chosen: rows {s1['chosenRows']}, buttons {s1['pressed']}, stepper {s1['step']}, Clear {s1['clearShown']}, count {s1['count']!r}")
            # the round button adds a question: it is shown ('i of 2'), the hash lists it first
            side(pg, True)
            pg.locator('.tr-pick[data-area="bao-hiem"][data-rank="8"]').click()
            k2 = k1 + ["bao-hiem:8"]
            choice(pg, k2, "bao-hiem:8")
            s2 = pg.evaluate(JS_TRACES)
            a2 = alpha(pg, k2, "the round button adds")
            i2 = s2["selected"].index("bao-hiem:8") + 1
            if (s2["step"] != f"{i2} of 2" or s2["hash"] != "#q=bao-hiem:8;lao-dong-tien-luong:3" or sorted(s2["pressed"]) != sorted(k2)
                    or s2["count"] != "540 of 540 questions · 2 chosen"):
                raise RuntimeError(f"two chosen: stepper {s2['step']}, hash {s2['hash']}, buttons {s2['pressed']}, count {s2['count']!r}")
            # Space on a row adds its question (the row's own click cancelled: the rest stays chosen), the focus stays
            pg.locator("#tr-item-thue-phi-le-phi-5").focus()
            pg.keyboard.press("Space")
            k3 = k2 + ["thue-phi-le-phi:5"]
            choice(pg, k3, "thue-phi-le-phi:5")
            act = pg.evaluate("() => document.activeElement && document.activeElement.id")
            # Ctrl-click on a row adds, Cmd-click (Meta) removes; the round button removes
            pg.locator("#tr-item-giao-duc-4").click(modifiers=["Control"])
            choice(pg, k3 + ["giao-duc:4"], "giao-duc:4")
            pg.locator("#tr-item-giao-duc-4").click(modifiers=["Meta"])
            choice(pg, k3)
            pg.locator('.tr-pick[data-area="bao-hiem"][data-rank="8"]').click()
            k4 = ["lao-dong-tien-luong:3", "thue-phi-le-phi:5"]
            choice(pg, k4)
            a4 = alpha(pg, k4, "after the removals")
            s4 = pg.evaluate(JS_TRACES)
            side(pg, False)
            c1, m1 = pg.evaluate(CAM), pg.evaluate(MOVES)
            if act != "tr-item-thue-phi-le-phi-5" or sorted(s4["pressed"]) != sorted(k4) or sorted(s4["chosenRows"]) != sorted(k4) or c0 != c1 or m0 != m1:
                raise RuntimeError(f"focus {act}; buttons {s4['pressed']}, rows {s4['chosenRows']}; camera {c0} -> {c1}, moves {m0} -> {m1}")
            return {"two": {"step": s2["step"], "hash": s2["hash"], "alpha": a2}, "space_focus": act, "after": {"chosen": s4["selected"], "alpha": a4}}
        check("several questions: the round button, Space on a row and Ctrl-click add one (it is shown, 'i of n'), Cmd-click and "
              "the round button remove; exactly the chosen traces opaque after every change; the camera stays", several, pg)

        def area_all():
            side(pg, True)
            r0 = runs(pg)
            pg.locator("#tr-g-lao-dong-tien-luong .tr-all").click()
            k20 = [f"lao-dong-tien-luong:{r}" for r in range(1, 21)]
            pg.wait_for_function(JS_TRACE_DONE, arg={"area": "lao-dong-tien-luong", "rank": 1, "runs": r0}, timeout=T_(90000))
            side(pg, False)
            s, co = pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS)
            a = alpha(pg, k20, "All 20")
            if (sorted(s["selected"]) != sorted(k20) or s["allPressed"] != ["lao-dong-tien-luong"] or s["hash"] != "#area=lao-dong-tien-luong&all=1"
                    or s["step"] != "1 of 20" or len(s["chosenRows"]) != 20 or s["count"] != "540 of 540 questions · 20 chosen"):
                raise RuntimeError(f"All 20: chosen {len(s['selected'])}, heading {s['allPressed']}, hash {s['hash']}, stepper {s['step']}, "
                                   f"rows {len(s['chosenRows'])}, count {s['count']!r}")
            d1 = judge(s, co, "All 20 (#1 shown)", pg)
            shot = c.shot(pg, "traces_area_all")
            # the stepper: next twice -> '3 of 20' (#3 shown, its call-outs), back -> '2 of 20'; no alpha written again
            w0 = s["writes"]
            for r in (2, 3):
                r1 = runs(pg)
                pg.locator('#panel [data-step="1"]').click()
                pg.wait_for_function(JS_TRACE_DONE, arg={"area": "lao-dong-tien-luong", "rank": r, "runs": r1}, timeout=T_(90000))
            s3, co3 = pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS)
            d3 = judge(s3, co3, "All 20 (#3 shown)", pg)
            r1 = runs(pg)
            pg.locator('#panel [data-step="-1"]').click()
            pg.wait_for_function(JS_TRACE_DONE, arg={"area": "lao-dong-tien-luong", "rank": 2, "runs": r1}, timeout=T_(90000))
            s2 = pg.evaluate(JS_TRACES)
            alpha(pg, k20, "stepping")
            if (s3["step"] != "3 of 20" or s3["hash"] != "#area=lao-dong-tien-luong&all=1&q=3" or s2["step"] != "2 of 20"
                    or len(s2["selected"]) != 20 or s2["writes"] != w0):
                raise RuntimeError(f"stepper: {s3['step']} (hash {s3['hash']}), back {s2['step']}; chosen {len(s2['selected'])}; alpha writes {w0} -> {s2['writes']}")
            return {"alpha": a, "first": d1["callouts"], "third": {"placed": d3["placed"], "occluded": d3["occluded_by_panel"]}, "writes": w0, "shot": shot}
        check("an area heading's All 20 chooses exactly its 20 traces (all opaque, the other traces faint, the network light; heading pressed, #area=<id>&all=1, "
              "'1 of 20'); the stepper shows #3 ('3 of 20', its must-show call-outs) and back, without writing the alphas again", area_all, pg)

        def static_map():
            """one static map: searching and further list use change the drawing only (the camera stays, and the page makes no
            camera move of its own); Zoom to selection frames every chosen trace; Reset view returns to the home view and
            keeps the choice"""
            flights = "() => window.__VLONTO_METRICS.traces.flights || 0"
            c0, m0 = pg.evaluate(CAM), pg.evaluate(MOVES)
            side(pg, True)
            pg.fill("#tr-search", "lao dong")
            pg.wait_for_function("() => window.__VLONTO_METRICS.traces.query === 'lao dong'", timeout=T_(15000))
            c1, m1 = pg.evaluate(CAM), pg.evaluate(MOVES)
            pg.fill("#tr-search", "")
            pg.wait_for_function("() => window.__VLONTO_METRICS.traces.query === ''", timeout=T_(15000))
            side(pg, False)
            if not (c0 == c1) or not (m0 == m1):
                raise RuntimeError(f"the camera moved: search {c0} -> {c1}; camera moves by the page {m0}, {m1}")
            f0 = pg.evaluate(flights)
            pg.locator("#btn-zoom").click()
            pg.wait_for_function("(f) => (window.__VLONTO_METRICS.traces.flights || 0) > f && window.VLApp.traces.settle()", arg=f0, timeout=T_(30000))
            c2, z = pg.evaluate(CAM), pg.evaluate(JS_ZOOM_FIT)
            if c2 == c1 or z["outside"] or z["fg"] < 20:
                raise RuntimeError(f"Zoom to selection: camera {c1} -> {c2}, {z['outside']} of {z['fg']} foreground nodes outside the free canvas {z}")
            shot = c.shot(pg, "traces_zoom")
            f1 = pg.evaluate(flights)
            pg.locator("#btn-reset-m" if c.mobile else "#btn-reset").click()
            pg.wait_for_function("(f) => (window.__VLONTO_METRICS.traces.flights || 0) > f && window.VLApp.traces.settle()", arg=f1, timeout=T_(30000))
            c3, home, s = pg.evaluate(CAM), pg.evaluate(HOME_CAM), pg.evaluate(JS_TRACES)
            if c3 != home or len(s["selected"]) != 20:
                raise RuntimeError(f"Reset view: camera {c3}, home {home}, chosen {len(s['selected'])}")
            return {"camera": c0, "zoomed": c2, "fit": z, "home": c3, "moves": [m0, m1], "shot": shot}
        check("one static map: searching leaves the camera where it is; Zoom to selection frames all 20 chosen traces (every "
              "foreground node in the free canvas); Reset view returns home and keeps the choice", static_map, pg)

        def clear_button():
            side(pg, True)
            pg.locator("#tr-clear").click()
            pg.wait_for_function("() => !(window.__VLONTO_METRICS.traces.selected || []).length && window.VLApp.traces.settle()", timeout=T_(30000))
            s = pg.evaluate(JS_TRACES)
            a = alpha(pg, [], "Clear")
            side(pg, False)
            if (s["hash"] or s["panelOpen"] or s["clearShown"] or s["chosenRows"] or s["pressed"] or s["allPressed"]
                    or s["count"] != "540 of 540 questions" or s["segments"]):
                raise RuntimeError(f"after Clear: hash {s['hash']!r}, panel {s['panelOpen']}, Clear {s['clearShown']}, rows {s['chosenRows']}, "
                                   f"heading {s['allPressed']}, count {s['count']!r}, segments {s['segments']}")
            return {"alpha": a}
        check("Clear: nothing chosen, every alpha light again, no deep link, the panel closed, Clear hidden", clear_button, pg)

        def links():
            clear(pg)
            c0, m0 = pg.evaluate(CAM), pg.evaluate(MOVES)
            all20 = lambda a: [f"{a}:{r}" for r in range(1, 21)]  # noqa: E731
            forms = [("#q=bao-hiem:8", ["bao-hiem:8"], "bao-hiem:8"),
                     ("#q=lao-dong-tien-luong:3,5", ["lao-dong-tien-luong:3", "lao-dong-tien-luong:5"], "lao-dong-tien-luong:3"),
                     ("#q=lao-dong-tien-luong:7,2;bao-hiem:8", ["lao-dong-tien-luong:7", "lao-dong-tien-luong:2", "bao-hiem:8"], "lao-dong-tien-luong:7"),
                     ("#area=thue-phi-le-phi&all=1", all20("thue-phi-le-phi"), "thue-phi-le-phi:1"),
                     ("#area=thue-phi-le-phi&all=1&q=6", all20("thue-phi-le-phi"), "thue-phi-le-phi:6"),
                     ("#area=thue-phi-le-phi&q=5", ["thue-phi-le-phi:5"], "thue-phi-le-phi:5")]
            out = []
            for h, keys, cur in forms:
                pg.evaluate("(h) => { location.hash = h; }", h)
                choice(pg, keys, cur)
                a = pg.evaluate(JS_ALPHA, keys)
                out.append([h, len(keys), cur, bool(a and a["pass"])])
            pg.evaluate("() => { location.hash = '#area=bao-hiem'; }")
            pg.wait_for_function("() => { const T = window.__VLONTO_METRICS.traces; return !(T.selected || []).length && T.scrolledTo === 'bao-hiem'; }",
                                 timeout=T_(30000))
            # the heading scrolled into the side's view (the page scrolls it at once, without smooth scrolling)
            head = pg.evaluate("""() => { const h = document.getElementById('tr-h-bao-hiem'), sd = document.getElementById('side');
                const r = h.getBoundingClientRect(), s = sd.getBoundingClientRect(); return { visible: r.height > 0 && r.top >= s.top - 1 && r.bottom <= s.bottom + 1,
                  head: [r.top, r.bottom].map(Math.round), side: [s.top, s.bottom].map(Math.round) }; }""")
            s2 = pg.evaluate(JS_TRACES)
            c1, m1 = pg.evaluate(CAM), pg.evaluate(MOVES)
            side(pg, False)
            if not all(x[3] for x in out) or s2["selected"] or s2["panelOpen"] or not head["visible"] or c0 != c1 or m0 != m1:
                raise RuntimeError(f"deep links {out}; #area=bao-hiem -> chosen {s2['selected']}, panel {s2['panelOpen']}, heading {head}; "
                                   f"camera {c0} -> {c1}, moves {m0} -> {m1}")
            return {"links": out, "area_link": s2["scrolledTo"], "heading": head}
        check("deep links: #q=a:r, #q=a:r1,r2, #q=a:r1,r2;b:r3, #area=a&all=1 (&q=r), v1's #area=a&q=r choose exactly those (the "
              "first listed shown); #area=a alone scrolls the list to its heading and chooses nothing; the camera stays", links, pg)
    finally:
        merge(log)
        ctx.close()

    # v1's deep link per theme (emulated system setting), then the header switch to the other theme keeps the trace (the
    # lite network, #ds=lite: these loads test the trace, the theme and the call-outs, not the network)
    for theme in c.themes:
        def deep(theme=theme):
            area, rank = TRACE_PICKS[0]
            ctx, pg, log = c.open(f"traces.html#area={area}&q={rank}&{LITE}", scheme=theme, ready_timeout=T_(240000))
            try:
                pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": 0}, timeout=T_(120000))
                applied = pg.evaluate("document.documentElement.getAttribute('data-theme')")
                if applied != theme:
                    raise RuntimeError(f"theme {applied}, expected {theme}")
                clash = pg.evaluate(JS_HINT_CLASH)
                if clash:
                    raise RuntimeError(f"deep link ({theme}): the first-visit hint overlaps the stage tools while the panel is open: {clash}")
                d1 = judge(pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS), f"deep link ({theme})", pg)
                a1 = alpha(pg, [f"{area}:{rank}"], f"deep link ({theme})")
                px1 = trace_pixels(pg, "#canvas-host", theme)
                if px1["core_out"] < TRACE_PX_MIN["core"] or px1["halo_near_core"] < TRACE_PX_MIN["halo"]:
                    raise RuntimeError(f"deep link ({theme}): trace pixels {px1} (minimum {TRACE_PX_MIN})")
                shot1 = c.shot(pg, f"traces_deep__{theme}")
                other = "dark" if theme == "light" else "light"
                r0, n0 = runs(pg), pg.evaluate("window.__VLONTO_METRICS.themeRenders || 0")
                click_theme(pg, other)
                pg.wait_for_function("(n) => (window.__VLONTO_METRICS.themeRenders || 0) > n", arg=n0, timeout=T_(30000))
                pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": r0}, timeout=T_(60000))
                d2 = judge(pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS), f"after switching to {other}", pg)
                a2 = alpha(pg, [f"{area}:{rank}"], f"after switching to {other}")
                px2 = trace_pixels(pg, "#canvas-host", other)
                if px2["core_out"] < TRACE_PX_MIN["core"] or px2["halo_near_core"] < TRACE_PX_MIN["halo"]:
                    raise RuntimeError(f"after switching to {other}: trace pixels {px2} (minimum {TRACE_PX_MIN})")
                shot2 = c.shot(pg, f"traces_deep__{theme}_to_{other}")
                return {"theme": [d1["callouts"], px1, shot1, a1["netLinks"]], "switched": [d2["callouts"], px2, shot2, a2["netLinks"]],
                        "hint_checked": clash is not None, "page_width": no_hscroll(c, pg, "traces deep link")}
            finally:
                merge(log)
                ctx.close()
        check(f"deep link #area=lao-dong-tien-luong&q=3 (v1) lights exactly the trace ({theme}); the theme switch keeps it and its "
              f"alphas (the other traces faint; the links at the other theme's opacities times the light alpha)", deep)

    # the page in EN and in VI (?lang=): one language in the headings, search, count line, Clear, list, hop panel, legend and
    # call-outs; the header switch back to EN–VI renders them as v1 (title over gloss, paired headings and hop headings)
    # and keeps the trace (the lite network, #ds=lite)
    def lang_state(pg):
        return pg.evaluate(JS_TRACES_LANG)

    for mode in ("en", "vi"):
        def lang(mode=mode):
            area, rank = TRACE_PICKS[0]
            ctx, pg, log = c.open(f"traces.html#area={area}&q={rank}&{LITE}", query=f"?lang={mode}", ready_timeout=T_(240000))
            try:
                pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": 0}, timeout=T_(120000))
                d1 = judge(pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS), f"in {mode}", pg)
                s = lang_state(pg)
                hops = " | ".join(s["hops"])
                bad = traces_side_lang(s, mode, chosen=1)
                if s["lang"] != mode or s["labelsLang"] != mode:
                    bad.append(f"mode {s['lang']}, call-outs {s['labelsLang']}")
                if s["glosses"]:
                    bad.append(f"{s['glosses']} list entries still carry the second language")
                if mode == "vi" and s["viTitles"] != s["items"]:
                    bad.append(f"{s['items'] - s['viTitles']} list entries without the Vietnamese title")
                if mode == "en" and (not hops.startswith("1 Question") or "Câu hỏi" in hops):
                    bad.append(f"hop headings: {hops[:200]}")
                if mode == "vi" and (not hops.startswith("1 Câu hỏi") or re.search(r"\b(Question|Answer|Provision)\b", hops)):
                    bad.append(f"hop headings: {hops[:200]}")
                if not c.mobile and not (("Traced answer" in s["legend"] and "Đường truy vết" not in s["legend"]) if mode == "en"
                                         else ("Đường truy vết" in s["legend"] and "Traced answer" not in s["legend"])):
                    bad.append(f"legend: {s['legend'][:160]}")
                if bad:
                    raise RuntimeError(f"{mode}: " + "; ".join(bad))
                shot = c.shot(pg, f"traces_lang_{mode}")
                r0 = runs(pg)
                set_lang(c, pg, "envi")
                pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": r0}, timeout=T_(60000))
                d2 = judge(pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS), f"{mode} -> EN–VI", pg)
                s2 = lang_state(pg)
                bad2 = traces_side_lang(s2, "envi", chosen=1)
                if s2["labelsLang"] != "envi" or s2["glosses"] != s2["items"] or not s2["hops"][0].startswith("1 Question Câu hỏi") or bad2:
                    raise RuntimeError(f"back to EN–VI: call-outs {s2['labelsLang']}, glosses {s2['glosses']}/{s2['items']}, hops {s2['hops'][:2]}; {bad2}")
                return {"callouts": d1["callouts"], "hops": s["hops"], "heads": [h["name"] for h in s["heads"]], "placeholder": s["placeholder"],
                        "count": s["count"], "back": {"callouts": d2["callouts"], "heads": [h["name"] for h in s2["heads"]],
                                                      "placeholder": s2["placeholder"], "count": s2["count"]}, "shot": shot}
            finally:
                merge(log)
                ctx.close()
        check(f"traces in {mode.upper()}: headings, search, count line, Clear, list, hop panel, legend and call-outs in one language; "
              f"the header switch back to EN–VI pairs the headings and keeps the trace", lang)
    res["log"] = logs
    return res


GALLERY = ["index.html", "about.html", "network-3d.html", "sparql.html", "dashboard.html", "ontology.html",
           "playbook.html", "downloads.html", "traces.html", "ontology/vlonto.html"]


def t_gallery(c: Ctx):
    """Review screenshots (http only): the viewport at the top of every page, and a full-page capture taken after
    scrolling back to the top, so sticky header and filter bars render in place; capped at 10,000 CSS px."""
    if c.mode != "http":
        return []
    shots = []
    for theme in c.themes:
      for page in GALLERY:
        ctx, pg, log = c.open(page, ready=not page.startswith("ontology/"), scheme=theme, ready_timeout=T_(240000))
        pg.wait_for_timeout(2500 if page in SCENES else 800)
        pg.evaluate("() => window.scrollTo(0, 0)")
        pg.wait_for_timeout(300)
        name = page.replace("/", "__").replace(".html", "")
        top = c.out / "gallery" / f"{name}__{theme}__{c.vp[0]}x{c.vp[1]}__top.png"
        top.parent.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(top))
        applied = pg.evaluate("document.documentElement.getAttribute('data-theme')")
        rec = {"page": page, "theme": theme, "applied": applied, "top": str(top.relative_to(c.out))}
        h = pg.evaluate("() => document.documentElement.scrollHeight")
        if h > c.vp[1] + 40 and "3d" not in page:
            full = c.out / "gallery" / f"{name}__{theme}__{c.vp[0]}x{c.vp[1]}__full.png"
            ch = min(h, 10000)
            pg.screenshot(path=str(full), full_page=True, clip={"x": 0, "y": 0, "width": c.vp[0], "height": ch})
            rec.update({"full": str(full.relative_to(c.out)), "page_height": h, "captured_height": ch})
        rec["errors"] = log["page_errors"] + log["console_errors"] + log["failed_requests"] + \
            ([f"theme {applied} applied, {theme} expected"] if applied != theme else [])
        # placeholder text is not in the DOM text checks: measure it against the input's content box
        rec["clipped_placeholders"] = pg.evaluate("""() => Array.from(document.querySelectorAll('input[placeholder], textarea[placeholder]'))
            .filter(e => e.offsetParent !== null && e.placeholder).map(e => {
              const cs = getComputedStyle(e), cx = document.createElement('canvas').getContext('2d');
              cx.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
              const w = cx.measureText(e.placeholder).width;
              const avail = e.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
              return {id: e.id, placeholder: e.placeholder, text_px: Math.round(w), avail_px: Math.round(avail)};
            }).filter(x => x.text_px > x.avail_px)""")
        shots.append(rec)
        ctx.close()
    bad = [s["page"] for s in shots if s["errors"] or s["clipped_placeholders"]]
    return [{"test": "gallery", "checks": [{"name": "review screenshots of every page", "pass": not bad, "details": shots}], "log": {}}]


LANG_NAV = {"en": "Traces", "vi": "Truy v\u1ebft", "envi": "Traces"}      # the traces link in each mode
LANG_HTML = {"en": "en", "vi": "vi", "envi": "en"}                          # html[lang]: English carries the envi page
JS_LANG = r"""() => {
  const M = window.__VLONTO_METRICS || {}, de = document.documentElement, se = document.scrollingElement || de;
  const links = Array.from(document.querySelectorAll('#vl-nav a[href^="traces.html"]'));
  const attrs = Array.from(document.querySelectorAll('[title],[aria-label]'))
      .map(e => (e.getAttribute('title') || '') + ' ' + (e.getAttribute('aria-label') || '')).join(' | ');
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: n =>
      /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(n.parentNode.nodeName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
  let body = ''; while (w.nextNode()) body += w.currentNode.nodeValue + ' ';
  const txt = (body + ' | ' + attrs + ' | ' + document.title).normalize('NFC');
  const mixed = /Truy v\u1EBFt\s*[\u00B7\u2022\u2013\u2014-]\s*Traces|Traces\s*[\u00B7\u2022\u2013\u2014-]\s*Truy v\u1EBFt/i.test(txt);
  const clipped = Array.from(document.querySelectorAll('.vl-header a, .vl-header button, .vl-header [role=radio]'))
      .filter(e => e.offsetParent !== null && e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1)
      .map(e => e.textContent.replace(/\s+/g, ' ').trim().slice(0, 40) + ' ' + e.scrollWidth + '>' + e.clientWidth);
  const hdr = document.querySelector('.vl-header');
  let stored = null; try { stored = window.localStorage.getItem('vlonto.lang'); } catch (e) { stored = 'blocked'; }
  return { lang: M.lang || null, data: de.getAttribute('data-lang'), html: de.getAttribute('lang'), changes: M.langChanges || 0,
           missing: (M.i18nMissing || []).slice(0, 12),
           labels: M.labelsLang === undefined ? null : M.labelsLang,
           nav: links.map(a => a.textContent.replace(/\s+/g, ' ').trim()), tip: links.map(a => a.getAttribute('title') || ''),
           mixed, clipped, scroll: se.scrollWidth, inner: window.innerWidth,
           header: hdr ? Math.max(0, hdr.scrollWidth - hdr.clientWidth) : null, stored, url: location.href,
           checked: Array.from(document.querySelectorAll('.vl-lang-bar [role=radio][aria-checked="true"]')).map(b => b.getAttribute('data-vl-lang')) };
}"""


def click_lang(c, pg, want):
    """Pick a language mode with the visible switch, like a visitor: the header copy on wide screens,
    the copy in the menu sheet on phones (the menu is closed again afterwards)."""
    bar = pg.locator(f'.vl-lang-bar [role=radio][data-vl-lang="{want}"]')
    if bar.count() and bar.first.is_visible():
        bar.first.click()
    else:
        pg.locator(".vl-menu-btn").click()
        pg.wait_for_timeout(250)
        pg.locator(f'.vl-lang-sheet [role=radio][data-vl-lang="{want}"]').first.click()
    pg.wait_for_function("(m) => document.documentElement.getAttribute('data-lang') === m", arg=want, timeout=T_(15000))
    mb = pg.locator(".vl-menu-btn")
    if mb.count() and mb.first.is_visible() and mb.first.get_attribute("aria-expanded") == "true":
        mb.first.click()
        pg.wait_for_timeout(250)


def wait_labels(pg, want):
    """3D views report the mode their canvas labels were last drawn in (M.labelsLang); other pages have none."""
    pg.wait_for_function("(m) => { const L = (window.__VLONTO_METRICS || {}).labelsLang; return L === undefined || L === null || L === m; }",
                         arg=want, timeout=T_(120000))


def t_lang(c: Ctx):
    """Language switch (EN, VI, EN-VI): the default is EN-VI; the header switch (menu sheet on phones) changes the
    whole page without a reload, navigation and buttons stay single-language in every mode (the traces link reads
    'Traces' in EN and EN-VI, with a 'Truy vet' tooltip in EN-VI, and 'Truy vet' in VI; the old mixed label is gone),
    3D canvas labels are redrawn in the new mode, nothing overflows the viewport or clips in the header, the choice
    persists across pages and reloads (localStorage, or ?lang= carried on internal links when storage is blocked),
    and ?lang= forces a mode."""
    res = {"test": "lang", "checks": []}
    logs = {"console_errors": [], "page_errors": [], "failed_requests": [], "external_requests": []}

    def merge(log):
        for k in logs:
            logs[k] += log.get(k, [])

    def check(name, fn):
        t0 = time.time()
        try:
            res["checks"].append({"name": name, "pass": True, "details": fn(), "s": round(time.time() - t0, 2)})
        except Exception as e:  # noqa
            res["checks"].append({"name": name, "pass": False, "details": {"error": str(e)[:1200]}, "s": round(time.time() - t0, 2)})

    def verify(page, s, want, when):
        p = []
        if s["lang"] != want or s["data"] != want:
            p.append(f"{when}: mode {s['lang']}/{s['data']}, expected {want}")
        if s["html"] != LANG_HTML[want]:
            p.append(f"{when}: html lang {s['html']!r}, expected {LANG_HTML[want]!r}")
        if not s["nav"] or any(t != LANG_NAV[want] for t in s["nav"]):
            p.append(f"{when}: traces link reads {s['nav']}, expected {LANG_NAV[want]!r}")
        if want == "envi" and not any("Truy v\u1ebft" in t for t in s["tip"]):
            p.append(f"{when}: traces link has no Vietnamese tooltip ({s['tip']})")
        if s["mixed"]:
            p.append(f"{when}: the mixed label 'Truy vet - Traces' is still on the page")
        if s["scroll"] > c.vp[0] + 1:      # measured against the device width: mobile Chrome zooms an over-wide page out
            p.append(f"{when}: page is {s['scroll']} px wide at a {c.vp[0]} px viewport")
        if s["header"]:
            p.append(f"{when}: header content overflows by {s['header']} px")
        if s["clipped"]:
            p.append(f"{when}: clipped header controls {s['clipped'][:4]}")
        if s["checked"] and s["checked"] != [want]:
            p.append(f"{when}: the switch shows {s['checked']} as selected")
        if s["missing"]:
            p.append(f"{when}: dictionary keys missing at run time {s['missing']}")
        if page in SCENES and s["labels"] != want:
            p.append(f"{when}: 3D labels drawn in {s['labels']}")
        return p

    def brief(s):
        return {"lang": s["lang"], "nav": s["nav"], "tip": s["tip"], "labels": s["labels"], "width": s["scroll"]}

    def page_modes(page):
        def fn():
            ctx, pg, log = c.open(loop_page(page), ready_timeout=T_(240000))
            try:
                pg.wait_for_timeout(1500 if page in SCENES else 300)
                wait_labels(pg, "envi")
                s = pg.evaluate(JS_LANG)
                seen, prob, shot = {"default": brief(s)}, verify(page, s, "envi", "default"), None
                for want in ("vi", "en"):
                    n0 = s["changes"]
                    click_lang(c, pg, want)
                    wait_labels(pg, want)
                    pg.wait_for_timeout(600 if page in SCENES else 200)
                    s = pg.evaluate(JS_LANG)
                    seen[want] = brief(s)
                    prob += verify(page, s, want, f"switch to {want}")
                    if s["changes"] <= n0:
                        prob.append(f"switch to {want}: langChanges stayed {s['changes']}")
                    if s["stored"] != want:
                        prob.append(f"switch to {want}: stored {s['stored']!r}")
                    if want == "vi":
                        shot = c.shot(pg, f"lang_vi_{page.rsplit('.', 1)[0]}")
                pg.reload(wait_until="load")
                pg.wait_for_function("window.__VLONTO_READY === true", timeout=T_(240000))
                wait_labels(pg, "en")
                s = pg.evaluate(JS_LANG)
                seen["reload"] = brief(s)
                prob += verify(page, s, "en", "after reload")
                if prob:
                    raise RuntimeError("; ".join(prob))
                return {"modes": seen, "shot": shot}
            finally:
                merge(log)
                ctx.close()
        check(f"switch EN-VI -> VI -> EN on {page}, then reload", fn)

    for page in SITE_PAGES:
        page_modes(page)

    def carry(init, label):
        def fn():
            ctx, pg, log = c.open("about.html", init_script=init)
            try:
                click_lang(c, pg, "vi")
                nav_to(c, pg, "dashboard.html")
                a = pg.evaluate(JS_LANG)
                pg.reload(wait_until="load")
                pg.wait_for_function("window.__VLONTO_READY === true", timeout=T_(120000))
                b = pg.evaluate(JS_LANG)
                click_lang(c, pg, "en")
                nav_to(c, pg, "playbook.html")
                d = pg.evaluate(JS_LANG)
                got = (a["lang"], b["lang"], d["lang"])
                prob = [] if got == ("vi", "vi", "en") else [f"modes after navigate/reload/switch+navigate: {got} ({a['url'][-40:]}, {d['url'][-40:]})"]
                prob += verify("dashboard.html", a, "vi", "after navigate") + verify("playbook.html", d, "en", "after switch+navigate")
                if prob:
                    raise RuntimeError("; ".join(prob))
                return {"after_nav": [a["lang"], a["stored"], a["url"][-40:]], "after_reload": b["lang"],
                        "after_switch_nav": [d["lang"], d["stored"], d["url"][-40:]]}
            finally:
                merge(log)
                ctx.close()
        check(f"choice persists across pages and reload ({label})", fn)

    carry(None, "localStorage")
    carry(NO_STORAGE, "storage blocked: ?lang= carried on links")

    def forced():
        ctx, pg, log = c.open("about.html", query="?lang=vi")
        try:
            s = pg.evaluate(JS_LANG)
            prob = verify("about.html", s, "vi", "?lang=vi")
            if prob:
                raise RuntimeError("; ".join(prob))
            return brief(s)
        finally:
            merge(log)
            ctx.close()
    check("?lang=vi forces Vietnamese", forced)

    res["log"] = logs
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--modes", default="http,file")
    ap.add_argument("--viewports", default="1440x900,390x844")
    ap.add_argument("--tests", default="ontology,network,sparql,dashboard,simple,traces,theme,paper,paper_style,lang,gallery")
    ap.add_argument("--themes", default="light,dark", help="themes of the gallery and paper screenshots (emulated system setting)")
    ap.add_argument("--chrome", type=Path, default=HERE.parent.parent / "tools" / "chrome.sh")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    sd = root / "downloads" / "data"
    stats = json.loads((sd / "stats.json").read_text(encoding="utf-8"))
    examples = json.loads((sd / "sparql_examples.json").read_text(encoding="utf-8"))["queries"]
    srv = make_server(root)
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    vps = [tuple(int(x) for x in v.split("x")) for v in a.viewports.split(",")]
    tests = a.tests.split(",")
    results = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(a.chrome), headless=True)
        for mode in a.modes.split(","):
            for vp in vps:
                c = Ctx(browser, root, base, mode, vp, a.out, themes=[t for t in a.themes.split(",") if t])
                runs = []
                if "theme" in tests:
                    runs.append(lambda: [t_theme(c)])
                if "paper" in tests:
                    runs.append(lambda: [t_paper(c)])
                if "paper_style" in tests:
                    runs.append(lambda: [t_paper_style(c)])
                if "lang" in tests:
                    runs.append(lambda: [t_lang(c)])
                if "ontology" in tests:
                    runs.append(lambda: [t_ontology(c)])
                if "network" in tests:
                    runs.append(lambda: [t_network(c)])
                if "sparql" in tests:
                    runs.append(lambda: [t_sparql(c, examples)])
                if "dashboard" in tests:
                    runs.append(lambda: [t_dashboard(c, stats)])
                if "simple" in tests:
                    runs.append(lambda: t_simple(c, root))
                if "traces" in tests:
                    runs.append(lambda: [t_traces(c)])
                if "gallery" in tests:
                    runs.append(lambda: t_gallery(c))
                for fn in runs:
                    try:
                        for r in fn():
                            r["mode"], r["viewport"] = mode, f"{vp[0]}x{vp[1]}"
                            lg = r.get("log", {})
                            r["pass"] = all(ch["pass"] for ch in r["checks"]) and not lg.get("page_errors") and not lg.get("console_errors") \
                                and not lg.get("failed_requests") and not lg.get("external_requests")
                            results.append(r)
                            print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['test']} {mode} {vp[0]}x{vp[1]}" +
                                  "".join(f"\n    - {'ok ' if ch['pass'] else 'FAIL'} {ch['name']}: {json.dumps(ch['details'], ensure_ascii=False)[:260]}" for ch in r["checks"]) +
                                  "".join(f"\n    ! {k}: {v[:3]}" for k, v in lg.items() if isinstance(v, list) and v), flush=True)
                    except Exception as e:  # noqa
                        results.append({"test": "harness", "mode": mode, "viewport": f"{vp[0]}x{vp[1]}", "pass": False, "error": str(e)[:500], "checks": []})
                        print(f"[FAIL] harness {mode} {vp}: {str(e)[:300]}", flush=True)
        browser.close()
    srv.shutdown()
    rep = {"tool": "interaction_tests.py", "root": str(a.root), "results": results,   # as given (relative): no node paths in reports
           "summary": {"runs": len(results), "failed": sum(1 for r in results if not r["pass"])}}
    rep["ok"] = rep["summary"]["failed"] == 0
    (a.out / "interactions.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("RESULT:", "PASS" if rep["ok"] else "FAIL", rep["summary"])
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
