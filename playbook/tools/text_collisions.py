#!/usr/bin/env python3
"""Find glyphs that collide on the same baseline in a PDF (text running into other text).

    $V/envs/web/bin/python playbook/tools/text_collisions.py PDF [--out report.json]

tools/pdf_check.py compares lines that are stacked vertically; a word that is wider than its
table cell runs into the next cell on the same baseline, which that check does not see. PyMuPDF
may report the two cells as two text lines or merge them into one, so every glyph is compared
with every other glyph whose box it intersects, on the whole page.

Two glyph boxes collide when they overlap by more than TOL horizontally and by more than half of
the smaller height vertically. Kerning legitimately overlaps the advance boxes of two glyphs that
follow each other in the same text run (same font and size), so such a pair only collides when
the overlap exceeds KERN times the font size; any other pair (other run, other line, other cell)
collides at TOL. Boxes that are identical (one ligature glyph for several characters) are one
glyph. Exit status 1 when any collision is found.
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
import fitz  # noqa: E402  PyMuPDF

TOL = 0.6    # pt
KERN = 0.2   # em; kerning pairs of the vendored fonts stay well below this


def glyphs_of(page):
    """All non-space glyphs of a page: (rect, run_id, seq, size, char, line_id)."""
    raw = page.get_text("rawdict")
    out, run_id, line_id = [], 0, 0
    for b in raw["blocks"]:
        for ln in b.get("lines", []):
            line_id += 1
            for s in ln["spans"]:
                run_id += 1
                for k, c in enumerate(s["chars"]):
                    if c["c"].strip():
                        out.append((fitz.Rect(c["bbox"]), run_id, k, s["size"], c["c"], line_id))
    return out


def text_near(glyphs, line_id, x, width=60):
    row = sorted((g for g in glyphs if g[5] == line_id), key=lambda g: g[0].x0)
    return "".join(g[4] for g in row if abs(g[0].x0 - x) < width)


def main():
    pdf = sys.argv[1]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    doc = fitz.open(pdf)
    found = []
    for pno, page in enumerate(doc, 1):
        gl = glyphs_of(page)
        order = sorted(range(len(gl)), key=lambda i: gl[i][0].x0)
        for p, i in enumerate(order):
            a, run_a, seq_a, size_a, ch_a, line_a = gl[i]
            for j in order[p + 1:]:
                b, run_b, seq_b, size_b, ch_b, line_b = gl[j]
                if b.x0 >= a.x1 - TOL:
                    break
                if tuple(a) == tuple(b):
                    continue
                dy = min(a.y1, b.y1) - max(a.y0, b.y0)
                if dy <= 0.5 * min(a.height, b.height):
                    continue
                dx = min(a.x1, b.x1) - max(a.x0, b.x0)
                neighbours = run_a == run_b and abs(seq_a - seq_b) == 1
                limit = max(TOL, KERN * min(size_a, size_b)) if neighbours else TOL
                if dx > limit:
                    found.append({
                        "page": pno, "overlap_pt": round(dx, 2), "chars": ch_a + ch_b,
                        "same_line": line_a == line_b,
                        "text_a": text_near(gl, line_a, a.x0), "text_b": text_near(gl, line_b, b.x0),
                        "at": [round(a.x0, 1), round(a.y0, 1)]})
    for f in found[:60]:
        print(f"p{f['page']} at {f['at']}: '{f['chars']}' overlap {f['overlap_pt']} pt "
              f"in '{f['text_a']}' / '{f['text_b']}'")
    res = {"pdf": pdf, "pages": doc.page_count, "tolerance_pt": TOL, "kerning_em": KERN,
           "collisions": found, "result": "PASS" if not found else "FAIL"}
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"text_collisions: {res['result']} ({len(found)} colliding glyph pairs, "
          f"{doc.page_count} pages)")
    return 0 if not found else 1


if __name__ == "__main__":
    sys.exit(main())
