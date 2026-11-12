#!/usr/bin/env python3
"""ci_requirements.py - the part of tools/requirements-web.lock that the website checks need, for CI.

    python scripts/site/ci_requirements.py --out requirements-test.lock [--lock tools/requirements-web.lock] [--check-imports]

Copies, unchanged (exact versions and sha256 hashes), the lock entries of the packages the check scripts import and of
everything those depend on according to the lock's "# via" annotations:
    playwright -> greenlet; pillow; beautifulsoup4 -> soupsieve, typing-extensions; fonttools -> brotli, zopfli; numpy
The result is installed with `pip install --require-hashes --no-deps -r <out>` (the node syncs the whole lock with
`uv pip sync --require-hashes`; the build-only packages - pandoc, node, pymupdf, ... - are not needed to test the site).
--check-imports parses the check scripts and fails when one imports a third-party module that is not covered, so a new
import shows up at setup time instead of as an ImportError in the middle of a run.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
# top-level module imported by a check script -> distribution in the lock
IMPORTS = {"playwright": "playwright", "PIL": "pillow", "bs4": "beautifulsoup4", "fontTools": "fonttools", "numpy": "numpy"}
SCRIPTS = ["tools/site_check.py", "scripts/site/site_check_theme.py", "scripts/site/interaction_tests.py",
           "scripts/site/contrast_check.py", "scripts/site/make_report.py", "scripts/site/ci_pages.py",
           "scripts/site/ci_summary.py", "scripts/site/ci_requirements.py"]


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(text: str):
    """[(name, version, block_text, via_parents)] in lock order; block_text is the entry verbatim"""
    entries, cur = [], None
    for line in text.splitlines(keepends=True):
        m = re.match(r"([A-Za-z0-9][A-Za-z0-9_.\-]*)==([^\s;\\]+)", line)
        if m:
            cur = {"name": norm(m.group(1)), "version": m.group(2), "lines": [line], "via": []}
            entries.append(cur)
            continue
        if cur is None:
            continue
        cur["lines"].append(line)
        s = line.strip()
        v = re.match(r"#\s+via\s*(.*)$", s)
        if v:
            cur["in_via"] = True
            if v.group(1):
                cur["via"].append(v.group(1).strip())
        elif cur.get("in_via") and re.match(r"#\s{2,}\S", s):
            cur["via"].append(s.lstrip("#").strip())
    out = []
    for e in entries:
        parents = [norm(p) for p in e["via"] if not p.startswith("-r ")]
        out.append((e["name"], e["version"], "".join(e["lines"]), parents))
    return out


def closure(entries, roots):
    have = {n for n, *_ in entries}
    missing = sorted(r for r in roots if r not in have)
    if missing:
        raise SystemExit(f"ci_requirements: not in the lock: {', '.join(missing)}")
    keep = set(roots)
    changed = True
    while changed:
        changed = False
        for name, _, _, parents in entries:
            if name not in keep and any(p in keep for p in parents):
                keep.add(name)
                changed = True
    return keep


def third_party_imports(path: Path):
    mods = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    return {m for m in mods if m not in sys.stdlib_module_names and m != "__future__"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lock", type=Path, default=REPO / "tools" / "requirements-web.lock")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--check-imports", action="store_true")
    a = ap.parse_args(argv)
    if a.check_imports:
        bad = []
        for rel in SCRIPTS:
            p = REPO / rel
            if not p.is_file():
                bad.append(f"{rel}: missing")
                continue
            bad += [f"{rel}: imports {m}, which is not in IMPORTS" for m in sorted(third_party_imports(p) - set(IMPORTS))]
        if bad:
            print("ci_requirements: " + "; ".join(bad), file=sys.stderr)
            return 1
        print(f"ci_requirements: the {len(SCRIPTS)} check scripts import only {', '.join(sorted(IMPORTS))} besides the standard library")
    entries = parse_lock(a.lock.read_text(encoding="utf-8"))
    keep = closure(entries, {norm(d) for d in IMPORTS.values()})
    picked = [(n, v, block) for n, v, block, _ in entries if n in keep]
    head = (f"# Test-time subset of {a.lock.name} written by scripts/site/ci_requirements.py: the packages the website\n"
            f"# checks import and their dependencies, entries copied unchanged (versions and hashes).\n")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(head + "".join(block if block.endswith("\n") else block + "\n" for _, _, block in picked), encoding="utf-8")
    print(f"ci_requirements: {len(picked)} of {len(entries)} locked packages -> {a.out.name}: "
          + ", ".join(f"{n}=={v}" for n, v, _ in picked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
