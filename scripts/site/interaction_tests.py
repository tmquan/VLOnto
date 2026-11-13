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
  traces        traces.html: one 3D scene of all 540 traces; 27 area tabs (ARIA, keyboard, scrolling inside their box),
                lazy area files, a question in each of three areas lights its trace (core / halo pixels), call-outs clean,
                Fig. 5 hop panel; node click; Escape; deep link #area=&q= per theme and the theme switch; no overflow
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
                # a real tap lasts ~100-200 ms; 3d-force-graph picks the object under the finger in its render loop
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
        if c.mobile:
            pg.click("#btn-side-m")
        pg.click("[data-lang=vi]")
        if c.mobile:
            pg.click("#btn-side-m")
        pg.click("#btn-reset2")
        pg.wait_for_timeout(1500)
        m = M()
        shot = c.shot(pg, "ontology3d_labels_vi")
        if m.get("labelLang") != "vi":
            raise RuntimeError("label language not switched")
        return {"labels_shown": m.get("labelsShown"), "labels_hidden": m.get("labelsHidden"), "shot": shot}
    check("EN/VI label toggle", labels_vi)

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
            ctx, pg, log = c.open(page, scheme="light", ready_timeout=T_(240000))
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
            ctx, pg, log = c.open(page, ready=not page.startswith("ontology/"), ready_timeout=T_(240000))
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


def callout_faults(co):
    """the paper's rule for one placement run: no two visible call-outs intersect, no visible call-out covers a projected
    node centre (the nodes the run saw: every visible node in the playground and the CONSTRUCT view, the highlighted
    documents in the legal network), and no selected or traced call-out was dropped"""
    if not co:
        return ["no call-out placement recorded"]
    boxes = [(p["id"], p["box"]) for p in co.get("placed", [])]
    inter = [(a[0], b[0]) for i, a in enumerate(boxes) for b in boxes[i + 1:]
             if a[1][0] < b[1][2] and b[1][0] < a[1][2] and a[1][1] < b[1][3] and b[1][1] < a[1][3]]
    covered = [(pid, nid) for pid, b in boxes for nid, x, y in co.get("nodes", []) if b[0] < x < b[2] and b[1] < y < b[3]]
    faults = []
    if inter:
        faults.append(f"{len(inter)} pairs of intersecting call-outs, e.g. {inter[:3]}")
    if covered:
        faults.append(f"{len(covered)} node centres under call-outs, e.g. {covered[:3]}")
    if co.get("mustHidden"):
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
                if not c.mobile and not all(x in legend for x in ("Văn bản · Work", "Điều · Article", "Đường truy vết")):
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
    res["log"] = logs
    return res


# ------------------------------------------------------------------ question traces (traces.html)
# geometry of the trace drawings as rendered: every call-out box against the boxes of the nodes (circles) and of the
# links and traced segments (paths, widened by half their stroke); each text line inside its box; boxes inside the view
JS_TRACES = """() => { const M = window.__VLONTO_METRICS || {}, T = M.traces || {}, tabs = Array.from(document.querySelectorAll('#tr-tabs [role=tab]'));
  const tl = document.getElementById('tr-tabs'), tp = document.getElementById('tr-panel'), pn = document.getElementById('panel'), l = document.getElementById('tr-list');
  return { available: T.available, webgl: T.webgl, fallback: T.fallback, graph: T.graph, area: T.area, loaded: (T.loaded || []).slice(),
    listItems: l.querySelectorAll('.tr-item').length, listArea: l.getAttribute('data-area'),
    current: Array.from(l.querySelectorAll('.tr-item[aria-current="true"]')).map(b => +b.getAttribute('data-rank')),
    selected: T.selected, segments: T.traceSegments, verified: T.traceVerified, structural: T.traceStructural, hops: T.hops, edgeCost: T.edgeCost || null,
    labels: T.labels, flights: T.flights, fps: T.fps, themeRenders: T.themeRenders, linksShown: T.linksShown, clicked: T.clicked || null,
    tabs: tabs.length, tablist: tl.getAttribute('role'), selTabs: tabs.filter(t => t.getAttribute('aria-selected') === 'true').map(t => t.getAttribute('data-area')),
    tabindex0: tabs.filter(t => t.tabIndex === 0).length, controls: tabs.every(t => t.getAttribute('aria-controls') === 'tr-panel'),
    labelledby: tp.getAttribute('aria-labelledby'), strip: { scroll: tl.scrollWidth, client: tl.clientWidth, overflowX: getComputedStyle(tl).overflowX },
    panelOpen: !pn.classList.contains('hidden'), panelHops: pn.querySelectorAll('.hop').length, hash: location.hash,
    active: document.activeElement ? (document.activeElement.id || document.activeElement.className || document.activeElement.tagName) : null,
    areaScripts: Array.from(document.scripts).map(s => s.getAttribute('src') || '').filter(s => s.indexOf('data/traces/') === 0).sort() }; }"""
# a selection is complete when the camera has arrived and a call-out run newer than `runs` shows the question's call-out
JS_TRACE_DONE = """(a) => { const M = window.__VLONTO_METRICS, T = M.traces, S = T.selected, C = M.callouts;
  return !!S && S.area === a.area && S.rank === a.rank && T.traceSegments > 0 && T.hops === 5 && window.VLApp.traces.settle() &&
    !!C && C.runs > a.runs && C.placed.some(p => p.id === S.q && p.sel); }"""
JS_AREA_DONE = """(id) => { const T = window.__VLONTO_METRICS.traces, l = document.getElementById('tr-list');
  return T.area === id && l.getAttribute('data-area') === id && l.querySelectorAll('.tr-item').length === 20 && window.VLApp.traces.settle(); }"""
TRACE_PICKS = [("lao-dong-tien-luong", 3), ("thue-phi-le-phi", 5), ("bao-hiem", 8)]


def t_traces(c: Ctx):
    """traces.html: the 540 traced answers in one 3D scene (js/traces3d.js, data/traces/graph.js). 27 area tabs in an ARIA
    tablist that scrolls inside its own box (keyboard: arrows, Home, End), the open area's 20 questions in the list (lazy
    area files), three areas opened and one question selected in each: the trace lit in the canvas (core and halo pixels),
    the question, provision, law, term and area call-outs placed with no overlap and no node centre covered, the Fig. 5
    hop panel with five boxes, the list entry marked; a click on a node opens its details; Escape clears the selection;
    the deep link #area=lao-dong-tien-luong&q=3 per theme, and the theme switch keeps the trace; no page wider than the
    screen, no console errors; screenshots."""
    res = {"test": "traces", "checks": []}
    logs = {"console_errors": [], "page_errors": [], "failed_requests": [], "external_requests": []}

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

    def open_area(pg, area):
        pg.locator(f"#tr-tab-{area}").click()
        pg.wait_for_function(JS_AREA_DONE, arg=area, timeout=T_(90000))

    def select(pg, area, rank):
        r0 = runs(pg)
        if c.mobile and not pg.evaluate("() => document.getElementById('app').classList.contains('side-open')"):
            pg.locator("#btn-list-m").click()
        pg.locator(f'#tr-list .tr-item[data-rank="{rank}"]').click()
        pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": r0}, timeout=T_(90000))
        pg.wait_for_timeout(400)
        return pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS)

    def judge(s, co, where):
        """the selected trace: drawn, five hops, list entry marked, call-outs clean (the question's never forced on desktop)"""
        S = s["selected"] or {}
        faults = callout_faults(co)
        q = [p for p in co.get("placed", []) if p["id"] == S.get("q")]
        if not q or (q[0]["forced"] and not c.mobile):
            faults.append(f"question call-out {'forced' if q else 'missing'}")
        if co.get("shown", 0) < (2 if c.mobile else 3):
            faults.append(f"only {co.get('shown')} call-outs shown")
        if s["segments"] < 3 or s["panelHops"] != 5 or not s["panelOpen"] or s["current"] != [S.get("rank")] or f"q={S.get('rank')}" not in s["hash"]:
            faults.append(f"segments {s['segments']}, hops {s['panelHops']}, panel {s['panelOpen']}, list {s['current']}, hash {s['hash']}")
        if faults:
            raise RuntimeError(f"{where}: {'; '.join(faults)}; call-outs {callout_summary(co)}")
        return {"selected": {k: S.get(k) for k in ("q", "provision", "law", "term", "areaNode", "fg", "segments")},
                "verified_segments": s["verified"], "structural_segments": s["structural"], "callouts": callout_summary(co),
                "placed": [p["id"] for p in co["placed"]]}

    ctx, pg, log = c.open("traces.html", ready_timeout=T_(240000))
    try:
        if pg.evaluate("() => { const h = document.getElementById('hint'); return !!h && !h.classList.contains('hidden'); }"):
            pg.locator("#hint-close").click()             # the first-visit hint: dismissed like a visitor would
        def tabs():
            s = pg.evaluate(JS_TRACES)
            ok = (s["available"] and s["webgl"] and not s["fallback"] and s["tabs"] == 27 and s["tablist"] == "tablist" and len(s["selTabs"]) == 1
                  and s["tabindex0"] == 1 and s["controls"] and s["labelledby"] == "tr-tab-" + s["selTabs"][0]
                  and (s["graph"] or {}).get("traces") == 540 and (s["graph"] or {}).get("nodes", 0) > 10000
                  and (s["edgeCost"] or {}).get("curves") and s["edgeCost"]["segments"] > s["edgeCost"]["links"])
            if not ok:
                raise RuntimeError(f"state {json.dumps(s, ensure_ascii=False)[:900]}")
            return {"tabs": s["tabs"], "selected": s["selTabs"], "graph": s["graph"], "fps": s["fps"], "links_shown": s["linksShown"],
                    "edge_cost": s["edgeCost"]}
        check("one WebGL scene of all traces (540 traces, > 10,000 nodes, links drawn as curves); 27 area tabs in an ARIA tablist, "
              "one selected, roving tabindex", tabs, pg)

        def strip():
            s = pg.evaluate(JS_TRACES)
            last = pg.evaluate("Array.from(document.querySelectorAll('#tr-tabs [role=tab]')).pop().getAttribute('data-area')")
            pg.locator(f"#tr-tab-{last}").scroll_into_view_if_needed()
            pg.wait_for_timeout(200)
            box = pg.evaluate("""(id) => { const t = document.getElementById('tr-tab-' + id).getBoundingClientRect(), s = document.getElementById('tr-tabs').getBoundingClientRect();
                return { inside: t.left >= s.left - 1 && t.right <= s.right + 1, tab: [Math.round(t.left), Math.round(t.right)], strip: [Math.round(s.left), Math.round(s.right)] }; }""", last)
            w = no_hscroll(c, pg, "traces")
            if s["strip"]["overflowX"] not in ("auto", "scroll") or s["strip"]["scroll"] <= s["strip"]["client"] or not box["inside"]:
                raise RuntimeError(f"tab strip {s['strip']}, last tab {box}")
            return {"strip": s["strip"], "last_tab": box, "page_width": w}
        check("the tab strip scrolls inside its own box (the last tab reachable); the page is no wider than the screen", strip, pg)

        def lazy():
            s = pg.evaluate(JS_TRACES)
            want = sorted(["data/traces/index.js", "data/traces/graph.js", "data/traces/" + s["area"] + ".js"])
            if s["listItems"] != 20 or s["listArea"] != s["area"] or s["areaScripts"] != want:
                raise RuntimeError(f"list {s['listItems']} ({s['listArea']}), scripts {s['areaScripts']}")
            return {"area": s["area"], "list": s["listItems"], "scripts": s["areaScripts"]}
        check("only the graph and the open area's file are loaded; the list shows the area's 20 questions", lazy, pg)

        def legend():
            if c.mobile:
                pg.locator("#btn-legend").click()
            L = pg.evaluate("""() => { const l = document.querySelector('[data-legend]'); if (!l) return null; const r = l.getBoundingClientRect();
                return { entries: l.querySelectorAll('li').length, text: l.textContent.replace(/\\s+/g, ' '), visible: r.width > 0 && r.height > 0,
                  flat: Array.from(l.querySelectorAll('.swatch:not(.trace)')).every(s => getComputedStyle(s).backgroundImage === 'none') }; }""")
            if c.mobile:
                pg.locator("#btn-legend").click()
            need = ("Văn bản", "Work", "Điều", "Article", "Đường truy vết", "Traced answer", "Structure only")
            if not L or not L["visible"] or L["entries"] < 14 or not L["flat"] or any(n not in L["text"] for n in need):
                raise RuntimeError(f"legend {L}")
            return {"entries": L["entries"], "flat_swatches": L["flat"]}
        check("flat bilingual legend with the traced and the structural path", legend, pg)

        def three():
            out = []
            for area, rank in TRACE_PICKS:
                open_area(pg, area)
                before = trace_pixels(pg, "#canvas-host", "light")
                s, co = select(pg, area, rank)
                d = judge(s, co, f"{area} #{rank}")
                after = trace_pixels(pg, "#canvas-host", "light")
                # the trace's own pixels, as in the paper-style check: its core outside the call-out boxes and the gold
                # band next to that core (a raw gold count also follows the pale answer nodes that fade on selection)
                d_core = after["core_out"] - before["core_out"]
                d_halo = after["halo_near_core"] - before["halo_near_core"]
                if d_core < 30 or d_halo < max(60, d_core // 2):
                    raise RuntimeError(f"{area} #{rank}: trace pixels {before} -> {after}")
                d.update({"area": area, "rank": rank, "pixels": [before, after]})
                if area == TRACE_PICKS[0][0]:
                    d["shot"] = c.shot(pg, "traces_selected")
                out.append(d)
            return {"traces": out, "page_width": no_hscroll(c, pg, "traces with a trace selected")}
        check("three areas: tab -> 20 questions -> a question lights its trace (core / halo pixels), call-outs clean, five hops", three, pg)

        def node_click():
            S = pg.evaluate("window.__VLONTO_METRICS.traces.selected")
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
            return {"target": hit["id"], "clicked": s["clicked"], "same": s["clicked"] == hit["id"]}
        check("a click on a node of the trace opens its details", node_click, pg)

        def keyboard():
            ids = pg.evaluate("Array.from(document.querySelectorAll('#tr-tabs [role=tab]')).map(t => t.getAttribute('data-area'))")
            cur = pg.evaluate("window.__VLONTO_METRICS.traces.area")
            i = ids.index(cur)
            pg.focus(f"#tr-tab-{cur}")
            pg.keyboard.press("ArrowRight")
            nxt = ids[(i + 1) % len(ids)]
            pg.wait_for_function(JS_AREA_DONE, arg=nxt, timeout=T_(90000))
            s1 = pg.evaluate(JS_TRACES)
            pg.keyboard.press("End")
            pg.wait_for_function("(id) => window.__VLONTO_METRICS.traces.area === id", arg=ids[-1], timeout=T_(90000))
            pg.keyboard.press("Home")
            pg.wait_for_function(JS_AREA_DONE, arg=ids[0], timeout=T_(90000))
            s2 = pg.evaluate(JS_TRACES)
            if s1["active"] != f"tr-tab-{nxt}" or s1["selTabs"] != [nxt] or s2["active"] != f"tr-tab-{ids[0]}" or "#area=" + ids[0] not in s2["hash"]:
                raise RuntimeError(f"after ArrowRight {s1['active']} {s1['selTabs']}; after End/Home {s2['active']} {s2['hash']}")
            if c.mobile:
                pg.locator("#btn-list-m").click()
            pg.focus('#tr-list .tr-item[data-rank="1"]')
            pg.keyboard.press("ArrowDown")
            down = pg.evaluate("() => document.activeElement && document.activeElement.id")
            r0 = runs(pg)
            pg.keyboard.press("Enter")
            pg.wait_for_function(JS_TRACE_DONE, arg={"area": ids[0], "rank": 2, "runs": r0}, timeout=T_(90000))
            pg.keyboard.press("Escape")
            pg.wait_for_function("() => !window.__VLONTO_METRICS.traces.selected && document.getElementById('panel').classList.contains('hidden')", timeout=T_(15000))
            s3 = pg.evaluate(JS_TRACES)
            if down != "tr-item-2" or s3["segments"] != 0 or "q=" in s3["hash"] or s3["current"]:
                raise RuntimeError(f"list ArrowDown -> {down}; after Escape {s3['segments']} segments, hash {s3['hash']}, list {s3['current']}")
            return {"arrow_right": nxt, "loaded": len(s2["loaded"]), "list_arrow_down": down, "after_escape": s3["hash"]}
        check("keyboard: ArrowRight / End / Home on the tabs, ArrowDown + Enter in the list select, Escape clears", keyboard, pg)
    finally:
        merge(log)
        ctx.close()

    # deep link per theme (emulated system setting), then the header switch to the other theme keeps the trace
    for theme in c.themes:
        def deep(theme=theme):
            area, rank = TRACE_PICKS[0]
            ctx, pg, log = c.open(f"traces.html#area={area}&q={rank}", scheme=theme, ready_timeout=T_(240000))
            try:
                pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": 0}, timeout=T_(120000))
                pg.wait_for_timeout(400)
                applied = pg.evaluate("document.documentElement.getAttribute('data-theme')")
                if applied != theme:
                    raise RuntimeError(f"theme {applied}, expected {theme}")
                d1 = judge(pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS), f"deep link ({theme})")
                px1 = trace_pixels(pg, "#canvas-host", theme)
                if px1["core"] < 30 or px1["halo"] < 60:
                    raise RuntimeError(f"deep link ({theme}): trace pixels {px1}")
                shot1 = c.shot(pg, f"traces_deep__{theme}")
                other = "dark" if theme == "light" else "light"
                r0, n0 = runs(pg), pg.evaluate("window.__VLONTO_METRICS.themeRenders || 0")
                click_theme(pg, other)
                pg.wait_for_function("(n) => (window.__VLONTO_METRICS.themeRenders || 0) > n", arg=n0, timeout=T_(30000))
                pg.wait_for_function(JS_TRACE_DONE, arg={"area": area, "rank": rank, "runs": r0}, timeout=T_(60000))
                pg.wait_for_timeout(400)
                d2 = judge(pg.evaluate(JS_TRACES), pg.evaluate(JS_CALLOUTS), f"after switching to {other}")
                px2 = trace_pixels(pg, "#canvas-host", other)
                if px2["core"] < 30 or px2["halo"] < 60:
                    raise RuntimeError(f"after switching to {other}: trace pixels {px2}")
                shot2 = c.shot(pg, f"traces_deep__{theme}_to_{other}")
                return {"theme": [d1["callouts"], px1, shot1], "switched": [d2["callouts"], px2, shot2], "page_width": no_hscroll(c, pg, "traces deep link")}
            finally:
                merge(log)
                ctx.close()
        check(f"deep link #area=lao-dong-tien-luong&q=3 lights the trace ({theme}); the theme switch keeps it", deep)
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--modes", default="http,file")
    ap.add_argument("--viewports", default="1440x900,390x844")
    ap.add_argument("--tests", default="ontology,network,sparql,dashboard,simple,traces,theme,paper,paper_style,gallery")
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
