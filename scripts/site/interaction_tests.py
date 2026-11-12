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
  about         navigation has the 8 pages (index.html first) + the Paper link; tool cards link to existing pages; paper card
  redirect      ontology-3d.html#class=... (old playground address) forwards to index.html and keeps the hash
  theme         toggle on every page re-renders canvas / charts / CONSTRUCT view / pyLODE frame; persistence (storage and
                ?theme= carry), system preference, ?theme=dark
  paper         Paper link in header, footer and footbar on every page; BibTeX copy (clipboard and fallback); no overflow
Exit 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import http.server
import json
import re
import sys
import threading
import time
import urllib.parse
from pathlib import Path

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

    def open(self, page: str, ready_timeout=180000, ready=True, scheme="light", query="", init_script=None, permissions=None):
        """New browser context per page: scheme = the emulated system setting (prefers-color-scheme), which is the
        site's default theme when nothing was chosen; query e.g. '?theme=dark'; init_script runs before page scripts."""
        ctx = self.browser.new_context(viewport={"width": self.vp[0], "height": self.vp[1]}, device_scale_factor=2 if self.mobile else 1,
                                       is_mobile=self.mobile, has_touch=self.mobile, accept_downloads=True, color_scheme=scheme)
        if permissions and self.mode == "http":
            ctx.grant_permissions(permissions, origin=self.base_http.rstrip("/"))
        if init_script:
            ctx.add_init_script(init_script)
        pg = ctx.new_page()
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
        pg.goto(self.url(page, query), wait_until="load", timeout=120000)
        if ready:
            pg.wait_for_function("window.__VLONTO_READY === true", timeout=ready_timeout)
        log["ready_s"] = round(time.time() - t0, 2)
        return ctx, pg, log

    def shot(self, pg, name: str) -> str:
        p = self.out / "shots" / f"{name}__{self.mode}__{self.vp[0]}x{self.vp[1]}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(p))
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


def panel_has(pg, *texts, timeout=30000):
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
        pg.wait_for_selector(("#onto-suggest-m" if c.mobile else "#onto-suggest") + " li[role=option]", timeout=10000)
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
        pg.wait_for_selector(("#onto-suggest-m" if c.mobile else "#onto-suggest") + " li[role=option]", timeout=10000)
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
        cands = ["vlo:Law", "vlo:Decree", "vlo:Circular", "vlo:Article", "vlo:LegalDocument", "vlo:CourtDecision", "vlo:Provision", "vlo:LegalChange", "vlo:Code"]
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
                pg.wait_for_function("id => window.__VLONTO_METRICS.selected === id", arg=cid, timeout=8000)
            except Exception:  # noqa
                tried.append([cid, f"selected {pg.evaluate('window.__VLONTO_METRICS.selected')}"])
                continue
            label = pg.evaluate("id => window.VLApp.state().panelText.slice(0, 120)", cid)
            pg.wait_for_timeout(1200)
            return {"clicked": cid, "x": round(p["x"]), "y": round(p["y"]), "panel_starts": label, "tried": tried, "shot": c.shot(pg, "ontology3d_click_class")}
        raise RuntimeError(f"no class node could be clicked: {tried}")
    check("click a class on the canvas -> panel", click_class)

    def construct():
        pg.keyboard.press("Escape")
        pg.evaluate("() => { const a = document.activeElement; if (a && a.blur) a.blur(); const x = document.querySelector('[data-act=close]'); if (x) x.click(); window.scrollTo(0, 0); }")
        pg.wait_for_timeout(300)
        pg.click("#btn-query-m" if c.mobile else "#btn-query")
        pg.wait_for_function("window.__VLONTO_METRICS.storeTriples > 0", timeout=60000)
        no_hscroll(c, pg, "query drawer open")
        pg.select_option("#qd-example", "c0")
        pg.click("#qd-run")
        pg.wait_for_function("(window.__VLONTO_METRICS.view || '').indexOf('construct') === 0", timeout=60000)
        pg.wait_for_timeout(2500)
        m = M()
        st = pg.evaluate("window.VLApp.state()")
        shot = c.shot(pg, "ontology3d_construct")
        if not (m.get("constructTriples", 0) > 0 and st["nodes"] > base_nodes):
            raise RuntimeError(f"graph did not change: {m.get('constructTriples')} triples, nodes {st['nodes']} vs {base_nodes}")
        status = pg.inner_text("#qd-status")
        pg.click("#qd-back")
        pg.wait_for_function("window.__VLONTO_METRICS.view === 'ontology'", timeout=20000)
        back = pg.evaluate("window.VLApp.state()")
        return {"triples": m.get("constructTriples"), "nodes_before": base_nodes, "nodes_after": st["nodes"], "links_after": st["links"],
                "nodes_back": back["nodes"], "store_triples": m.get("storeTriples"), "status": status[:200], "shot": shot}
    check("run a CONSTRUCT example -> 3D graph changes (overlay) and back", construct)

    def select_in_drawer():
        pg.select_option("#qd-example", "s0")
        pg.click("#qd-run")
        pg.wait_for_function("window.__VLONTO_METRICS.lastQuery && window.__VLONTO_METRICS.lastQuery.form === 'SELECT'", timeout=30000)
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
        pg.wait_for_function("window.__VLONTO_METRICS.view === 'construct-replace'", timeout=30000)
        pg.wait_for_timeout(2000)
        st = pg.evaluate("window.VLApp.state()")
        shot = c.shot(pg, "ontology3d_construct_replace")
        pg.click("#qd-back")
        pg.wait_for_function("window.__VLONTO_METRICS.view === 'ontology'", timeout=20000)
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
    ctx, pg, log = c.open("network-3d.html", ready_timeout=240000)
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
        pg.wait_for_selector(lst + " li[role=option]", timeout=15000)
        first = pg.inner_text(lst + " li[role=option]").split("\n")[0]
        pg.press(sel, "Enter")
        panel_has(pg, "Bộ luật Lao động")
        pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '333670'", timeout=60000)
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
        pg.wait_for_function("window.__VLONTO_METRICS.panelLoaded === '142187'", timeout=30000)
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
        pg.evaluate("() => { const e = document.getElementById('y-from'); e.value = 2015; e.dispatchEvent(new Event('input', {bubbles: true})); }")
        pg.wait_for_timeout(600)
        after = pg.inner_text("#status")
        pg.click("[data-color=type]")
        pg.wait_for_timeout(500)
        legend = pg.inner_text("#legend") if pg.is_visible("#legend") else ""
        if c.mobile:
            pg.click("#btn-side-m")
        shot = c.shot(pg, "network3d_filtered")
        pg.evaluate("() => { const e = document.getElementById('y-from'); e.value = e.min; e.dispatchEvent(new Event('input', {bubbles: true})); }")
        pg.wait_for_timeout(400)
        if before == after:
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
        pg.wait_for_function("ds => window.__VLONTO_METRICS.dataset === ds", arg=other, timeout=180000)
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
        pg.wait_for_function("window.__VLONTO_METRICS.constructDrawn && window.__VLONTO_METRICS.constructDrawn.nodes > 0", timeout=60000)
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

    def csv():
        pg.evaluate("window.VLApp.runExample('s1')")
        pg.wait_for_function("window.__VLONTO_METRICS.lastQuery && window.__VLONTO_METRICS.lastQuery.count === 27", timeout=30000)
        with pg.expect_download(timeout=20000) as d:
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
                "c-changes": kg["change_events"], "c-dec-year": kg["court_decisions"], "c-dec-level": kg["court_decisions"],
                "c-dec-inst": kg["court_decisions"], "c-qa": kg["legal_questions"], "c-terms": kg["legal_terms"], "c-news": kg["news_articles"]}
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

    def year_note():
        # a year range leaves undated records out and says so; reset brings the undated buckets back
        last2 = "echarts.getInstanceByDom(document.getElementById('{}')).getOption().xAxis[0].data.slice(-2)"
        pg.select_option("#f-y0", "2015")
        pg.wait_for_timeout(500)
        t = pg.evaluate("window.VLApp.dashTotals()")
        cap, lo = t["caption"], t["undatedLeftOut"]
        subs = pg.evaluate("['sub-type-year', 'sub-changes', 'sub-dec-year'].map(id => document.getElementById(id).textContent)")
        cats = {cid: pg.evaluate(last2.format(cid)) for cid in ("c-type-year", "c-changes", "c-dec-year")}
        shot = c.shot(pg, "dashboard_year_range")
        pg.click("#f-reset")
        pg.wait_for_timeout(500)
        t2 = pg.evaluate("window.VLApp.dashTotals()")
        cats2 = {cid: pg.evaluate(last2.format(cid)) for cid in ("c-type-year", "c-changes", "c-dec-year")}
        problems = []
        if not (lo["docs"] > 0 and lo["changes"] > 0 and lo["decisions"] > 0):
            problems.append(f"undated counts {lo}")
        for key, words, sub in (("docs", "without an issue year", 0), ("changes", "without an effective date", 1), ("decisions", "without a year", 2)):
            n = lo[key]
            if n and (f"{n:,}" not in cap or words not in cap):
                problems.append(f"filter caption lacks the {key}: {cap!r}")
            if n and (f"{n:,}" not in subs[sub] or "leaves out" not in subs[sub]):
                problems.append(f"chart caption lacks the {key}: {subs[sub]!r}")
        if any(v[-1] in ("no year", "no date") for v in cats.values()):
            problems.append(f"undated bucket still drawn with a year range: {cats}")
        if [v[-1] for v in cats2.values()] != ["no year", "no date", "no year"]:
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
        law_idx = pg.evaluate("Array.from(document.querySelectorAll('#f-type option')).findIndex(o => o.textContent.startsWith('Law ·')) - 1")
        pg.select_option("#f-type", str(law_idx))
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
    out.append({"test": "about", "checks": [
        {"name": "navigation (3D Ontology = index.html first, 8 pages + Paper) and tool cards link to existing pages",
         "pass": len(internal) == 8 and internal[0] == "index.html" and internal[-1] == "about.html" and external == [PAPER_URL] and not missing,
         "details": {"nav": nav, "tools": tools, "missing": missing}},
        {"name": "about.html renders the paper card with BibTeX and Copy; the logo links to index.html",
         "pass": card["title"].startswith("Vietnamese Legal Ontology") and card["copy"] and card["bib"].startswith("@misc{bui2026vietnamese") and card["brand"] == "index.html",
         "details": card}], "log": log})
    ctx.close()
    # the old playground address forwards to index.html, keeping the #hash (deep link to a class). Opened from about.html
    # with wait_until=commit: the stub replaces itself while it loads, which would interrupt a goto waiting for 'load'.
    ctx, pg, log = c.open("about.html")
    try:
        pg.goto(c.url("ontology-3d.html#class=vlo:Article"), wait_until="commit", timeout=60000)
        pg.wait_for_url(re.compile(r".*/index\.html(\?[^#]*)?#class=vlo:Article$"), timeout=30000)
        pg.wait_for_function("window.__VLONTO_READY === true", timeout=180000)
        pg.wait_for_function("window.__VLONTO_METRICS.selected === 'vlo:Article'", timeout=60000)
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
              "playbook.html", "downloads.html"]
SCENES = ("index.html", "network-3d.html")       # pages with a full-screen WebGL scene
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
    pg.wait_for_function("(t) => document.documentElement.getAttribute('data-theme') === t", arg=want, timeout=15000)


def nav_to(c, pg, href):
    """Follow a header navigation link like a visitor (the menu opens first on phones)."""
    if c.mobile:
        pg.locator(".vl-menu-btn").click()
        pg.wait_for_timeout(250)
    with pg.expect_navigation(wait_until="load", timeout=120000):
        pg.locator(f'#vl-nav a[href^="{href}"]').first.click()
    pg.wait_for_function("window.__VLONTO_READY === true", timeout=180000)


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
            ctx, pg, log = c.open(page, scheme="light", ready_timeout=240000)
            try:
                if page == "sparql.html":    # draw a CONSTRUCT result so the 3D view is part of the switch
                    pg.locator("#ex-construct button").first.click()
                    pg.wait_for_function("!!window.__VLONTO_METRICS.constructDrawn", timeout=120000)
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
                pg.wait_for_function("window.__VLONTO_READY === true", timeout=120000)
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
            pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=10000)
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
        ctx, pg, log = c.open("ontology.html", scheme="light")
        try:
            f = doc_frame(pg)
            f.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=15000)
            click_theme(pg, "dark")
            f.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'", timeout=15000)
            bg = f.evaluate("getComputedStyle(document.body).backgroundColor")
            f.locator(".vl-theme-btn").click()
            pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=15000)
            f.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=15000)
            return {"frame_dark_bg": bg, "frame_toggle_switched_page": True}
        finally:
            merge(log)
            ctx.close()
    check("pyLODE iframe follows the page, and its own toggle switches the page", iframe)

    def doc_standalone():
        ctx, pg, log = c.open("ontology/vlonto.html", scheme="dark", ready=False)
        try:
            pg.wait_for_function("!!window.__VLONTO_DOC_THEME", timeout=30000)
            a = pg.evaluate("document.documentElement.getAttribute('data-theme')")
            pg.locator(".vl-theme-btn").click()
            pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=10000)
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
            ctx, pg, log = c.open(page, ready=not page.startswith("ontology/"), ready_timeout=240000)
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
            ctx, pg, log = c.open(page, init_script=init, permissions=perms, ready_timeout=180000)
            try:
                if page == "index.html":
                    open_side(pg)
                btn = pg.locator("[data-copy-bib]").first
                btn.scroll_into_view_if_needed()
                btn.click()
                pg.wait_for_function("!!window.__VLONTO_METRICS.lastCopy", timeout=10000)
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


GALLERY = ["index.html", "about.html", "network-3d.html", "sparql.html", "dashboard.html", "ontology.html",
           "playbook.html", "downloads.html", "ontology/vlonto.html"]


def t_gallery(c: Ctx):
    """Review screenshots (http only): the viewport at the top of every page, and a full-page capture taken after
    scrolling back to the top, so sticky header and filter bars render in place; capped at 10,000 CSS px."""
    if c.mode != "http":
        return []
    shots = []
    for theme in c.themes:
      for page in GALLERY:
        ctx, pg, log = c.open(page, ready=not page.startswith("ontology/"), scheme=theme, ready_timeout=240000)
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
    ap.add_argument("--tests", default="ontology,network,sparql,dashboard,simple,theme,paper,gallery")
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
