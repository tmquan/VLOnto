#!/usr/bin/env python3
"""ci_pages.py - run interaction_tests.py or contrast_check.py unchanged, with every page of site_check_pages.json in
its page lists, so that a page added to the config (e.g. traces.html) is also contrast-checked, screenshotted in both
themes, theme-toggled and checked for the paper link, without editing the test scripts.

    python scripts/site/ci_pages.py --config scripts/site/site_check_pages.json -- scripts/site/interaction_tests.py ARGS
    python scripts/site/ci_pages.py --config scripts/site/site_check_pages.json --list -- scripts/site/contrast_check.py

Lists extended (pages already listed keep their place; new pages are appended in config order):
  interaction_tests.py  GALLERY     every page of the config
                        SITE_PAGES  pages with a "ready" condition outside ontology/ (the site's own pages, which carry
                                    the standard header and footer; the pyLODE document has no ready flag)
  contrast_check.py     PAGES       every page of the config (the default of --pages)
Page-specific behaviour stays in the scripts (SCENES, the per-page interaction tests, the navigation count of the about
test). With the current config nothing is added, so the checks are exactly those of scripts/site/check.sh.
--list prints the resulting lists and exits. Exit code: the script's own (0 pass, 1 failures); 2 on a usage error.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

LISTS = {"interaction_tests": ("GALLERY", "SITE_PAGES"), "contrast_check": ("PAGES",)}


def config_pages(path: Path):
    pages = json.loads(path.read_text(encoding="utf-8"))["pages"]
    every = [p["path"] for p in pages]
    site = [p["path"] for p in pages if p.get("ready") and not p["path"].startswith("ontology/")]
    return every, site


def main() -> int:
    argv = sys.argv[1:]
    if "--" not in argv:
        print(__doc__, file=sys.stderr)
        return 2
    i = argv.index("--")
    own, rest = argv[:i], argv[i + 1:]
    if not rest or "--config" not in own or own.index("--config") + 1 >= len(own):
        print("usage: ci_pages.py --config PAGES_JSON [--list] -- SCRIPT [ARGS]", file=sys.stderr)
        return 2
    cfg = Path(own[own.index("--config") + 1])
    script = Path(rest[0]).resolve()
    name = script.stem
    if name not in LISTS:
        print(f"ci_pages.py: {script.name} has no page lists to extend (supported: {', '.join(LISTS)})", file=sys.stderr)
        return 2
    every, site = config_pages(cfg)
    spec = importlib.util.spec_from_file_location(name, script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    added = {}
    for attr in LISTS[name]:
        cur = getattr(mod, attr, None)
        if not isinstance(cur, list):
            print(f"ci_pages.py: {script.name} has no list {attr}", file=sys.stderr)
            return 2
        new = [p for p in (site if attr == "SITE_PAGES" else every) if p not in cur]
        cur.extend(new)          # in place: the test functions read these module globals when they run
        added[attr] = new
    what = "; ".join(f"{k} +{v}" for k, v in added.items() if v) or "nothing (the lists already cover every page)"
    print(f"ci_pages.py: {script.name} with the pages of {cfg.name}: added {what}", flush=True)
    if "--list" in own:
        for attr in LISTS[name]:
            print(f"{attr} = {getattr(mod, attr)}")
        return 0
    sys.argv = [str(script)] + rest[1:]
    return mod.main(rest[1:])


if __name__ == "__main__":
    sys.exit(main())
