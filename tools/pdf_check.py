#!/usr/bin/env python3
"""pdf_check.py - render-level checks for a PDF built from known source fonts (Typst / pandoc output).

Checks (each one is reported; any failure gives exit code 1)
  open            the PDF opens and has pages
  fonts_embedded  every font used on every page has an embedded font program (Type3 fonts are listed)
  fonts_known     every font maps to one of the source fonts (--fonts DIR) by PostScript name; catches silent
                  fallbacks to fonts you did not ship (e.g. Typst's embedded Libertinus / New CM / DejaVu)
  glyphs          no .notdef glyph (glyph id 0 = tofu box) and no U+FFFD in the text layer; every character
                  is in the cmap of the source font that drew it; no drawn glyph without an outline in the
                  embedded font program (invisible text)
  bounds          no glyph outside the page; no glyph beyond the left/right content margins (punctuation may
                  hang by up to its own width, like Typst's default `overhang`); baselines inside the
                  top/bottom margins except running header/footer zones (--no-running-zones turns those into
                  failures), which must still keep --edge from the paper edge
  text_overlap    glyph cores (baseline-0.72em .. baseline+0.12em) of different text lines must not intersect
  images          raster images inside the page and inside the left/right margins
  blank_pages     pages without any text, image or vector drawing (unless --allow-blank)
  reproducible    with --rebuild-cmd CMD --rebuild-output PATH: CMD runs twice, outputs must be byte-identical
Every page is rendered to PNG with pypdfium2 (--dpi, default 110) plus a contact sheet, for visual inspection.

Usage
  pdf_check.py doc.pdf --fonts typst/fonts --margins 22mm,20mm,24mm,20mm --out build/pdf_check
               [--rebuild-cmd "bash rebuild.sh" --rebuild-output build/rebuild.pdf] [--dpi 110] [--edge 5mm]
  --margins top,right,bottom,left (or one value for all sides, or vertical,horizontal); units mm, cm, in, pt, px.
Outputs: <out>/pdf_check_report.json, <out>/pdf_check_report.md, <out>/pages/page-NNN.png, <out>/contact_sheet.png
Exit 0 = pass, 1 = failures, 2 = usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

UNITS = {"pt": 1.0, "mm": 72 / 25.4, "cm": 72 / 2.54, "in": 72.0, "px": 0.75}
SUBSET_TAG = re.compile(r"^[A-Z]{6}\+")
TOL = 0.75  # pt


def length(s: str) -> float:
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(pt|mm|cm|in|px)?\s*", s)
    if not m:
        raise argparse.ArgumentTypeError(f"bad length {s!r}")
    return float(m.group(1)) * UNITS[m.group(2) or "pt"]


def margins(s: str):
    v = [length(x) for x in s.split(",")]
    if len(v) == 1:
        v *= 4
    elif len(v) == 2:
        v = [v[0], v[1], v[0], v[1]]
    if len(v) != 4:
        raise argparse.ArgumentTypeError("margins: 1, 2 or 4 comma-separated values (top,right,bottom,left)")
    return v


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def blank_char(cp: int) -> bool:
    if cp <= 0x20 or cp in (0xA0, 0xAD):
        return True
    cat = unicodedata.category(chr(cp))
    return cat in ("Zs", "Zl", "Zp", "Cc", "Cf")


class SourceFonts:
    def __init__(self, dirs):
        from fontTools.ttLib import TTCollection, TTFont
        self.by_ps: dict[str, dict] = {}
        self.fonts: list[dict] = []
        for d in dirs:
            for p in sorted(Path(d).rglob("*")):
                ext = p.suffix.lower()
                if ext not in (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"):
                    continue
                fonts = TTCollection(str(p)).fonts if ext in (".ttc", ".otc") else [TTFont(str(p), lazy=True)]
                for f in fonts:
                    nm = f["name"]
                    info = {"file": p.name, "postscript": nm.getDebugName(6) or "",
                            "family": nm.getDebugName(16) or nm.getDebugName(1) or "",
                            "style": nm.getDebugName(17) or nm.getDebugName(2) or "",
                            "cmap": set((f.getBestCmap() or {}).keys())}
                    self.fonts.append(info)
                    self.by_ps.setdefault(norm(info["postscript"]), info)

    def match(self, pdf_name: str):
        n = norm(SUBSET_TAG.sub("", pdf_name or ""))
        if n in self.by_ps:
            return self.by_ps[n]
        for f in self.fonts:
            if n in (norm(f["family"] + f["style"]), norm(f["family"] + "-" + f["style"])):
                return f
        return None


def outline_checker(doc, xref):
    """Return gid -> bool|None (has outline) for an embedded font program, or None if unreadable."""
    try:
        _name, _ext, _type, buf = doc.extract_font(xref)
    except Exception:
        return None
    if not buf:
        return None
    from fontTools.ttLib import TTFont
    try:
        f = TTFont(io.BytesIO(buf), lazy=True)
        order = f.getGlyphOrder()
        if "glyf" in f:
            glyf = f["glyf"]

            def has(gid):
                if gid >= len(order):
                    return None
                return glyf[order[gid]].numberOfContours != 0
            return has
        if "CFF " in f:
            cs = f["CFF "].cff.topDictIndex[0].CharStrings

            def has(gid):
                if gid >= len(order):
                    return None
                return cs[order[gid]].calcBounds(cs) is not None
            return has
    except Exception:
        pass
    try:
        from fontTools.cffLib import CFFFontSet
        cff = CFFFontSet()
        cff.decompile(io.BytesIO(buf), None)
        top = cff.topDictIndex[0]
        cs, order = top.CharStrings, top.charset

        def has(gid):
            if gid >= len(order):
                return None
            return cs[order[gid]].calcBounds(cs) is not None
        return has
    except Exception:
        return None


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Check:
    def __init__(self, name):
        self.name, self.count, self.examples, self.info = name, 0, [], {}

    def add(self, ex, limit=40):
        self.count += 1
        if len(self.examples) < limit:
            self.examples.append(ex)

    def as_dict(self):
        return {"ok": self.count == 0, "count": self.count, "examples": self.examples, **self.info}


def render_pages(pdf_path: Path, out: Path, dpi: int):
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    files, thumbs = [], []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=dpi / 72).to_pil().convert("RGB")
        fp = pages_dir / f"page-{i + 1:03d}.png"
        img.save(fp)
        files.append(str(fp.relative_to(out)))
        t = img.copy()
        t.thumbnail((360, 520))
        thumbs.append(t)
    pdf.close()
    if thumbs:
        cols = min(4, len(thumbs))
        rows = (len(thumbs) + cols - 1) // cols
        cw, ch = 380, max(t.height for t in thumbs) + 34
        sheet = Image.new("RGB", (cols * cw, rows * ch), "#d9dce3")
        d = ImageDraw.Draw(sheet)
        for k, t in enumerate(thumbs):
            x, y = (k % cols) * cw + 10, (k // cols) * ch + 8
            sheet.paste(t, (x, y))
            d.rectangle([x - 1, y - 1, x + t.width, y + t.height], outline="#7a8194")
            d.text((x, y + t.height + 6), f"page {k + 1}", fill="#20242c")
        sheet.save(out / "contact_sheet.png")
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--fonts", type=Path, action="append", required=True, help="source font dir (repeatable)")
    ap.add_argument("--margins", type=margins, required=True)
    ap.add_argument("--out", type=Path, default=Path("pdf_check_out"))
    ap.add_argument("--edge", type=length, default=length("5mm"))
    ap.add_argument("--no-running-zones", action="store_true")
    ap.add_argument("--allow-font", action="append", default=[], help="extra allowed PDF font name (regex)")
    ap.add_argument("--allow-blank", action="store_true")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--rebuild-cmd")
    ap.add_argument("--rebuild-output", type=Path)
    a = ap.parse_args(argv)
    if a.rebuild_cmd and not a.rebuild_output:
        ap.error("--rebuild-cmd needs --rebuild-output")
    if not a.pdf.is_file():
        print(f"no such PDF: {a.pdf}", file=sys.stderr)
        return 2
    import pymupdf

    a.out.mkdir(parents=True, exist_ok=True)
    src = SourceFonts(a.fonts)
    top, right, bottom, left = a.margins
    checks = {n: Check(n) for n in ("open", "fonts_embedded", "fonts_known", "glyphs", "bounds", "text_overlap", "images", "blank_pages")}
    rep = {"tool": "pdf_check.py", "pdf": str(a.pdf), "sha256": sha256_file(a.pdf),
           "margins_pt": {"top": round(top, 2), "right": round(right, 2), "bottom": round(bottom, 2), "left": round(left, 2)},
           "source_fonts": sorted({f["postscript"] for f in src.fonts})}
    try:
        doc = pymupdf.open(str(a.pdf))
    except Exception as e:
        checks["open"].add(f"cannot open: {e}")
        doc = None
    font_use: dict[str, dict] = {}
    warnings: dict[str, list] = {"unmapped_glyphs": [], "combining_marks_not_nfc": []}
    pages = []
    if doc is not None:
        rep["pages"] = doc.page_count
        rep["metadata"] = {k: v for k, v in (doc.metadata or {}).items() if v}
        if doc.page_count == 0:
            checks["open"].add("PDF has no pages")
        checkers: dict[int, object] = {}
        name_to_xref: dict[str, int] = {}
        for pno in range(doc.page_count):
            page = doc[pno]
            W, H = page.rect.width, page.rect.height
            pinfo = {"page": pno + 1, "size_pt": [round(W, 2), round(H, 2)], "chars": 0, "fonts": set()}
            for (xref, ext, ftype, basefont, _n, enc, *_r) in page.get_fonts(full=True):
                base = SUBSET_TAG.sub("", basefont or "")
                name_to_xref.setdefault(base, xref)
                fu = font_use.setdefault(base, {"pdf_name": basefont, "type": ftype, "ext": ext, "encoding": enc,
                                                "glyphs": 0, "pages": set()})
                fu["pages"].add(pno + 1)
                if ftype == "Type3":
                    fu["note"] = "Type3 (glyphs are drawings)"
                elif ext in ("n/a", "", None):
                    checks["fonts_embedded"].add(f"p{pno + 1}: font {basefont} ({ftype}) is not embedded")
            # ---- per glyph: tofu, unmapped, cmap, outline, bounds
            cx0, cx1, cy0, cy1 = left, W - right, top, H - bottom
            for span in page.get_texttrace():
                fname = span.get("font", "")
                base = SUBSET_TAG.sub("", fname)
                size = float(span.get("size") or 0)
                fu = font_use.setdefault(base, {"pdf_name": fname, "type": span.get("type"), "glyphs": 0, "pages": set()})
                fu["pages"].add(pno + 1)
                sf = src.match(base)
                xref = name_to_xref.get(base)
                if xref is not None and xref not in checkers:
                    checkers[xref] = outline_checker(doc, xref)
                has_outline = checkers.get(xref) if xref is not None else None
                for ch in span.get("chars", []):
                    ucs, gid, origin, bbox = ch[0], ch[1], ch[2], ch[3]
                    fu["glyphs"] += 1
                    pinfo["chars"] += 1
                    pinfo["fonts"].add(base)
                    c = chr(ucs) if 0 <= ucs < 0x110000 else "?"
                    where = f"p{pno + 1} ({origin[0]:.0f},{origin[1]:.0f}pt) {base}"
                    if gid == 0 and not blank_char(ucs):
                        what = "unknown character" if ucs == 0xFFFD else f"U+{ucs:04X} {c!r}"
                        checks["glyphs"].add(f"{where}: .notdef glyph (tofu box) drawn for {what}")
                        continue
                    if ucs == 0xFFFD:
                        # glyph without its own Unicode mapping: 2nd+ glyph of a multi-glyph cluster (marks,
                        # decompositions). Rendering is fine; only copy/paste of that glyph loses text.
                        warnings["unmapped_glyphs"].append(f"{where}: glyph {gid}")
                        continue
                    if 0x300 <= ucs <= 0x36F:
                        warnings["combining_marks_not_nfc"].append(f"{where}: U+{ucs:04X} (normalise the source text to NFC)")
                    if sf is not None and not blank_char(ucs) and ucs not in sf["cmap"]:
                        dec = unicodedata.normalize("NFD", c)
                        if len(dec) > 1 and all(ord(x) in sf["cmap"] for x in dec):
                            parts = " + ".join(f"U+{ord(x):04X}" for x in dec)
                            checks["glyphs"].add(f"{where}: U+{ucs:04X} {c!r} is not in {sf['file']}; the shaper drew it by canonical "
                                                 f"decomposition ({parts}), overlay marks are often misplaced - give this character to "
                                                 f"a font that has it (Typst: font entry with `covers`)")
                        else:
                            checks["glyphs"].add(f"{where}: U+{ucs:04X} {c!r} is not in the cmap of {sf['file']}")
                    if has_outline is not None and gid > 0 and not blank_char(ucs) and unicodedata.category(c) != "Mn":
                        ho = has_outline(gid)
                        if ho is False:
                            checks["glyphs"].add(f"{where}: U+{ucs:04X} {c!r} drawn with an empty glyph (invisible)")
                    if blank_char(ucs):
                        continue
                    x0, y0, x1, y1 = bbox
                    oy = origin[1]
                    if x0 < -TOL or y0 < -TOL or x1 > W + TOL or y1 > H + TOL:
                        checks["bounds"].add(f"{where}: {c!r} outside the page (bbox {x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f})")
                        continue
                    hang = (x1 - x0) if unicodedata.category(c).startswith("P") else 0.0
                    if x0 < cx0 - TOL - hang or x1 > cx1 + TOL + hang:
                        side = "left" if x0 < cx0 - TOL - hang else "right"
                        over = (cx0 - x0) if side == "left" else (x1 - cx1)
                        checks["bounds"].add(f"{where}: {c!r} beyond the {side} margin by {over:.1f} pt")
                        continue
                    if oy < cy0 - TOL or oy > cy1 + TOL:
                        if a.no_running_zones:
                            checks["bounds"].add(f"{where}: {c!r} baseline in the {'top' if oy < cy0 else 'bottom'} margin")
                        elif y0 < a.edge - TOL or y1 > H - a.edge + TOL:
                            checks["bounds"].add(f"{where}: {c!r} closer than {a.edge:.1f} pt to the paper edge")
            # ---- overlap of glyph cores between different lines
            cores = []
            for bi, b in enumerate(page.get_text("rawdict").get("blocks", [])):
                for li, line in enumerate(b.get("lines", [])):
                    for sp in line.get("spans", []):
                        sz = float(sp.get("size") or 0)
                        for chd in sp.get("chars", []):
                            cc = chd.get("c", " ")
                            if not cc.strip() or blank_char(ord(cc[0])):
                                continue
                            ox, oy = chd["origin"]
                            x0, _, x1, _ = chd["bbox"]
                            if x1 - x0 < 0.3:
                                continue
                            cores.append(((bi, li), x0, oy - 0.72 * sz, x1, oy + 0.12 * sz, cc, sp.get("text", "")))
            grid, seen = {}, set()
            G = 36.0
            for k, (lid, x0, y0, x1, y1, cc, _t) in enumerate(cores):
                for gx in range(int(x0 // G), int(x1 // G) + 1):
                    for gy in range(int(y0 // G), int(y1 // G) + 1):
                        cell = grid.setdefault((gx, gy), [])
                        for j in cell:
                            o = cores[j]
                            if o[0] == lid:
                                continue
                            pair = (min(o[0], lid), max(o[0], lid))
                            if pair in seen:
                                continue
                            iw, ih = min(o[3], x1) - max(o[1], x0), min(o[4], y1) - max(o[2], y0)
                            if iw <= 0 or ih <= 0:
                                continue
                            amin = min((o[3] - o[1]) * (o[4] - o[2]), (x1 - x0) * (y1 - y0))
                            if iw * ih > 0.3 * amin:
                                seen.add(pair)
                                checks["text_overlap"].add(f"p{pno + 1} ({x0:.0f},{y0:.0f}pt): {o[5]!r} of line '{o[6][:30]}' overlaps {cc!r} of line '{_t[:30]}'")
                        cell.append(k)
            # ---- images, drawings, blank pages
            imgs = page.get_image_info()
            for im in imgs:
                x0, y0, x1, y1 = im["bbox"]
                if x0 < -TOL or y0 < -TOL or x1 > W + TOL or y1 > H + TOL:
                    checks["images"].add(f"p{pno + 1}: image outside the page {tuple(round(v, 1) for v in im['bbox'])}")
                elif x0 < cx0 - TOL or x1 > cx1 + TOL:
                    checks["images"].add(f"p{pno + 1}: image beyond the left/right margins {tuple(round(v, 1) for v in im['bbox'])}")
            drawings = page.get_drawings()
            if pinfo["chars"] == 0 and not imgs and not drawings and not a.allow_blank:
                checks["blank_pages"].add(f"p{pno + 1}: blank page")
            pinfo["images"], pinfo["drawings"] = len(imgs), len(drawings)
            pinfo["fonts"] = sorted(pinfo["fonts"])
            pages.append(pinfo)
        for base, fu in font_use.items():
            sf = src.match(base)
            fu["source_file"] = sf["file"] if sf else None
            fu["pages"] = sorted(fu["pages"])
            if sf is None and fu.get("type") != "Type3" and not any(re.search(p, base) for p in a.allow_font):
                checks["fonts_known"].add(f"font {fu['pdf_name']} is not one of the source fonts ({', '.join(str(d) for d in a.fonts)})")
        doc.close()
    rep["fonts"] = font_use
    rep["per_page"] = pages
    # ---- reproducibility
    if a.rebuild_cmd:
        hashes = []
        for k in range(2):
            r = subprocess.run(a.rebuild_cmd, shell=True, capture_output=True, text=True)
            ok = r.returncode == 0 and a.rebuild_output.is_file()
            hashes.append(sha256_file(a.rebuild_output) if ok else f"FAILED rc={r.returncode}: {r.stderr[-300:]}")
        chk = Check("reproducible")
        if hashes[0] != hashes[1] or hashes[0].startswith("FAILED"):
            chk.add(f"rebuilds differ or failed: {hashes}")
        chk.info = {"cmd": a.rebuild_cmd, "build1_sha256": hashes[0], "build2_sha256": hashes[1],
                    "checked_pdf_sha256": rep["sha256"], "checked_pdf_identical_to_rebuild": hashes[0] == rep["sha256"]}
        checks["reproducible"] = chk
    if not a.no_render and doc is not None:
        rep["renders"] = render_pages(a.pdf, a.out, a.dpi)
        rep["contact_sheet"] = "contact_sheet.png"
    rep["checks"] = {k: v.as_dict() for k, v in checks.items()}
    rep["warnings"] = {k: {"count": len(v), "examples": v[:20]} for k, v in warnings.items()}
    rep["ok"] = all(v.count == 0 for v in checks.values())
    (a.out / "pdf_check_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=sorted), encoding="utf-8")
    md = [f"# pdf_check: {a.pdf.name}", "", f"- result: **{'PASS' if rep['ok'] else 'FAIL'}**  ",
          f"- pages: {rep.get('pages')}; sha256 `{rep['sha256'][:16]}…`  ",
          f"- margins (pt): {rep['margins_pt']}", "", "| check | result | count |", "|---|---|---|"]
    for k, v in rep["checks"].items():
        md.append(f"| {k} | {'PASS' if v['ok'] else 'FAIL'} | {v['count']} |")
    md += ["", "| font in PDF | type | glyphs | source file |", "|---|---|---|---|"]
    for base, fu in sorted(font_use.items()):
        md.append(f"| {fu['pdf_name']} | {fu.get('type')} | {fu['glyphs']} | {fu.get('source_file') or '**not a source font**'} |")
    for k, v in rep["checks"].items():
        if v["examples"]:
            md += ["", f"## {k}", ""] + [f"- {e}" for e in v["examples"][:25]]
    for k, v in rep["warnings"].items():
        if v["count"]:
            md += ["", f"## warning: {k} ({v['count']}, not a failure)", ""] + [f"- {e}" for e in v["examples"][:10]]
    (a.out / "pdf_check_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:8 + len(rep['checks'])]))
    for k, v in rep["checks"].items():
        for e in v["examples"][:6]:
            print(f"  [{k}] {e}")
    print(f"RESULT: {'PASS' if rep['ok'] else 'FAIL'}  report: {a.out / 'pdf_check_report.json'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
