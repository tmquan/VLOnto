#!/usr/bin/env python3
"""trace_global_preview.py - offline projection previews of the global 3D trace scene (scripts/site/trace_global.py).

    python scripts/site/trace_global_preview.py --site site --out previews [--trace lao-dong-tien-luong:3] [--themes light,dark]

Projects the build-time coordinates of data/traces/graph.js with a perspective camera like the page's (fov 45 degrees,
the view directions of js/traces3d.js) and draws them as SVG, rasterised with resvg-py (pip) when it is installed: the
links as thin pastel curves (the page's S-curve: vertical tangents, control points at 45 % of the rise, a soft arch
within a level), the nodes as shaded spheres in the paper's class colours with a depth fade, and, for a selected trace,
everything else faded, the traced path as a navy core over the gold halo on the same curve and the trace's nodes on
top. Views: overview (all areas), area (the region of the selected trace's area) and trace (framed as the page frames
it). It shows the composition of the layout; the call-outs are placed by the page (VL.Callouts) and are not drawn here,
and it is not a rendering of js/traces3d.js (WebGL is checked in the browser tests).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

PALETTE = {"work": "#7dbe8e", "record": "#a3d3ae", "chapter": "#6fb7b4", "section": "#86c4bf", "article": "#9ed2c9",
           "clause": "#bde2d9", "point": "#d9efe9", "term": "#8db8e8", "question": "#f4b183", "answer": "#f8d49b",
           "area": "#b9b9ce", "other_question": "#f4b183"}
THEME = {"light": {"bg": "#ffffff", "core": "#2c3a47", "halo": "#ecc890", "halo2": "#f4dcac", "ink": "#2b3036", "ink2": "#666c73",
                   "box": "#ffffff", "line": "#d3d7dc", "leader": "#a2a8af"},
         "dark": {"bg": "#0f131a", "core": "#f6f1e6", "halo": "#ecc890", "halo2": "#f4dcac", "ink": "#e8ebef", "ink2": "#a3abb5",
                  "box": "#161b23", "line": "#3a4350", "leader": "#5e6875"}}
DIR_ALL, DIR_AREA, DIR_TRACE = (0.0, 0.78, 1.0), (0.25, 0.62, 1.0), (0.28, 0.42, 1.0)    # as js/traces3d.js
SIZE = {"area": 13.0, "work": 15.0, "record": 9.0, "chapter": 10.0, "section": 9.0, "article": 8.5, "clause": 7.5,
        "point": 6.5, "term": 10.0, "question": 12.0, "answer": 10.0, "other_question": 5.0}


def load_js(path: Path):
    m = re.search(r'= JSON\.parse\((".*")\);\n$', path.read_text(encoding="utf-8"), re.S)
    return json.loads(json.loads(m.group(1)))


def rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def mix(a, b, t):
    A, B = rgb(a), rgb(b)
    return "#" + "".join(f"{round(A[i] + (B[i] - A[i]) * t):02x}" for i in range(3))


class Cam:
    """perspective camera looking at target from dir (unit vector towards the camera) at distance d"""
    def __init__(self, target, dirv, d, W, Hpx, fov=45.0):
        self.W, self.H = W, Hpx
        n = math.sqrt(sum(c * c for c in dirv))
        self.f = [c / n for c in dirv]                         # from target to camera
        self.pos = [target[i] + self.f[i] * d for i in range(3)]
        up = [0.0, 1.0, 0.0]
        fw = [-c for c in self.f]                              # forward
        r = [fw[1] * up[2] - fw[2] * up[1], fw[2] * up[0] - fw[0] * up[2], fw[0] * up[1] - fw[1] * up[0]]
        rn = math.sqrt(sum(c * c for c in r))
        self.r = [c / rn for c in r]
        self.u = [self.r[1] * fw[2] - self.r[2] * fw[1], self.r[2] * fw[0] - self.r[0] * fw[2], self.r[0] * fw[1] - self.r[1] * fw[0]]
        self.fw = fw
        self.k = (Hpx / 2) / math.tan(math.radians(fov) / 2)

    def proj(self, p):
        v = [p[i] - self.pos[i] for i in range(3)]
        z = sum(v[i] * self.fw[i] for i in range(3))
        if z < 1:
            return None
        x = sum(v[i] * self.r[i] for i in range(3))
        y = sum(v[i] * self.u[i] for i in range(3))
        return (self.W / 2 + self.k * x / z, self.H / 2 - self.k * y / z, z)


def fit(points, dirv, W, Hpx, fov=45.0, pad=1.08):
    """target (centre of the bounding box) and the smallest distance at which every point projects inside the frame,
    with a margin of (pad - 1) of the frame"""
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    m = (pad - 1) / 2
    def ok(d):
        cam = Cam(c, dirv, d, W, Hpx, fov)
        for p in corners:
            s = cam.proj(p)
            if not s or s[0] < m * W or s[0] > (1 - m) * W or s[1] < m * Hpx or s[1] > (1 - m) * Hpx:
                return False
        return True
    a, b = 1.0, 1.0
    while not ok(b):
        b *= 2
    for _ in range(40):
        mid = (a + b) / 2
        a, b = (a, mid) if ok(mid) else (mid, b)
    return c, b


def curve(a, b, n, H):
    """the page's link curve (js/traces3d.js curvePoint): cubic Bezier, vertical tangents, control points at 45 % of the
    rise, lifted into a soft arch (0.18 x run, at most 0.04 H) when both ends lie within one level gap (0.1 H)"""
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    k, run = 0.45 * dy, math.hypot(dx, dz)
    lift = min(0.18 * run, 0.04 * H) * max(0.0, min(1.0, 1 - abs(dy) / (0.1 * H)))
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        w0, w1, w2, w3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append(((w0 + w1) * a[0] + (w2 + w3) * b[0], w0 * a[1] + w1 * (a[1] + k + lift) + w2 * (b[1] - k + lift) + w3 * b[1],
                    (w0 + w1) * a[2] + (w2 + w3) * b[2]))
    return out


def segs_for(a, b, H):
    """segments per link as the page draws them: 8 when the curve leaves its chord visibly (>= 1.5 units), else 2"""
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    run = math.hypot(dx, dz)
    lift = min(0.18 * run, 0.04 * H) * max(0.0, min(1.0, 1 - abs(dy) / (0.1 * H)))
    return 8 if max(0.34 * min(abs(dy), run), 0.75 * lift) >= 1.5 else 2


def render(G, cam, theme, sel=None, labels=None, title=""):
    T = THEME[theme]
    cls = [G["classes"][c] for c in G["c"]]
    N = len(cls)
    P = [(G["p"][3 * i] / 10, G["p"][3 * i + 1] / 10, G["p"][3 * i + 2] / 10) for i in range(N)]
    S = [cam.proj(p) for p in P]
    zs = [s[2] for s in S if s]
    z0, z1 = min(zs), max(zs)
    alpha = [1.0] * N
    if sel is not None:
        fg, tn = set(sel["f"]), set(sel["n"])
        alpha = [1.0 if i in fg else (0.5 if i in tn else 0.12) for i in range(N)]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{cam.W}" height="{cam.H}" viewBox="0 0 {cam.W} {cam.H}">',
           f'<rect width="{cam.W}" height="{cam.H}" fill="{T["bg"]}"/>']
    LCOL = {"contains": None, "cites": "answer", "mentions": "term", "defines": "term", "answers": "answer",
            "applies_to": "area", "realizes": "record"}
    lines = []
    for k, arr in G["e"].items():
        for j in range(0, len(arr), 2):
            s, t = arr[j], arr[j + 1]
            a, b = S[s], S[t]
            if not a or not b:
                continue
            col = PALETTE[cls[t]] if k == "contains" else PALETTE["other_question" if (k == "cites" and cls[s] == "other_question") else LCOL[k]]
            al = min(alpha[s], alpha[t])
            depth = ((a[2] + b[2]) / 2 - z0) / max(1, z1 - z0)
            op = (0.55 if k != "applies_to" else 0.28) * al * (1 - 0.55 * depth) * (0.3 if G["h"][s] != G["h"][t] else 1.0)
            if theme == "light":
                col = mix(col, "#000000", 0.12)
            pts = [cam.proj(p) for p in curve(P[s], P[t], segs_for(P[s], P[t], G["H"]), G["H"])]
            if not all(pts):
                continue
            lines.append(((a[2] + b[2]) / 2, f'<polyline points="{" ".join(f"{q[0]:.1f},{q[1]:.1f}" for q in pts)}" fill="none" stroke="{col}" '
                                             f'stroke-width="0.7" stroke-opacity="{op:.3f}"/>'))
    for _, ln in sorted(lines, key=lambda x: -x[0]):
        out.append(ln)
    def ribbon():
        """the traced path on the links' curve: structural strokes (0.55 of the widths, 60 % opacity), then the verified"""
        segs = sel["e"]
        for st_pass in (2, 1):
            for width, colk in ((9.2, "halo2"), (6.4, "halo"), (2.8, "core")):
                for j in range(0, len(segs), 3):
                    if segs[j + 2] != st_pass:
                        continue
                    pts = [cam.proj(p) for p in curve(P[segs[j]], P[segs[j + 1]], 16, G["H"])]
                    if not all(pts):
                        continue
                    w = width * (0.55 if st_pass == 2 else 1.0)
                    o = 0.6 if st_pass == 2 else 1.0
                    out.append(f'<polyline points="{" ".join(f"{q[0]:.1f},{q[1]:.1f}" for q in pts)}" fill="none" stroke="{T[colk]}" '
                               f'stroke-width="{w:.2f}" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="{o}"/>')
    # nodes, far to near; with a selection the trace is drawn over the others and the trace's own nodes over the trace
    fgset = set(sel["f"]) if sel is not None else set()
    order = sorted((i for i in range(N) if S[i]), key=lambda i: -S[i][2])
    out.append("<defs>" + "".join(
        f'<radialGradient id="g-{k}" cx="0.38" cy="0.34" r="0.7"><stop offset="0" stop-color="{mix(v, "#ffffff", 0.35)}"/>'
        f'<stop offset="0.7" stop-color="{v}"/><stop offset="1" stop-color="{mix(v, "#000000", 0.16)}"/></radialGradient>'
        for k, v in PALETTE.items()) + "</defs>")
    def disc(i):
        x, y, z = S[i]
        r = max(0.9, SIZE[cls[i]] / 2 * cam.k / z)
        depth = (z - z0) / max(1, z1 - z0)
        op = alpha[i] * (1 - 0.5 * depth)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="url(#g-{cls[i]})" fill-opacity="{op:.3f}"/>')
    for i in order:
        if i not in fgset:
            disc(i)
    if sel is not None:
        ribbon()
        for i in order:
            if i in fgset:
                disc(i)
    if title:
        out.append(f'<text x="12" y="22" font-family="Libertinus Sans" font-size="15" fill="{T["ink2"]}">{esc(title)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--trace", default="lao-dong-tien-luong:3")
    ap.add_argument("--themes", default="light")
    ap.add_argument("--size", default="1600x900")
    a = ap.parse_args(argv)
    G = load_js(a.site / "data" / "traces" / "graph.js")
    IDX = load_js(a.site / "data" / "traces" / "index.js")
    W, Hpx = (int(v) for v in a.size.split("x"))
    a.out.mkdir(parents=True, exist_ok=True)
    area_id, rank = a.trace.split(":")
    ai = [x["id"] for x in G["areas"]].index(area_id)
    sel = next(t for t in G["t"] if t["a"] == ai and t["r"] == int(rank))
    data = load_js(a.site / "data" / "traces" / f"{area_id}.js")
    if not any(t["rank"] == int(rank) for t in data["traces"]):
        raise SystemExit(f"no trace {a.trace}")
    N = len(G["c"])
    P = [(G["p"][3 * i] / 10, G["p"][3 * i + 1] / 10, G["p"][3 * i + 2] / 10) for i in range(N)]
    views = {}
    dirv = DIR_ALL
    c, d = fit(P, dirv, W, Hpx, pad=1.06)
    views["overview"] = (Cam(c, dirv, d, W, Hpx), None, None, "All 27 areas, 540 traces: " + f"{N:,} nodes")
    reg = [P[i] for i in range(N) if G["h"][i] == ai]
    c, d = fit(reg, DIR_AREA, W, Hpx, pad=1.06)
    views["area"] = (Cam(c, DIR_AREA, d, W, Hpx), None, None, f"Area {area_id}")
    homes = {G["h"][k] for j, k in enumerate(sel["co"]) if k >= 0 and (j != 4 or G["h"][k] in (G["h"][sel["co"][0]], G["h"][sel["co"][2]], G["h"][sel["co"][3]]))}
    framed = [P[i] for i in sel["f"] if G["h"][i] in homes] + [P[k] for k in sel["co"] if k >= 0 and G["h"][k] in homes]
    framed.append((framed[0][0], max(p[1] for p in framed) + 30, framed[0][2]))     # headroom above the area node, as the page
    c, d = fit(framed, DIR_TRACE, W, Hpx, pad=1.4)
    views["trace"] = (Cam(c, DIR_TRACE, d, W, Hpx), sel, None, f"Trace {a.trace} (call-outs: placed by the page)")
    try:
        import resvg_py
    except ImportError:
        resvg_py = None
    # resvg reads TrueType, not the site's woff2: the Libertinus Sans faces converted with fontTools (when installed)
    import tempfile
    font_dirs = [str(a.site / "fonts")]
    try:
        from fontTools.ttLib import TTFont
        tmp = Path(tempfile.mkdtemp(prefix="trace-fonts-"))
        for name in ("LibertinusSans-Regular", "LibertinusSans-Italic", "LibertinusSans-Bold"):
            src = a.site / "fonts" / f"{name}.subset.woff2"
            if src.exists():
                f = TTFont(str(src))
                f.flavor = None
                f.save(str(tmp / f"{name}.ttf"))
        font_dirs = [str(tmp)]
    except ImportError:
        pass
    made = []
    for theme in a.themes.split(","):
        for name, (cam, s, labs, title) in views.items():
            svg = render(G, cam, theme, s, labs, title)
            p = a.out / f"global_{name}_{theme}.svg"
            p.write_text(svg, encoding="utf-8")
            if resvg_py:
                png = bytes(resvg_py.svg_to_bytes(svg_string=svg, font_dirs=font_dirs))
                (a.out / f"global_{name}_{theme}.png").write_bytes(png)
            made.append(p.name)
    print(json.dumps({"views": made, "nodes": N, "trace": a.trace}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
