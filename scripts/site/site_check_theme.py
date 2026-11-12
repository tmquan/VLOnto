#!/usr/bin/env python3
"""site_check_theme.py - run the toolchain's tools/site_check.py, unchanged, in one colour scheme.

    $W/python scripts/site/site_check_theme.py --color-scheme dark -- --root site --config scripts/site/site_check_pages.json --out DIR

Every browser context that site_check opens gets Playwright's color_scheme (the emulated prefers-color-scheme). The
site has no stored choice in a fresh context, so each page renders in that theme; all checks, outputs and the exit
code are site_check's own. (site_check takes page paths that must exist as files, so ?theme= cannot be used there.)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    argv = sys.argv[1:]
    scheme = "light"
    if "--color-scheme" in argv:
        i = argv.index("--color-scheme")
        scheme = argv[i + 1]
        del argv[i:i + 2]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if scheme not in ("light", "dark"):
        print(f"--color-scheme must be light or dark, not {scheme}", file=sys.stderr)
        return 2
    tool = HERE.parent.parent / "tools" / "site_check.py"          # repo/scripts/site -> repo/tools
    spec = importlib.util.spec_from_file_location("site_check", tool)
    sc = importlib.util.module_from_spec(spec)
    sys.modules["site_check"] = sc
    spec.loader.exec_module(sc)
    original = sc.run_one

    class Browser:
        """the real browser, except that new contexts emulate the colour scheme"""
        def __init__(self, b):
            self._b = b

        def new_context(self, **kw):
            kw.setdefault("color_scheme", scheme)
            return self._b.new_context(**kw)

        def __getattr__(self, name):
            return getattr(self._b, name)

    def run_one(browser, *a, **k):
        return original(Browser(browser), *a, **k)

    sc.run_one = run_one
    print(f"site_check.py in colour scheme '{scheme}' ({tool})", flush=True)
    return sc.main(argv)


if __name__ == "__main__":
    sys.exit(main())
