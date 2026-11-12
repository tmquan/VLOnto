#!/usr/bin/env python3
"""ci_summary.py - summary of a ci_check.sh run: one row per check (result, exit code, runs, failed runs, minutes),
the first failures, and the merged report (site_test_report.md) folded. Writes OUT/ci/summary.md and
OUT/ci/results.json and, with --append, appends the Markdown to a file such as $GITHUB_STEP_SUMMARY. It reads only
what exists, so it also describes a run that stopped early (setup failure, timeout, cancellation). Standard library only.

    python3 scripts/site/ci_summary.py --out OUT [--append "$GITHUB_STEP_SUMMARY"] [--artifact-url URL]

A check PASSes when its exit code is 0 and its results file says ok; 124 = stopped by CI_CHECK_TIMEOUT. The job's
verdict is ci_check.sh's exit code; this script always exits 0.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

CHECKS = [  # key (ci/rc/<key>), label, results file, kind, log
    ("light", "site_check light", "site_check_light/site_check_report.json", "site_check", "site_check_light/site_check.log"),
    ("dark", "site_check dark", "site_check_dark/site_check_report.json", "site_check", "site_check_dark/site_check.log"),
    ("core", "interactions core", "site_tests/core/interactions.json", "interactions", "site_tests/core/interactions.log"),
    ("theme", "interactions theme", "site_tests/theme/interactions.json", "interactions", "site_tests/theme/interactions.log"),
    ("gallery", "interactions gallery", "site_tests/gallery/interactions.json", "interactions", "site_tests/gallery/interactions.log"),
    ("contrast", "contrast", "site_contrast/contrast.json", "contrast", "site_contrast/contrast.log"),
]
MAX_FAILURES = 60
MAX_BYTES = 900_000          # GitHub keeps at most 1 MiB of summary per step


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rc_of(out: Path, key: str):
    try:
        rc, secs = (out / "ci" / "rc" / key).read_text().split()[:2]
        return int(rc), int(secs)
    except (OSError, ValueError):
        return None, None


def cell(s) -> str:
    return " ".join(str(s).split()).replace("|", "/")


def short(s, n=260) -> str:
    s = cell(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def tail(p: Path, n=6) -> list[str]:
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def uniq(xs):
    return list(dict.fromkeys(x for x in xs if x))


def describe(kind, d):
    """scope, runs, failed runs, failure lines of one results file"""
    fails = []
    if kind == "site_check":
        s = d.get("summary") or {}
        scope = f"{s.get('pages', len(d.get('pages', [])))} pages × {'/'.join(d.get('modes', []))} × {'/'.join(d.get('viewports', []))}"
        for p in d.get("pages", []):
            fails += [f"`{p['page']}` static lint: {short(l.get('message'))}" for l in p.get("lint", []) if l.get("severity") == "fail"]
            for r in p.get("runs", []):
                if not r.get("ok"):
                    f = r.get("failures") or ["failed"]
                    fails.append(f"`{r.get('page')}` {r.get('mode')} {r.get('viewport')}: {short('; '.join(map(str, f[:3])))}"
                                 + (f" (+{len(f) - 3} more)" if len(f) > 3 else ""))
        extra = f", {s.get('lint_failures', 0)} lint" if s.get("lint_failures") else ""
        return scope, s.get("runs"), f"{s.get('failed_runs')}{extra}", fails
    if kind == "interactions":
        res = d.get("results", [])
        scope = (", ".join(uniq(r.get("test") for r in res)) or "-") + \
            f" × {'/'.join(uniq(r.get('mode') for r in res))} × {'/'.join(uniq(r.get('viewport') for r in res))}"
        for r in res:
            if r.get("pass"):
                continue
            where = f"{r.get('test')} {r.get('mode')} {r.get('viewport')}"
            if r.get("error"):
                fails.append(f"{where}: harness error: {short(r['error'])}")
            for ch in r.get("checks", []):
                if not ch.get("pass"):
                    det = ch.get("details")
                    det = det.get("error", det) if isinstance(det, dict) else det
                    fails.append(f"{where}: {short(ch.get('name'), 120)}: {short(json.dumps(det, ensure_ascii=False) if not isinstance(det, str) else det)}")
            lg = {k: len(v) for k, v in (r.get("log") or {}).items() if isinstance(v, list) and v}
            if lg:
                fails.append(f"{where}: page log {json.dumps(lg)}")
        s = d.get("summary") or {}
        return scope, s.get("runs"), s.get("failed"), fails
    s = d.get("summary") or {}                                   # contrast
    pages = d.get("pages", [])
    scope = f"{len(uniq(p.get('page') for p in pages))} pages × {'/'.join(d.get('themes', []))} × {'/'.join(d.get('viewports', []))}"
    for p in pages:
        if p.get("pass"):
            continue
        where = f"`{p.get('page')}` {p.get('theme')} {p.get('viewport')}"
        if p.get("error"):
            fails.append(f"{where}: {short(p['error'])}")
            continue
        first = (p.get("text_fail") or []) + (p.get("ui_fail") or [])
        why = f"{len(p.get('text_fail') or [])} text below AA, {len(p.get('ui_fail') or [])} UI below 3:1"
        if p.get("applied") != p.get("theme"):
            why += f"; theme applied {p.get('applied')}"
        if first:
            t = first[0]
            why += f"; first: `{short(t.get('sel'), 80)}` ratio {t.get('p10', t.get('ratio'))} need {t.get('need')}"
        fails.append(f"{where}: {why}")
    extra = f" (text {s.get('text_checked')}/{s.get('text_fails')} fail, UI {s.get('ui_checked')}/{s.get('ui_fails')} fail)" if s else ""
    return scope + extra, s.get("runs"), s.get("failed_runs"), fails


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--append", type=Path, default=None, help="also append the Markdown to this file")
    ap.add_argument("--artifact-url", default="")
    a = ap.parse_args(argv)
    out = a.out
    run = load(out / "ci" / "run.json") or {}
    tool = load(out / "ci" / "toolchain.json") or {}
    rows, failures, results = [], [], []
    any_rc = False
    for key, label, rel, kind, log in CHECKS:
        rc, secs = rc_of(out, key)
        any_rc = any_rc or rc is not None
        d = load(out / rel)
        scope, runs, failed, fails = describe(kind, d) if d else ("-", None, None, [])
        if rc is None:
            result = "not run" if d is None else "unfinished"
        elif rc == 0 and d and d.get("ok") is True:
            result = "PASS"
        elif rc == 124:
            result = "TIMEOUT"
        else:
            result = "FAIL"
        if result != "PASS" and rc is not None and not fails:
            lines = tail(out / log)
            fails = [f"exit {rc}, no failure recorded in {rel}; last log lines: " + short(" ⏎ ".join(lines), 600)]
        failures += [f"- **{label}** {f}" for f in fails]
        rows.append(f"| {label} | {cell(scope)} | **{result}** | {'' if rc is None else rc} | {'' if runs is None else runs} | "
                    f"{'' if failed is None else failed} | {'' if secs is None else round(secs / 60, 1)} |")
        results.append({"check": key, "label": label, "result": result, "exit": rc, "seconds": secs, "runs": runs,
                        "failed": failed, "results_file": rel if d is not None else None, "log": log})
    rrc, _ = rc_of(out, "report")
    rep = load(out / "site_tests" / "site_test_report.json")
    rep_ok = bool(rep and rep.get("ok") is True and rrc == 0)
    rows.append(f"| report | make_report.py: site_test_report.md/.json | **{'PASS' if rep_ok else ('not run' if rrc is None else 'FAIL')}** | "
                f"{'' if rrc is None else rrc} |  |  |  |")
    ok = any_rc and all(r["result"] == "PASS" for r in results) and rep_ok
    verdict = "PASS" if ok else ("NOT RUN" if not any_rc else "FAIL")
    env = os.environ
    ctx = []
    if env.get("GITHUB_SHA"):
        ctx.append(f"commit `{env['GITHUB_SHA'][:12]}` on `{env.get('GITHUB_REF_NAME', '?')}`, run {env.get('GITHUB_RUN_ID', '?')}"
                   f" (attempt {env.get('GITHUB_RUN_ATTEMPT', '1')})")
    if tool:
        ctx.append(f"{tool.get('browser') and 'Chrome for Testing ' + tool['browser'] or 'browser ?'} (WebGL: {tool.get('webgl_renderer')}), "
                   f"Python {tool.get('python')}, Playwright {(tool.get('packages') or {}).get('playwright')}; "
                   f"{tool.get('os')}, {tool.get('cpus')} CPUs, {tool.get('mem_gib')} GiB")
    if run:
        ctx.append(f"{run.get('parallel')} checks at a time, limit {run.get('check_timeout')} each, wall {round((run.get('wall_s') or 0) / 60, 1)} min")
    L = [f"## VLOnto site checks: **{verdict}**", ""] + [f"- {c}" for c in ctx]
    if a.artifact_url:
        L.append(f"- screenshots, gallery images, logs and reports: [site-check-{env.get('GITHUB_RUN_ID', 'run')}]({a.artifact_url})")
    if not any_rc:
        L += ([""] if len(L) > 2 else []) + ["No check ran (see the setup step's log)."]
    L += ["", "| check | scope | result | exit | runs | failed | min |", "|---|---|---|---:|---:|---:|---:|"] + rows
    if failures:
        L += ["", f"### Failures ({len(failures)}{', first ' + str(MAX_FAILURES) if len(failures) > MAX_FAILURES else ''})", ""]
        L += failures[:MAX_FAILURES]
    md_path = out / "site_tests" / "site_test_report.md"
    if md_path.exists():
        body = md_path.read_text(encoding="utf-8")
        result_line = next((l for l in body.splitlines() if l.startswith("- result:")), "")
        if result_line:
            L += ["", "### Merged report", "", result_line.rstrip()]
        room = MAX_BYTES - len("\n".join(L).encode("utf-8")) - 400
        if len(body.encode("utf-8")) > room:
            body = body.encode("utf-8")[:max(room, 0)].decode("utf-8", "ignore") + "\n\n… (truncated; full file in the artifact)\n"
        L += ["", "<details><summary>site_test_report.md</summary>", "", body, "</details>"]
    text = "\n".join(L) + "\n"
    (out / "ci").mkdir(parents=True, exist_ok=True)
    (out / "ci" / "summary.md").write_text(text, encoding="utf-8")
    (out / "ci" / "results.json").write_text(json.dumps({"verdict": verdict, "ok": ok, "checks": results,
                                                          "report": {"exit": rrc, "ok": rep_ok}, "run": run, "toolchain": tool},
                                                         ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.append:
        with open(a.append, "a", encoding="utf-8") as f:
            f.write(text)
    print(f"ci_summary: {verdict} ({sum(r['result'] == 'PASS' for r in results)}/{len(results)} checks pass, "
          f"{len(failures)} failure lines) -> {out / 'ci' / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
