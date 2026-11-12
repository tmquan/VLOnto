#!/usr/bin/env python3
"""make_font_metrics.py - advance widths of the vendored Libertinus Sans faces for build-time text measurement.

    python scripts/site/make_font_metrics.py            # writes scripts/site/font_metrics_libertinus.json
    python scripts/site/make_font_metrics.py --check    # exit 1 when the JSON differs from the fonts

The question-trace figures (traces.html) place their call-out boxes at build time (scripts/site/trace_layout.py, stdlib
only), so the box sizes come from the same font the browser draws them with: the Latin + Vietnamese subsets of
Libertinus Sans 7.051 in site/fonts/ (tools/vendor_build.py, pinned in tools/versions.lock). This script reads their
cmap and hmtx tables with fontTools (in tools/requirements-web.lock) and stores, per face, the advance width of every
mapped code point in font units. Kerning is not stored: the layout adds a safety margin instead. Re-run it when the
vendored fonts change; the output is deterministic.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FACES = {"regular": "LibertinusSans-Regular.subset.woff2", "italic": "LibertinusSans-Italic.subset.woff2",
         "bold": "LibertinusSans-Bold.subset.woff2"}
OUT = HERE / "font_metrics_libertinus.json"


def runs(widths: dict) -> list:
    """[[first code point, [advance, ...]], ...] for runs of consecutive code points"""
    out, cur = [], None
    for cp in sorted(widths):
        if cur and cp == cur[0] + len(cur[1]):
            cur[1].append(widths[cp])
        else:
            cur = [cp, [widths[cp]]]
            out.append(cur)
    return out


def build() -> dict:
    from fontTools.ttLib import TTFont        # build-time tool only; the layout itself is stdlib
    faces, head = {}, None
    for key, name in FACES.items():
        f = TTFont(str(REPO / "site" / "fonts" / name))
        cmap, hmtx = f.getBestCmap(), f["hmtx"]
        if head is None:
            head = {"units_per_em": f["head"].unitsPerEm, "ascent": f["hhea"].ascent, "descent": -f["hhea"].descent}
        faces[key] = {"file": f"site/fonts/{name}", "runs": runs({cp: hmtx[g][0] for cp, g in cmap.items()}),
                      "fallback": hmtx[cmap[ord("o")]][0]}
    return {"generated_by": "scripts/site/make_font_metrics.py", "font": "Libertinus Sans 7.051 (Latin + Vietnamese subset)",
            **head, "faces": faces}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, separators=(",", ":")) + "\n"
    if a.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{OUT.name}: {'up to date' if ok else 'DIFFERS from the fonts (re-run make_font_metrics.py)'}")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
