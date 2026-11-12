#!/usr/bin/env python3
"""trace_preview.py - offline PNG previews of the question-trace drawings of traces.html, without a browser.

    python scripts/site/trace_preview.py --site site --out build/trace_preview \
        [--cards lao-dong-tien-luong:1,3 thue-phi-le-phi:1] [--focus lao-dong-tien-luong:3] [--themes light,dark]

Runs the page's own drawing code (site/js/trace-draw.js) in V8 (pip package mini-racer) on the page's data
(site/data/traces/<area>.js), resolves the CSS custom properties of css/site.css for each theme (the drawing's classes
and the paper-style tokens; only the rules of the "question traces" section are applied) and rasterises the SVG with
resvg (pip package resvg-py) using the vendored Libertinus Sans faces (woff2 converted to TrueType with fontTools).
Writes card_<area>_<rank>_<theme>.png, focus_<area>_<rank>_<view>_<theme>.png, a contact sheet of the cards per theme
and a JSON report with each call-out box checked against the ink bounding boxes of its drawing.

The card's HTML parts (header, question title, English gloss, provenance line) are drawn as SVG text in the page's
fonts, sizes and colours with line breaks from the font metrics; the browser lays them out itself, so the contact sheet
shows them approximately. The drawing itself is the markup the page inserts. Development tool: not used by the build.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))


# ------------------------------------------------------------------------------------------------ CSS resolution
def css_rules(text: str):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"@import[^;]*;", "", text)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        yield m.group(1).strip(), m.group(2)


def root_like(sel: str) -> bool:
    rest = re.sub(r":not\([^)]*\)", "", sel)
    rest = re.sub(r":root|\[[^\]]*\]", "", rest)
    return not rest.strip()


def theme_ok(sel: str, theme: str) -> bool:
    neg = ':not([data-theme="dark"])' in sel
    dark = '[data-theme="dark"]' in sel.replace(':not([data-theme="dark"])', "")
    if dark:
        return theme == "dark"
    if neg:
        return theme == "light"
    return True


def tokens(css_texts, theme: str) -> dict:
    tok = {}
    for text in css_texts:
        for sel, body in css_rules(text):
            if sel.startswith("@"):
                continue
            parts = [p.strip() for p in sel.split(",")]
            if not any(root_like(p) and theme_ok(p, theme) for p in parts):
                continue
            for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);?", body):
                tok[m.group(1)] = m.group(2).strip()
    return tok


def resolve(value: str, tok: dict, depth=0) -> str:
    if depth > 12:
        return value

    def sub(m):
        name, fb = m.group(1), m.group(2)
        v = tok.get(name)
        if v is None:
            return fb.strip() if fb else ""
        return resolve(v, tok, depth + 1)
    out = re.sub(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)", sub, value)
    out = re.sub(r"calc\(\s*([\d.]+)\s*\*\s*([\d.]+)\s*\)", lambda m: f"{float(m.group(1)) * float(m.group(2)):.3f}", out)
    return out


def trace_css(theme: str) -> tuple[str, dict]:
    site = (REPO / "site" / "css" / "site.css").read_text(encoding="utf-8")
    fonts = [(REPO / "site" / "css" / f).read_text(encoding="utf-8") for f in ("fonts-web.css", "fonts-paper.css")]
    tok = tokens(fonts + [site], theme)
    sec = site.split("question traces (traces.html)", 1)[1].split("/* --- the page", 1)[0]
    out = []
    for sel, body in css_rules(sec):
        if root_like(sel.split(",")[0].strip()) or sel.startswith(":root"):
            continue
        decl = []
        for m in re.finditer(r"([\w-]+)\s*:\s*([^;]+);?", body):
            decl.append(f"{m.group(1)}: {resolve(m.group(2).strip(), tok)}")
        out.append(f"{sel} {{ {'; '.join(decl)} }}")
    return "\n".join(out), tok


# ------------------------------------------------------------------------------------------------ data and V8
def load_js_data(path: Path):
    s = path.read_text(encoding="utf-8")
    m = re.search(r'= JSON\.parse\((".*")\);\s*$', s, re.S)
    return json.loads(json.loads(m.group(1)))


class Drawer:
    def __init__(self):
        from py_mini_racer import MiniRacer
        self.ctx = MiniRacer()
        self.ctx.eval("var window = this;")
        self.ctx.eval((REPO / "site" / "js" / "trace-draw.js").read_text(encoding="utf-8"))

    def svg(self, tr, view, opts):
        self.ctx.eval("var __tr = " + json.dumps(tr, ensure_ascii=False) + "; var __o = " + json.dumps(opts, ensure_ascii=False) + ";")
        return self.ctx.eval(f"VL.TraceDraw.svg(__tr, {json.dumps(view)}, __o)")

    def defs(self):
        return self.ctx.eval("VL.TraceDraw.defs()")


def font_files(tmp: Path):
    from fontTools.ttLib import TTFont
    out = []
    for name in ("LibertinusSans-Regular", "LibertinusSans-Italic", "LibertinusSans-Bold"):
        f = TTFont(str(REPO / "site" / "fonts" / f"{name}.subset.woff2"))
        f.flavor = None
        p = tmp / f"{name}.ttf"
        f.save(str(p))
        out.append(str(p))
    for name in ("BeVietnamPro-Regular", "BeVietnamPro-Italic", "NotoSansSymbols2-Regular.subset"):
        src = REPO / "site" / "fonts" / f"{name}.woff2"
        if src.exists():
            f = TTFont(str(src))
            f.flavor = None
            p = tmp / f"{name}.ttf"
            f.save(str(p))
            out.append(str(p))
    return out


def standalone(svg: str, css: str, defs: str, bg: str) -> str:
    head = svg[:svg.index(">") + 1]
    w, h = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head).groups()
    head2 = head.replace("<svg ", f'<svg width="{w}" height="{h}" ', 1)
    return (head2 + f"<style>{css}</style>" + defs + f'<rect width="{w}" height="{h}" fill="{bg}"/>' +
            svg[len(head):])


# ------------------------------------------------------------------------------------------------ checks
def ink_boxes(svg: str):
    """node circle boxes, link / traced-segment path boxes (endpoints of the vertical-tangent curves) and call-out boxes;
    background nodes and links (class "bg": faded, a call-out may cover them) are not ink, as in the browser test"""
    nodes = [(float(cx) - float(r), float(cy) - float(r), float(cx) + float(r), float(cy) + float(r))
             for cl, cx, cy, r in re.findall(r'<circle class="(tn[^"]*)" cx="([-\d.]+)" cy="([-\d.]+)" r="([-\d.]+)"', svg)
             if " bg" not in cl]
    paths = []
    half = {"tl": 0.6, "th2": 7.0, "th": 5.0, "tc": 2.3}           # half the stroke widths of css/site.css
    for cl, d in re.findall(r'<path class="((?:tl|th2|th|tc)[^"]*)" d="([^"]+)"', svg):
        if " bg" in cl:
            continue
        nums = [float(x) for x in re.findall(r"-?[\d.]+", d)]
        xs, ys, w = nums[0::2], nums[1::2], half[cl.split()[0]]
        paths.append((min(xs) - w, min(ys) - w, max(xs) + w, max(ys) + w))
    boxes = [tuple(float(v) for v in m) for m in re.findall(r'<rect class="tr-box" x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', svg)]
    boxes = [(x, y, x + w, y + h) for x, y, w, h in boxes]
    return nodes, paths, boxes


def overlaps(a, b, tol=0.25):
    return a[0] < b[2] - tol and a[2] > b[0] + tol and a[1] < b[3] - tol and a[3] > b[1] + tol


def check_svg(svg: str) -> dict:
    nodes, paths, boxes = ink_boxes(svg)
    hits = [(i, "node") for i, b in enumerate(boxes) for n in nodes if overlaps(b, n)]
    hits += [(i, "link") for i, b in enumerate(boxes) for p in paths if overlaps(b, p)]
    vb = [float(x) for x in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups()]
    outside = [i for i, b in enumerate(boxes) if b[0] < 0 or b[1] < 0 or b[2] > vb[0] or b[3] > vb[1]]
    return {"callouts": len(boxes), "nodes": len(nodes), "paths": len(paths), "box_ink_hits": len(hits), "outside": len(outside)}


# ------------------------------------------------------------------------------------------------ main
def card_mock(tr, fig_svg, font, theme_tok, x0, y0, width):
    """SVG stand-in for the card's HTML (header, title, gloss, provenance) around the real drawing"""
    import trace_layout as TL
    ink, ink2 = theme_tok.get("--paper-ink", "#2b3036"), theme_tok.get("--paper-ink-2", "#666c73")
    pad = 14
    inner = width - 2 * pad
    parts, y = [], y0 + pad
    # as lawTitle() in site/js/traces3d.js: the number only when the English name does not carry it
    head = tr['law']['en'] if tr['law']['number'] in tr['law']['en'] else f"{tr['law']['en']} · {tr['law']['number']}"
    y += 16
    parts.append(f'<text x="{x0 + pad}" y="{y}" font-family="Libertinus Sans" font-weight="700" font-size="15" fill="{ink}">{tr["rank"]}</text>')
    parts.append(f'<text x="{x0 + pad + 24}" y="{y}" font-family="Libertinus Sans" font-size="16" fill="{ink}">{esc(head)}</text>')
    y += 6
    for ln in font.wrap(tr["qa"]["vi"], inner - 24, 15, "italic"):
        y += 19
        parts.append(f'<text x="{x0 + pad + 24}" y="{y}" font-family="Libertinus Sans" font-style="italic" font-size="15" fill="{ink}">{esc(ln)}</text>')
    for ln in font.wrap(tr["qa"]["en"], inner - 24, 14.5):
        y += 18.5
        parts.append(f'<text x="{x0 + pad + 24}" y="{y}" font-family="Libertinus Sans" font-size="14.5" fill="{ink2}">{esc(ln)}</text>')
    y += 8
    vb = [float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', fig_svg).groups()]
    fw = inner
    fh = fw * vb[1] / vb[0]
    fig = fig_svg.replace("<svg ", f'<svg x="{x0 + pad}" y="{y}" width="{fw}" height="{fh}" ', 1)
    parts.append(fig)
    y += fh + 6
    ok = "✓ text match" if tr["verified"] else "structural · match"
    prov = f"hdpl #{tr['qa']['id']} · {tr['qa']['date']} · {tr['article']['n']} answers cite {tr['article']['en']} · {ok} {tr['match']:.2f}"
    for ln in font.wrap(prov, inner, 12):
        y += 15
        parts.append(f'<text x="{x0 + pad}" y="{y}" font-family="Libertinus Sans" font-size="12" fill="{ink2}">{esc(ln)}</text>')
    return parts, y + pad - y0


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=REPO / "site")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cards", nargs="*", default=["lao-dong-tien-luong:1,3", "thue-phi-le-phi:1,2", "dau-tu:12,1"])
    ap.add_argument("--focus", nargs="*", default=["lao-dong-tien-luong:3"])
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--scale", type=float, default=2.0)
    a = ap.parse_args(argv)
    import resvg_py
    import trace_layout as TL
    font = TL.Font()
    a.out.mkdir(parents=True, exist_ok=True)
    dr = Drawer()
    defs = dr.defs()
    report = {"cards": [], "focus": []}
    data = {}

    def get(area):
        if area not in data:
            data[area] = load_js_data(a.site / "data" / "traces" / f"{area}.js")
        return data[area]
    with tempfile.TemporaryDirectory() as td:
        fonts = font_files(Path(td))
        render = lambda svg, bg, zoom: resvg_py.svg_to_bytes(svg_string=svg, font_files=fonts, skip_system_fonts=True,
                                                             zoom=zoom, background=bg)
        for theme in a.themes.split(","):
            css, tok = trace_css(theme)
            bg = tok.get("--scene-bg", "#ffffff")
            page_bg = "#f4f6fb" if theme == "light" else "#0c1120"
            sheet, x, y, colw, rowh = [], 16, 16, 430, 0
            k = 0
            for spec in a.cards:
                area, ranks = spec.split(":")
                for rank in [int(r) for r in ranks.split(",")]:
                    tr = next(t for t in get(area)["traces"] if t["rank"] == rank)
                    svg = dr.svg(tr, "card", {"id": f"c{rank}", "title": "", "desc": ""})
                    chk = check_svg(svg)
                    report["cards"].append({"area": area, "rank": rank, "theme": theme, **chk})
                    png = render(standalone(svg, css, defs, bg), bg, a.scale)
                    (a.out / f"card_{area}_{rank}_{theme}.png").write_bytes(png)
                    parts, h = card_mock(tr, svg, font, tok, x, y, colw)
                    sheet.append(f'<rect x="{x}" y="{y}" width="{colw}" height="{h}" fill="{bg}" stroke="{tok.get("--paper-callout-line", "#d3d7dc")}"/>')
                    sheet += parts
                    rowh = max(rowh, h)
                    k += 1
                    if k % 3 == 0:
                        x, y, rowh = 16, y + rowh + 16, 0
                    else:
                        x += colw + 16
            total_h = y + (rowh + 16 if k % 3 else 0)
            W = 16 + 3 * (colw + 16)
            doc = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h}" viewBox="0 0 {W} {total_h}">'
                   f"<style>{css}</style>{defs}" + f'<rect width="{W}" height="{total_h}" fill="{page_bg}"/>' + "".join(sheet) + "</svg>")
            (a.out / f"contact_sheet_{theme}.png").write_bytes(render(doc, page_bg, 1.5))
            for spec in a.focus:
                area, ranks = spec.split(":")
                for rank in [int(r) for r in ranks.split(",")]:
                    tr = next(t for t in get(area)["traces"] if t["rank"] == rank)
                    for view in ("wide", "tall"):
                        svg = dr.svg(tr, view, {"id": f"f{rank}", "title": "", "desc": "", "nodeTitles": True})
                        chk = check_svg(svg)
                        report["focus"].append({"area": area, "rank": rank, "view": view, "theme": theme, **chk})
                        png = render(standalone(svg, css, defs, bg), bg, 1.5 if view == "wide" else 2.0)
                        (a.out / f"focus_{area}_{rank}_{view}_{theme}.png").write_bytes(png)
    (a.out / "preview_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in report["cards"] + report["focus"] if r["box_ink_hits"] or r["outside"]]
    print(json.dumps({"cards": len(report["cards"]), "focus": len(report["focus"]), "problems": bad[:5]}, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
