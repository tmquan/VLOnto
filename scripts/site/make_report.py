#!/usr/bin/env python3
"""make_report.py - merge site_check (one run per theme), the interaction tests (one or more result folders), the
contrast check and the build report into site_test_report.md / .json.

    $W/python scripts/site/make_report.py --site-check light=$V/build/site_check_light --site-check dark=$V/build/site_check_dark \
        --tests $V/build/site_tests/core --tests $V/build/site_tests/theme --tests $V/build/site_tests/gallery \
        --contrast $V/build/site_contrast --build $V/build/site_build_report.json --out $V/build/site_tests
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-check", action="append", required=True, help="THEME=DIR (or DIR) of a site_check run; repeatable")
    ap.add_argument("--tests", type=Path, action="append", required=True, help="folder with interactions.json; repeatable")
    ap.add_argument("--contrast", type=Path, default=None, help="folder with contrast.json")
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--bundle", type=Path, default=None)
    a = ap.parse_args(argv)
    scs = []
    for spec in a.site_check:
        theme, _, d = spec.partition("=") if "=" in spec else ("default", "", spec)
        scs.append((theme, load(Path(d) / "site_check_report.json") or {}))
    its = [load(d / "interactions.json") or {"ok": False, "summary": {"runs": 0, "failed": 1}, "missing": str(d)} for d in a.tests]
    it = {"results": [r for x in its for r in x.get("results", [])],
          "summary": {"runs": sum((x.get("summary") or {}).get("runs", 0) for x in its),
                      "failed": sum((x.get("summary") or {}).get("failed", 0) for x in its)},
          "ok": all(x.get("ok") for x in its)}
    ct = load(a.contrast / "contrast.json") if a.contrast else None
    bd = load(a.build) or {}
    bundle = load(a.bundle) if a.bundle else None
    runs = []
    for theme, sc in scs:
      for p in sc.get("pages", []):
        lint_fail = [l["message"] for l in p.get("lint", []) if l["severity"] == "fail"]
        for r in p.get("runs", []):
            cv = r.get("canvases", [])
            gc = r.get("glyph_coverage", {})
            runs.append({
                "theme": theme,
                "page": r["page"], "mode": r["mode"], "viewport": r["viewport"], "ok": r["ok"] and not lint_fail,
                "failures": r.get("failures", []) + [f"static_lint: {m}" for m in lint_fail],
                "warnings": r.get("warnings", []),
                "console_errors": len(r.get("console_errors", [])), "page_errors": len(r.get("page_errors", [])),
                "failed_requests": len(r.get("failed_requests", [])), "external_requests": len(r.get("external_requests", [])),
                "canvases_nonblank": sum(1 for c in cv if c.get("nonblank")), "canvases": len(cv),
                "overflow_px": max(0, (r.get("page_overflow") or {}).get("overflowPx", 0)),
                "clipped": len(r.get("clipped_text", [])), "overlaps": len(r.get("text_overlap", [])),
                "broken_words": len(r.get("broken_words", [])), "uncovered_glyphs": len(gc.get("uncovered", [])),
                "decomposed_glyphs": len(gc.get("decomposed", [])), "load_s": r.get("load_s"),
                "fonts_loaded": sorted({f["family"] for f in r.get("font_faces", []) if f.get("status") == "loaded"}),
                "platform_fonts": r.get("platform_fonts"), "metrics": r.get("metrics"), "screenshot": r.get("screenshot"),
                "webgl": r.get("webgl"),
            })
    fps = []
    for r in runs:
        m = r.get("metrics") or {}
        if m.get("fps") is not None:
            fps.append({"source": f"site_check (page load, {r['theme']})", "page": r["page"], "mode": r["mode"], "viewport": r["viewport"],
                        "dataset": m.get("dataset"), "nodes": m.get("nodes") or m.get("graphNodes"), "fps": m.get("fps"), "renderer": m.get("webglRenderer")})
    for r in it.get("results", []):
        for ch in r.get("checks", []):
            d = ch.get("details") if isinstance(ch.get("details"), dict) else {}
            if "fps" in d:
                fps.append({"source": "interaction test", "page": r["test"], "mode": r["mode"], "viewport": r["viewport"],
                            "dataset": d.get("dataset"), "nodes": d.get("nodes"), "edges": d.get("edges"), "fps": d.get("fps"), "renderer": d.get("renderer")})
    sc_runs = sum((sc.get("summary") or {}).get("runs", 0) for _, sc in scs)
    sc_failed = sum((sc.get("summary") or {}).get("failed_runs", 0) for _, sc in scs)
    sc_lint = sum((sc.get("summary") or {}).get("lint_failures", 0) for _, sc in scs)
    sc_ok = all(bool(sc.get("ok")) for _, sc in scs) and sc_runs > 0
    it_ok = bool(it.get("ok"))
    ct_ok = bool(ct.get("ok")) if ct else None
    first = scs[0][1] if scs else {}
    rep = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "browser": first.get("browser_version"), "chrome": first.get("chrome"),
        "site_check": {"ok": sc_ok, "themes": [t for t, _ in scs], "summary": {"runs": sc_runs, "failed_runs": sc_failed, "lint_failures": sc_lint},
                       "summary_by_theme": {t: sc.get("summary") for t, sc in scs}, "runs": runs},
        "interactions": {"ok": it_ok, "summary": it.get("summary"), "results": it.get("results", [])},
        "contrast": ({"ok": ct_ok, "summary": ct.get("summary"), "pages": [{k: v for k, v in p.items() if k not in ("text", "ui")} for p in ct.get("pages", [])]}
                     if ct else None),
        "fps": fps, "build": bd, "bundle": bundle,
        "notes": [
            "Rendering is tested in headless Chromium (chrome-headless-shell 157) only; Firefox and Safari were not machine-tested on the node.",
            "WebGL runs on SwiftShader (CPU rasteriser) on the build node; frame rates on laptop GPUs are much higher.",
            "Canvas text (3D labels, chart labels) is invisible to DOM checks; the screenshots were inspected by eye.",
            "Themes: site_check ran once per theme with the browser's colour scheme emulated (the site follows it when no choice is stored); "
            "the interaction tests cover the toggle, ?theme=, persistence and live re-rendering.",
        ],
    }
    rep["ok"] = sc_ok and it_ok and (ct_ok is not False) and bool(bd.get("ok", True))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "site_test_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    L = ["# VLOnto website - test report", "",
         f"- generated: {rep['generated']}  ", f"- browser: {rep['browser']} (`tools/chrome.sh`, SwiftShader WebGL)  ",
         f"- result: **{'PASS' if rep['ok'] else 'FAIL'}** - site_check {'PASS' if sc_ok else 'FAIL'} "
         f"({sc_failed} of {sc_runs} runs failed over themes {', '.join(t for t, _ in scs)}, {sc_lint} lint failures); "
         f"interactions {'PASS' if it_ok else 'FAIL'} "
         f"({(it.get('summary') or {}).get('failed', '?')} of {(it.get('summary') or {}).get('runs', '?')} runs failed)"
         + (f"; contrast {'PASS' if ct_ok else 'FAIL'} ({ct['summary']['text_checked']} text elements, {ct['summary']['text_fails']} below AA; "
            f"{ct['summary']['ui_checked']} UI checks, {ct['summary']['ui_fails']} below 3:1)" if ct else ""), ""]
    if bd:
        L += [f"- site: {bd.get('files')} files, {bd.get('total_bytes', 0) / 1048576:.1f} MB; largest file "
              f"{(bd.get('largest') or [{}])[0].get('path')} ({(bd.get('largest') or [{}])[0].get('bytes', 0) / 1048576:.1f} MB); "
              f"non-NFC files: {len(bd.get('non_nfc', []))}; files over 50 MB: {len(bd.get('over_50MB', []))}", ""]
    if bundle:
        L += [f"- bundle: `{bundle.get('path')}` {bundle.get('bytes', 0) / 1048576:.1f} MB, sha256 `{bundle.get('sha256')}`", ""]
    L += ["## Render checks (site_check: every page x theme x http/file x 1440x900/390x844)", "",
          "| page | theme | mode | viewport | result | console err | failed req | external | canvases | overflow px | clipped | overlaps | broken words | uncovered glyphs | load s |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        L.append(f"| {r['page']} | {r['theme']} | {r['mode']} | {r['viewport']} | {'PASS' if r['ok'] else 'FAIL'} | {r['console_errors'] + r['page_errors']} | {r['failed_requests']} | "
                 f"{r['external_requests']} | {r['canvases_nonblank']}/{r['canvases']} | {r['overflow_px']} | {r['clipped']} | {r['overlaps']} | {r['broken_words']} | "
                 f"{r['uncovered_glyphs']} | {r['load_s']} |")
    bad = [r for r in runs if not r["ok"]]
    if bad:
        L += ["", "### Failures", ""]
        for r in bad:
            for f in r["failures"][:12]:
                L.append(f"- [{r['page']} {r['theme']} {r['mode']} {r['viewport']}] {f}")
    if ct:
        L += ["", "## Contrast (WCAG AA, rendered pages over http; details in contrast_report.md)", "",
              "| page | theme | viewport | text checked | text below AA | UI checked | UI below 3:1 | result |", "|---|---|---|---:|---:|---:|---:|---|"]
        for p in ct.get("pages", []):
            L.append(f"| {p['page']} | {p['theme']} | {p['viewport']} | {p.get('text_checked', 0)} | {len(p.get('text_fail', []))} | "
                     f"{len(p.get('ui', []))} | {len(p.get('ui_fail', []))} | {'PASS' if p.get('pass') else 'FAIL'} |")
    L += ["", "## Interaction tests (Playwright)", "", "| test | mode | viewport | check | result | details |", "|---|---|---|---|---|---|"]
    for r in it.get("results", []):
        for ch in r.get("checks", []):
            d = ch.get("details")
            if isinstance(d, dict):
                d = {k: v for k, v in d.items() if k not in ("shot", "rows", "construct", "all", "law", "law_area", "law_area_2015", "reset")}
            txt = json.dumps(d, ensure_ascii=False)[:220].replace("|", "/")
            L.append(f"| {r['test']} | {r['mode']} | {r['viewport']} | {ch['name']} | {'PASS' if ch['pass'] else 'FAIL'} | {txt} |")
        lg = r.get("log") or {}
        extra = {k: len(v) for k, v in lg.items() if isinstance(v, list) and v}
        if extra:
            L.append(f"| {r['test']} | {r['mode']} | {r['viewport']} | page log | FAIL | {json.dumps(extra)} |")
    L += ["", "## Frame rates (SwiftShader, CPU WebGL on the build node)", "", "| page | source | mode | viewport | dataset | nodes | fps |", "|---|---|---|---|---|---|---|"]
    for f in fps:
        L.append(f"| {f['page']} | {f['source']} | {f['mode']} | {f['viewport']} | {f.get('dataset') or ''} | {f.get('nodes') or ''} | {f['fps']} |")
    L += ["", "## Notes", ""] + [f"- {n}" for n in rep["notes"]]
    (a.out / "site_test_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"site_test_report: {'PASS' if rep['ok'] else 'FAIL'} -> {a.out / 'site_test_report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
