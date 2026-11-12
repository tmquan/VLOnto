#!/usr/bin/env python3
"""Glyph-coverage report for Vietnamese text + required symbols (fontTools).

Checks every font file given, and optional font *stacks* (role = ordered fallback list),
against these character sets:

  ascii            printable ASCII U+0020-U+007E (required)
  vi_letters       all 146 Vietnamese letters: a ă â e ê i o ô ơ u ư y (upper/lower) x 6 tones
                   (ngang, huyền, sắc, hỏi, ngã, nặng) as NFC precomposed code points, plus đ Đ (required)
  symbols          → ← ✓ ✗ • – — “ ” ‘ ’ … § ≤ ≥ × ° ² (required)
  extra_symbols    ₫ « » ↔ ⇒ ≠ ± © ® ™ ½ (informational)
  combining        U+0300 U+0301 U+0303 U+0309 U+0323 U+0302 U+0306 U+031B (informational; NFD text)

A character counts as covered only if the cmap maps it to a glyph that has an outline
(non-empty glyf/CFF charstring); space-like characters are exempt from the outline test.

Stacks are walked in order like HarfBuzz/Typst/browsers do: the first font that maps a character draws it; a font
that lacks a precomposed character but maps all pieces of its canonical decomposition (Noto Serif: ≠ = "=" +
U+0338) would draw those pieces (misplaced overlay), so that counts as not covered. A stack entry can be limited
to code point ranges, like Typst `covers` / CSS `unicode-range`: path/to/font.ttf{2190-21FF;2200-22FF}.

Usage
  font_coverage.py FONT [FONT ...] [--stack ROLE=FONT1,FONT2{2190-21FF},...] [--json out.json] [--md out.md]
                   [--require-full]
  --require-full   exit 1 if any stack (or, without stacks, any font) misses a required character.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from fontTools.ttLib import TTFont

VOWELS = "aăâeêioôơuưy"
TONES = ["", "\u0300", "\u0301", "\u0309", "\u0303", "\u0323"]


def vietnamese_letters() -> list[str]:
    out = []
    for v in VOWELS + VOWELS.upper():
        for t in TONES:
            s = unicodedata.normalize("NFC", v + t)
            assert len(s) == 1, (v, t, s)
            out.append(s)
    out += ["đ", "Đ"]
    return out


CHARSETS = {
    "ascii": [chr(c) for c in range(0x20, 0x7F)],
    "vi_letters": vietnamese_letters(),
    "symbols": list("→←✓✗•–—“”‘’…§≤≥×°²"),
    "extra_symbols": list("₫«»↔⇒≠±©®™½"),
    "combining": ["\u0300", "\u0301", "\u0303", "\u0309", "\u0323", "\u0302", "\u0306", "\u031B"],
}
REQUIRED = ("ascii", "vi_letters", "symbols")
SPACE_LIKE = {0x20, 0xA0, 0x2002, 0x2003, 0x2009, 0x200A, 0x202F}


def _name(font: TTFont, *ids: int) -> str:
    table = font["name"]
    for i in ids:
        rec = table.getDebugName(i)
        if rec:
            return rec
    return ""


class FontInfo:
    def __init__(self, path: Path):
        self.path = path
        self.font = TTFont(str(path), fontNumber=0, lazy=True)
        self.cmap = self.font.getBestCmap() or {}
        self.family = _name(self.font, 16, 1)
        self.style = _name(self.font, 17, 2)
        self.psname = _name(self.font, 6)
        self.version = _name(self.font, 5)
        self.license = _name(self.font, 13)[:120]
        self.is_variable = "fvar" in self.font
        self._glyf = self.font["glyf"] if "glyf" in self.font else None
        self._cff = None
        if "CFF " in self.font:
            self._cff = self.font["CFF "].cff.topDictIndex[0].CharStrings
        self._outline_cache: dict[str, bool] = {}

    def has_outline(self, gname: str) -> bool:
        if gname in self._outline_cache:
            return self._outline_cache[gname]
        ok = True
        try:
            if self._glyf is not None:
                g = self._glyf[gname]
                ok = g.numberOfContours != 0  # -1 = composite (non-empty), >0 = contours
            elif self._cff is not None:
                cs = self._cff[gname]
                ok = cs.calcBounds(self._cff) is not None
        except Exception:
            ok = True  # unknown outline format: trust the cmap
        self._outline_cache[gname] = ok
        return ok

    def covers(self, ch: str) -> bool:
        cp = ord(ch)
        g = self.cmap.get(cp)
        if g is None:
            return False
        if cp in SPACE_LIKE or unicodedata.category(ch) in ("Zs", "Mn", "Cc"):
            return True
        return self.has_outline(g)

    def features(self) -> dict:
        out = {}
        for tag in ("GSUB", "GPOS"):
            if tag in self.font and self.font[tag].table.FeatureList:
                out[tag] = sorted({fr.FeatureTag for fr in self.font[tag].table.FeatureList.FeatureRecord})
        return out


def font_report(fi: FontInfo) -> dict:
    rep = {
        "file": str(fi.path),
        "family": fi.family,
        "style": fi.style,
        "postscript_name": fi.psname,
        "version": fi.version,
        "variable": fi.is_variable,
        "glyphs": len(fi.font.getGlyphOrder()),
        "cmap_size": len(fi.cmap),
        "license_name_id13": fi.license,
        "gpos_mark": "mark" in fi.features().get("GPOS", []),
        "gpos_mkmk": "mkmk" in fi.features().get("GPOS", []),
        "sets": {},
    }
    for name, chars in CHARSETS.items():
        missing = [c for c in chars if not fi.covers(c)]
        rep["sets"][name] = {
            "total": len(chars),
            "covered": len(chars) - len(missing),
            "missing": [f"U+{ord(c):04X} {c if unicodedata.category(c) != 'Mn' else '◌' + c}" for c in missing],
        }
    rep["required_ok"] = all(rep["sets"][s]["covered"] == rep["sets"][s]["total"] for s in REQUIRED)
    return rep


def stack_report(role: str, fonts: list[tuple[FontInfo, list | None]]) -> dict:
    """Walk the stack in order like HarfBuzz/Typst/browsers: the first font that maps the character wins; a font that
    lacks it but maps all pieces of its canonical decomposition (e.g. Noto Serif for ≠ = '=' + U+0338) would draw it
    from those pieces, which counts as NOT covered. Entries may be restricted to code point ranges."""
    def label(fi, rng):
        return f"{fi.family} {fi.style} ({fi.path.name})" + (f" only {'; '.join(f'U+{a:04X}-{b:04X}' for a, b in rng)}" if rng else "")
    rep = {"role": role, "fonts": [label(f, r) for f, r in fonts], "sets": {}}
    primary = next((k for k, (_f, r) in enumerate(fonts) if not r), 0)  # first unrestricted entry = the text font
    for name, chars in CHARSETS.items():
        missing, provider, decomposed = [], {}, {}
        for c in chars:
            cp, verdict = ord(c), None
            for k, (f, rng) in enumerate(fonts):
                if rng and not any(a <= cp <= b for a, b in rng):
                    continue
                if f.covers(c):
                    verdict = ("ok", k, f)
                    break
                dec = unicodedata.normalize("NFD", c)
                if len(dec) > 1 and all(f.covers(x) for x in dec):
                    verdict = ("decomposed", k, f)
                    break
            if verdict is None:
                missing.append(c)
            elif verdict[0] == "decomposed":
                missing.append(c)
                decomposed[f"U+{cp:04X} {c}"] = f"{verdict[2].family} {verdict[2].style} would draw it from its decomposition"
            elif verdict[1] != primary:
                routed = " (routed)" if fonts[verdict[1]][1] else ""
                provider[f"U+{cp:04X} {c}"] = f"{verdict[2].family} {verdict[2].style}{routed}"
        rep["sets"][name] = {
            "total": len(chars),
            "covered": len(chars) - len(missing),
            "missing": [f"U+{ord(c):04X} {c}" for c in missing],
            "fallback_used": provider,
            "decomposed": decomposed,
        }
    rep["required_ok"] = all(rep["sets"][s]["covered"] == rep["sets"][s]["total"] for s in REQUIRED)
    return rep


def to_markdown(fonts: list[dict], stacks: list[dict]) -> str:
    L = ["# Font coverage report", ""]
    L.append("Required sets: printable ASCII (95), Vietnamese letters (146 = 12 vowels x 2 cases x 6 tones + đ Đ), "
             "symbols → ← ✓ ✗ • – — “ ” ‘ ’ … § ≤ ≥ × ° ² (18). Informational: ₫ « » ↔ ⇒ ≠ ± © ® ™ ½ and the "
             "combining marks used by NFD Vietnamese text.")
    L.append("")
    L.append("## Per font file")
    L.append("")
    L.append("| Font | Style | Version | ASCII | VI letters | Symbols | Extra | Combining | GPOS mark | Missing (required) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in fonts:
        s = r["sets"]
        miss = s["ascii"]["missing"] + s["vi_letters"]["missing"] + s["symbols"]["missing"]
        cells = [f"{s[k]['covered']}/{s[k]['total']}" for k in CHARSETS]
        L.append(f"| {r['family']} | {r['style']} | {r['version'].split(';')[0]} | " + " | ".join(cells)
                 + f" | {'yes' if r['gpos_mark'] else 'no'} | {', '.join(miss) if miss else '-'} |")
    if stacks:
        L += ["", "## Font stacks (role -> ordered fallback list)", ""]
        L.append("| Role | Stack | ASCII | VI letters | Symbols | Extra | Missing (required) | Served by fallback |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in stacks:
            s = r["sets"]
            miss = s["ascii"]["missing"] + s["vi_letters"]["missing"] + s["symbols"]["missing"]
            fb, dec = {}, {}
            for k in CHARSETS:
                if k in REQUIRED:
                    fb.update(s[k]["fallback_used"])
                dec.update(s[k]["decomposed"])
            fbtxt = "; ".join(f"{k}→{v}" for k, v in fb.items()) or "-"
            if dec:
                fbtxt += "; DECOMPOSED: " + "; ".join(f"{k}: {v}" for k, v in dec.items())
            L.append(f"| {r['role']} | {' > '.join(r['fonts'])} | {s['ascii']['covered']}/{s['ascii']['total']} | "
                     f"{s['vi_letters']['covered']}/{s['vi_letters']['total']} | {s['symbols']['covered']}/{s['symbols']['total']} | "
                     f"{s['extra_symbols']['covered']}/{s['extra_symbols']['total']} | {', '.join(miss) if miss else '-'} | {fbtxt} |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fonts", nargs="*", type=Path)
    ap.add_argument("--stack", action="append", default=[], help="ROLE=font1.ttf,font2.ttf (ordered fallback)")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--md", type=Path)
    ap.add_argument("--require-full", action="store_true")
    a = ap.parse_args(argv)

    cache: dict[Path, FontInfo] = {}

    def load(p: Path) -> FontInfo:
        p = p.resolve()
        if p not in cache:
            cache[p] = FontInfo(p)
        return cache[p]

    font_reps = [font_report(load(p)) for p in a.fonts]
    stack_reps = []
    for spec in a.stack:
        role, _, files = spec.partition("=")
        entries = []
        for item in (x for x in files.split(",") if x):
            m = re.fullmatch(r"(.+?)\{([0-9A-Fa-f;\- ]+)\}", item)
            path, rng = (m.group(1), [tuple(int(v, 16) for v in r.split("-")) if "-" in r else (int(r, 16), int(r, 16))
                                      for r in m.group(2).replace(" ", "").split(";") if r]) if m else (item, None)
            entries.append((load(Path(path)), rng))
        stack_reps.append(stack_report(role, entries))
    result = {"charsets": {k: "".join(v) for k, v in CHARSETS.items()}, "fonts": font_reps, "stacks": stack_reps}
    result["ok"] = all(r["required_ok"] for r in (stack_reps or font_reps))
    if a.json:
        a.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_markdown(font_reps, stack_reps)
    if a.md:
        a.md.write_text(md, encoding="utf-8")
    print(md)
    print("RESULT:", "PASS" if result["ok"] else "FAIL")
    return 0 if (result["ok"] or not a.require_full) else 1


if __name__ == "__main__":
    sys.exit(main())
