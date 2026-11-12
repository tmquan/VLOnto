#!/usr/bin/env python3
"""trace_layout.py - build-time 2D drawings of the question traces of traces.html (stdlib only, deterministic); the page
shows them when the browser has no WebGL (the 3D scene: scripts/site/trace_global.py, site/js/traces3d.js).

Each trace of build/traces/<area>.json (question -> answer -> cited provision -> ... -> law, terms, other answers citing
the same law) is drawn like the figures of the paper (arXiv:2611.11426).

The cards are Fig. 6 panels (class Panel), a flat drawing that fills the card width: the question and its answer at the
floor; the trace as V/W strokes rising from them - one arm through the chain of the provision the call-out names to its
law, other traced paths to that law as strands beside it, paths to other laws and the question's terms on the opposite
side, each term with a dark hop to the clause that defines it when that clause was found (Fig. 1, Fig. 5). The rest of
the law's structure spreads across the top band and the other answers hang, faded, under the articles they cite. The
two call-outs (the provision and one term) sit at the left and right edges of the panel, level with their nodes, on
each node's outer side; they may cover the faded background ("bg") but never a foreground node, link or traced
segment (with its halo), and their leaders cross neither the trace nor a foreground node. Composition variants
(PANEL_VARIANTS) are tried in order until both call-outs fit.

The focus view keeps Fig. 1: a hanging tree seen obliquely (class Layout3D), the law from the top, its chapters, sections
and articles below it, the question and its answer at the bottom centre under the legal area, projected orthographically
from a raised viewpoint; far nodes fade, low nodes cast soft floor shadows. Its call-outs stand in two columns beside the
graph (wide screens) or in bands above and below it (narrow screens), clear of any node, link, traced segment or shadow.

Text is measured with the advance widths of the vendored Libertinus Sans (font_metrics_libertinus.json, made by
make_font_metrics.py) plus a 3 % margin. Every random choice comes from a PRNG seeded with the area id, the rank and the
question id, so the same input gives the same bytes.

Output per trace (graph units of the 3D drawing; the focus views map them with [a, tx, ty]):
  nodes    [[u, v, r, opacity], ...] in the order of the trace's node list
  order    node indices from far to near (drawing order)
  links    [[source, target, colour class, opacity], ...]; curves are cubic with vertical tangents (see curve())
  trace    [[i, j, style], ...]: style 1 = text-verified path (match >= 0.5) or a term -> defining clause hop,
           2 = structural primary path
  shadows  [[u, v, rx, ry, opacity], ...] on the floor
  views    card / wide / tall: {"w", "h", "t": [a, tx, ty], "c": [call-outs]}; the card carries its own panel drawing
           in card units ("t" = [1, 0, 0]): "n" [[x, y, r, opacity(, 1 = background)], ...], "s" floor shadows,
           "o" drawing order (background first), "lo" link opacities; call-out = {"n": node index,
           "b": [x, y, w, h], "l": [[text, 0 = Vietnamese | 1 = English, x, baseline], ...], "k": leader polyline
           [x1, y1, x2, y2(, x3, y3)]: from the box (via the column's inner edge in the focus views) to the node}
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ------------------------------------------------------------------------------------------------ text measurement
class Font:
    """Advance widths of Libertinus Sans (regular / italic / bold) from font_metrics_libertinus.json."""

    def __init__(self, path: Path = HERE / "font_metrics_libertinus.json"):
        m = json.loads(path.read_text(encoding="utf-8"))
        self.upm, self.ascent, self.descent = m["units_per_em"], m["ascent"], m["descent"]
        self.faces = {}
        for k, f in m["faces"].items():
            w = {}
            for cp0, advs in f["runs"]:
                for i, adv in enumerate(advs):
                    w[cp0 + i] = adv
            self.faces[k] = (w, f["fallback"])

    def width(self, s: str, size: float, face: str = "regular") -> float:
        w, fb = self.faces[face]
        return sum(w.get(ord(c), fb) for c in s) * size / self.upm * 1.03

    def wrap(self, text: str, max_w: float | None, size: float, face: str = "regular") -> list:
        if not max_w or self.width(text, size, face) <= max_w:
            return [text]
        lines, cur = [], ""
        for word in text.split(" "):
            t = f"{cur} {word}" if cur else word
            if cur and self.width(t, size, face) > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = t
        if cur:
            lines.append(cur)
        return lines

    def wrap_balanced(self, text: str, max_w: float | None, size: float, face: str = "regular") -> list:
        """the greedy line count at max_w, with the narrowest width that keeps that count (no lone last syllable)"""
        lines = self.wrap(text, max_w, size, face)
        if len(lines) < 2:
            return lines
        lo = max(self.width(w, size, face) for w in text.split(" "))
        hi = max_w
        for _ in range(14):
            mid = (lo + hi) / 2
            if len(self.wrap(text, mid, size, face)) <= len(lines):
                hi = mid
            else:
                lo = mid
        return self.wrap(text, hi + 0.01, size, face)


# ------------------------------------------------------------------------------------------------ constants
# heights of the hanging tree (fraction of HS), sphere radii (graph px), colour class of the links that end in a class
HS, XS = 168.0, 150.0
HEIGHT = {"area": 1.0, "record": 0.965, "work": 0.9, "chapter": 0.78, "section": 0.68, "article": 0.575, "clause": 0.47,
          "point": 0.39, "term": 0.41, "answer": 0.2, "question": 0.065, "other_question": 0.1}
RADIUS = {"area": 5.0, "record": 4.4, "work": 6.0, "chapter": 4.6, "section": 4.3, "article": 4.0, "clause": 3.6,
          "point": 3.3, "term": 4.5, "answer": 4.6, "question": 5.0, "other_question": 2.8}
CLASSES = ["work", "record", "chapter", "section", "article", "clause", "point", "term", "question", "answer", "area",
           "other_question"]
CONV_H = 0.3                      # the provisions' arms converge above the answer at this height
ELEV = math.radians(20)           # camera elevation
CARD = {"w": 360, "h": 176, "m": 3.0, "font": 13.5, "lh": 15.5, "padx": 5.0, "pady": 3.0, "gap": 4.0}
WIDE = {"w": 1000, "m": 6.0, "font": 15.0, "lh": 18.0, "padx": 6.0, "pady": 3.5, "gap": 7.0, "col": 300.0}
TALL = {"w": 400, "m": 4.0, "font": 12.5, "lh": 15.0, "padx": 4.5, "pady": 2.5, "gap": 5.0, "col": 150.0}
# the traced path as in the paper: navy core 4.6, gold halo 10 and pale outer halo 14 (css/site.css, every view)
HALO = {"card": 7.0, "wide": 7.0, "tall": 7.0}       # half-width of the outer halo (keep-out around traced segments)
LINK_W = {"card": 0.95, "wide": 1.25, "tall": 1.05}


def seed_of(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12], 16)


def r1(x: float) -> float:
    return round(x + 0.0, 1)


def curve(p, q):
    """Cubic Bezier between two points with vertical tangents at both ends (control points at 45 % of the height
    difference); the trace drawing in js/trace-draw.js uses the same formula. Its bounding box is the endpoints' box."""
    (x1, y1), (x2, y2) = (p, q) if p[1] <= q[1] else (q, p)
    k = 0.45 * (y2 - y1)
    return (x1, y1), (x1, y1 + k), (x2, y2 - k), (x2, y2)


# ------------------------------------------------------------------------------------------------ 3D layout
def bez_poly(p, q, n=16):
    """the drawn curve between p and q (curve()) as a polyline of n pieces"""
    p0, p1, p2, p3 = curve(p, q)
    out = []
    for i in range(n + 1):
        u = i / n
        a, b, c, d = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


class Layout3D:
    def __init__(self, tr: dict, seed: int):
        self.tr, self.rnd = tr, random.Random(seed)
        self.nodes = {n["id"]: n for n in tr["nodes"]}
        self.cls = {i: n["cls"] for i, n in self.nodes.items()}
        self.children, self.parent, self.oq = defaultdict(list), {}, defaultdict(list)
        for ln in tr["links"]:
            if ln["kind"] == "contains":
                self.children[ln["s"]].append(ln["t"])
                self.parent[ln["t"]] = ln["s"]
            elif ln["kind"] == "cites" and self.cls[ln["s"]] == "other_question":
                self.oq[ln["t"]].append(ln["s"])
        self.prim = next(p for p in tr["paths"] if p.get("primary"))
        self.q, self.a, self.w0 = self.prim["nodes"][0], self.prim["nodes"][1], self.prim["nodes"][-1]
        self.on_path = set()
        for p in tr["paths"]:
            self.on_path.update(p["nodes"][2:])
        self.pos = {}

    def h(self, i, jitter=0.0):
        return (HEIGHT[self.cls[i]] + (self.rnd.uniform(-jitter, jitter) if jitter else 0.0)) * HS

    def run(self):
        rnd, side = self.rnd, (1 if self.rnd.random() < 0.5 else -1)
        self.side = side
        P = self.pos
        P[self.q] = (0.0, self.h(self.q), 14.0)
        P[self.a] = (0.0, self.h(self.a), 8.0)
        self.conv = (0.0, CONV_H * HS, 8.0)
        areas = [i for i, c in self.cls.items() if c == "area"]
        for i in areas:
            P[i] = (rnd.uniform(-6, 6), self.h(i), -6.0)
        # works: the ranked article's law on one side at the top, other cited works on the other side
        works = [i for i, c in self.cls.items() if c == "work"]
        others = [w for w in works if w != self.w0]
        P[self.w0] = (side * 0.56 * XS, self.h(self.w0), rnd.uniform(-14, 4))
        per_row = 6
        for k, w in enumerate(sorted(others, key=lambda w: (w not in self.children, w))):
            row, col = divmod(k, per_row)
            x = -side * (0.30 * XS + 27.0 * col + 11.0 * row)
            P[w] = (x, (HEIGHT["work"] - 0.03 * row - 0.012 * col) * HS, rnd.uniform(-22, 10) - 9.0 * row)
        for w in works:
            self.place_tree(w)
        for i, c in self.cls.items():           # the vbpl record next to its work
            if c == "record":
                tgt = next((ln["t"] for ln in self.tr["links"] if ln["s"] == i and ln["kind"] == "realizes"), self.w0)
                x, y, z = P.get(tgt, P[self.w0])
                P[i] = (x + (side if tgt == self.w0 else -side) * 17.0, self.h(i), z - 9.0)
        terms = [i for i, c in self.cls.items() if c == "term"]
        defined = {ln["t"]: ln["s"] for ln in self.tr["links"] if ln["kind"] == "defines"}
        for k, t in enumerate(terms):
            off = (k - (len(terms) - 1) / 2.0) * 26.0
            c = defined.get(t)
            if c in P:          # half way to the clause that defines it, in front
                P[t] = (0.5 * P[c][0] + 0.3 * off, self.h(t, 0.02), 0.5 * P[c][2] + 12.0 + rnd.uniform(-4, 4))
            else:
                P[t] = (side * 0.2 * XS + off, self.h(t, 0.02), 20.0 + rnd.uniform(-4, 4))
        for i in self.nodes:                     # anything not reached (defensive): near the centre
            if i not in P:
                P[i] = (rnd.uniform(-40, 40), self.h(i), rnd.uniform(-20, 20))
        return P

    def place_tree(self, root):
        """the arm (path nodes) runs from the work to the convergence point above the answer; other children hang
        around their parent on a circle (cone tree), other answers near the floor under their article"""
        P, rnd = self.pos, self.rnd
        stack = [root]
        while stack:
            x = stack.pop()
            kids = self.children.get(x, [])
            arm = [c for c in kids if c in self.on_path]
            rest = [c for c in kids if c not in self.on_path]
            px, py, pz = P[x]
            cx, cy, cz = self.conv
            ang_c = math.atan2(cz - pz, cx - px)
            for k, c in enumerate(arm):
                yc = self.h(c)
                f = (py - yc) / max(1.0, py - cy)
                f = max(0.0, min(1.0, f))
                bx, bz = px + (cx - px) * f, pz + (cz - pz) * f
                if len(arm) > 1:                 # parallel strands for several cited children of one node
                    o = (k - (len(arm) - 1) / 2.0) * 9.0
                    bx += -math.sin(ang_c) * o
                    bz += math.cos(ang_c) * o
                P[c] = (bx, yc, bz)
                stack.append(c)
            if rest:
                n = len(rest)
                cls = self.cls[rest[0]]
                rho = max({"chapter": 30.0, "section": 20.0, "article": 17.0, "clause": 10.0, "point": 8.0}.get(cls, 14.0),
                          n * 13.0 / (2 * math.pi))
                on_arm = x in self.on_path or x in (self.prim["nodes"][-1],)
                gap = math.radians(60) if (arm or on_arm) else 0.0
                span = 2 * math.pi - 2 * gap
                start = (ang_c + gap) if gap else rnd.uniform(0, 2 * math.pi)
                for k, c in enumerate(sorted(rest)):
                    t = start + span * ((k + 0.5) / n) + rnd.uniform(-0.12, 0.12)
                    P[c] = (px + rho * math.cos(t), self.h(c, 0.012), pz + rho * math.sin(t))
                    stack.append(c)
            oqs = self.oq.get(x, [])
            if oqs:
                n = len(oqs)
                rho = max(9.0, n * 7.5 / (2 * math.pi))
                start = rnd.uniform(0, 2 * math.pi)
                for k, o in enumerate(sorted(oqs)):
                    if o in P:                    # cites several articles: hangs under the first one placed
                        continue
                    t = start + 2 * math.pi * (k / n)
                    P[o] = (px + rho * math.cos(t), self.h(o, 0.025), pz + rho * math.sin(t))


def project(P: dict, az: float):
    ca, sa, ce, se = math.cos(az), math.sin(az), math.cos(ELEV), math.sin(ELEV)
    out = {}
    for i, (x, y, z) in P.items():
        xr = x * ca + z * sa
        zr = -x * sa + z * ca
        out[i] = (xr, -y * ce + zr * se, zr, (xr, zr * se))       # u, v (down), depth (toward the viewer), floor point
    return out


# ------------------------------------------------------------------------------------------------ card: Fig. 6 panel
# The card is composed like a panel of the paper's Fig. 6, directly in card units: the question at the floor with its
# answer just above it; the cited provision's chain rising on one side to its law; on the other side the terms the
# question names, each with a dark hop to the clause that defines it when that clause was found (Fig. 1, Fig. 5), the
# defining document's chain climbing on, faded, to its law; the rest of the law's structure spread across the top band
# and the other answers hanging, faded, under the articles they cite. Faded nodes and links are background ("bg"):
# a call-out box may cover them, as in the paper, but never the trace, its nodes or the other foreground links.
PANEL_H = {"work": 1.0, "record": 0.985, "area": 0.995, "chapter": 0.86, "section": 0.765, "article": 0.665,
           "clause": 0.565, "point": 0.48, "term": 0.40, "answer": 0.075, "question": 0.0, "other_question": 0.12}
PANEL_R = {"work": 5.4, "record": 4.2, "area": 4.6, "chapter": 4.4, "section": 4.2, "article": 4.0, "clause": 3.6,
           "point": 3.3, "term": 4.8, "question": 5.2, "answer": 4.7, "other_question": 2.8}
STRUCT = ("chapter", "section", "article", "clause", "point")
# composition variants, tried in order until both call-outs of a card fit: (flip the provision side, vertex offset,
# reach of the provision arm, reach of the terms), offsets and reaches as fractions of the card width
PANEL_VARIANTS = [(flip, xo, dp, dt) for dp, dt in ((0.17, 0.16), (0.14, 0.13), (0.20, 0.19), (0.12, 0.11), (0.24, 0.23))
                  for flip in (0, 1) for xo in (-0.02, 0.03, -0.07)]


class Panel:
    def __init__(self, tr: dict, seed: int, cfg: dict, side: int, xo: float, dp: float, dt: float, callout_term=None,
                 callout_provision=None):
        self.tr, self.rnd = tr, random.Random(seed)
        self.W, self.H, self.m = cfg["w"], cfg["h"], cfg["m"]
        self.s, self.xo, self.dp, self.dt, self.callout_term = side, xo, dp, dt, callout_term
        self.cls = {n["id"]: n["cls"] for n in tr["nodes"]}
        self.parent, self.children, self.oq, self.defines, self.realizes = {}, defaultdict(list), {}, {}, {}
        for ln in tr["links"]:
            s, t, k = ln["s"], ln["t"], ln["kind"]
            if k == "contains":
                self.parent[t] = s
                self.children[s].append(t)
            elif k == "cites" and self.cls[s] == "other_question":
                self.oq.setdefault(s, []).append(t)
            elif k == "defines":
                self.defines.setdefault(t, s)
            elif k == "realizes":
                self.realizes.setdefault(s, t)
        self.prim = next(p for p in tr["paths"] if p.get("primary"))
        self.q, self.a, self.w0 = self.prim["nodes"][0], self.prim["nodes"][1], self.prim["nodes"][-1]
        self.traced = [p for p in tr["paths"] if p["verified"] or p.get("primary")]
        # the main arm carries the call-out provision (on a traced path in every trace; the primary path otherwise)
        self.main = next((p for p in sorted(self.traced, key=lambda p: (not p["verified"], not p.get("primary")))
                          if callout_provision in p["nodes"]), self.prim)
        self.y0, self.y1 = self.H - 13.0, 13.0                 # floor and top of the node centres
        self.P, self.fg, self.op = {}, set(), {}

    def Y(self, h):
        return self.y0 - h * (self.y0 - self.y1)

    def jit(self, a):
        return self.rnd.uniform(-a, a)

    def clamp(self, x, pad=8.0):
        return min(max(x, self.m + pad), self.W - self.m - pad)

    @staticmethod
    def arm_x(h, x0, x1):
        """x of an arm that leaves the vertex x0 just above the answer and reaches x1 at the top"""
        t = max(0.0, min(1.0, (h - PANEL_H["answer"]) / (1.0 - PANEL_H["answer"])))
        return x0 + (x1 - x0) * t ** 0.9

    def run(self):
        W, s, P, rnd = self.W, self.s, self.P, self.rnd
        xv = W * (0.5 + s * self.xo)
        self.xv = xv
        P[self.q] = (xv, self.Y(0.0))
        P[self.a] = (xv + s * 1.5, self.Y(PANEL_H["answer"]))
        self.fg.update((self.q, self.a))
        # provision arms: the primary path to its law on side s; other traced paths to that law as strands just inside
        # it; traced paths to other laws on the other side
        wm = self.main["nodes"][-1]
        top_of = {wm: self.clamp(xv + s * self.dp * W, 14)}
        k_other = 0
        for p in self.traced:
            w = p["nodes"][-1]
            if w not in top_of:
                top_of[w] = self.clamp(xv - s * self.dp * (1.0 - 0.2 * k_other) * W, 14)
                k_other += 1
        self.k_other = k_other
        n_strands = Counter(p["nodes"][-1] for p in self.traced)
        strands = defaultdict(int)
        for p in sorted(self.traced, key=lambda p: (p is not self.main, not p.get("primary"), not p["verified"])):
            w = p["nodes"][-1]
            k = strands[w]
            strands[w] += 1
            sp = 8.5 if n_strands[w] <= 3 else max(5.0, 25.5 / (n_strands[w] - 1))   # bundles of 4+ strands closer
            off = (-s if w == wm else s) * sp * k                                       # strands step inwards
            for i in p["nodes"][2:]:
                if i in P:
                    continue
                c = self.cls[i]
                h = PANEL_H.get(c, 0.6) + (0.0 if c == "work" else self.jit(0.012))
                x = self.arm_x(h, xv, top_of[w]) + (0.0 if c == "work" else off + self.jit(1.5))
                P[i] = (self.clamp(x, 6), self.Y(h))
            self.fg.update(p["nodes"])
        # terms on the other side, the call-out term outermost; the defining clause just above and inside its term
        terms = [t["node"] for t in self.tr.get("terms") or [] if t["node"] in self.cls]
        if self.callout_term in terms:
            terms = [t for t in terms if t != self.callout_term] + [self.callout_term]
        n = len(terms)
        for k, t in enumerate(terms):
            c = self.defines.get(t)
            frac = self.dt * (0.45 + 0.55 * (k + 1) / n) + (0.6 * self.dp if k_other else 0.0)   # outside other laws' arms
            th = PANEL_H["term"] + (0.035 if k % 2 else 0.0) - (0.07 if c is None else 0.0)
            tx = self.clamp(xv - s * frac * W, 10)
            P[t] = (tx, self.Y(th))
            self.fg.add(t)
            if c is None:
                continue
            self.fg.add(c)
            if c in P:
                continue
            hc = th + 0.17
            P[c] = (self.clamp(tx + s * 0.042 * W, 8), self.Y(hc))
            chain, x = [], self.parent.get(c)
            while x is not None and x not in P:
                chain.append(x)
                x = self.parent.get(x)
            for j, anc in enumerate(chain):
                ha = min(1.0, max(PANEL_H.get(self.cls[anc], 0.8), hc + 0.07 * (j + 1)))
                f = (ha - hc) / max(0.05, 1.0 - hc)
                P[anc] = (self.clamp(P[c][0] - s * 0.11 * W * f + self.jit(2.0), 10), self.Y(ha))
        # area at the top inside the provision arm; the law's record beside it
        for i, c in sorted(self.cls.items()):
            if c == "area" and i not in P:
                P[i] = (self.clamp(xv + s * 0.42 * self.dp * W, 10), self.Y(PANEL_H["area"]))
                self.fg.add(i)
        for r, w in sorted(self.realizes.items()):
            if r not in P and w in P:
                P[r] = (self.clamp(P[w][0] - s * 13.0, 8), self.Y(PANEL_H["record"]))
                if w == self.w0:
                    self.fg.add(r)
        # other works the answer cites: free spots of the top band, the far side first
        taken = [x for x, y in P.values() if y < self.Y(0.93)]
        slots = [self.m + 12 + 17.0 * j for j in range(int((W - 2 * self.m - 24) / 17.0) + 1)]
        slots.sort(key=lambda x: (s * (x - xv) > 0, abs(x - (xv - s * 0.36 * W))))
        for w in sorted(i for i, c in self.cls.items() if c == "work" and i not in P):
            x = next((x for x in slots if all(abs(x - t) > 14 for t in taken)), self.clamp(xv + self.jit(0.3 * W)))
            taken.append(x)
            P[w] = (x, self.Y(0.975 + self.jit(0.02)))
        for r, w in sorted(self.realizes.items()):
            if r not in P:
                P[r] = (self.clamp(P.get(w, (xv, 0))[0] + 11.0, 8), self.Y(PANEL_H["record"] - 0.04))
        # the rest of the structure: subtrees spread across the width, ordered by their parent's x
        oq_first = defaultdict(list)
        for o, tg in self.oq.items():
            oq_first[tg[0]].append(o)

        def weight(i):
            return 1.0 + 0.45 * len(oq_first.get(i, ())) + sum(weight(c) for c in self.children.get(i, ())
                                                                 if c not in P and self.cls.get(c) in STRUCT)
        roots = []
        for par in sorted(P, key=lambda i: (P[i][0], i)):
            for c in self.children.get(par, ()):
                if c not in P and self.cls.get(c) in STRUCT:
                    roots.append((par, c))
        orphans = sorted(i for i, c in self.cls.items() if c in STRUCT and i not in P and self.parent.get(i) not in self.cls)
        roots += [(None, i) for i in orphans]
        if roots:
            wts = [weight(c) for _, c in roots]
            lo, hi = self.m + 8.0, W - self.m - 8.0
            x = lo
            for (par, c), wt in zip(roots, wts):
                span = (hi - lo) * wt / sum(wts)
                self.place_sub(c, x, x + span)
                x += span
        for i, c in sorted(self.cls.items()):                   # anything still unplaced (defensive)
            if c in STRUCT and i not in P:
                P[i] = (self.clamp(xv + self.jit(0.3 * W)), self.Y(PANEL_H[c]))
        # other answers hang under the node they cite first
        groups = defaultdict(list)
        for o, tg in sorted(self.oq.items()):
            groups[next((t for t in tg if t in P), None)].append(o)
        for t0, os_ in sorted(groups.items(), key=lambda kv: str(kv[0])):
            bx = P[t0][0] if t0 is not None else xv
            sp = min(5.4, 46.0 / max(1, len(os_)))
            for j, o in enumerate(os_):
                P[o] = (self.clamp(bx + (j - (len(os_) - 1) / 2.0) * sp + self.jit(1.2), 5),
                        self.Y(0.05 + rnd.uniform(0.0, 0.22)))
        for i, c in sorted(self.cls.items()):
            if i not in P:
                P[i] = (self.clamp(xv + self.jit(0.3 * W)), self.Y(0.6))
        # opacity: foreground strong, the rest faded
        for i in sorted(P):
            c = self.cls[i]
            if i in self.fg:
                self.op[i] = 0.95
            elif c == "other_question":
                self.op[i] = round(0.3 + 0.2 * rnd.random(), 2)
            elif c in ("work", "record"):
                self.op[i] = 0.62
            else:
                self.op[i] = round(0.38 + 0.24 * rnd.random(), 2)
        return P

    def place_sub(self, i, x0, x1):
        """a background subtree in the interval [x0, x1]: the node in the middle, its children side by side below"""
        P = self.P
        c = self.cls[i]
        P[i] = (self.clamp((x0 + x1) / 2 + self.jit(0.12 * (x1 - x0)), 6), self.Y(PANEL_H[c] + self.jit(0.015)))
        kids = [k for k in self.children.get(i, ()) if k not in P and self.cls.get(k) in STRUCT]
        if not kids:
            return
        wts = [1.0 + len(self.children.get(k, ())) for k in kids]
        x = x0
        for k, wt in zip(kids, wts):
            span = (x1 - x0) * wt / sum(wts)
            self.place_sub(k, x, x + span)
            x += span


# ------------------------------------------------------------------------------------------------ geometry
class Rects:
    """ink boxes of a view [x0, y0, x1, y1]; free(box) tests a call-out box against all of them"""

    def __init__(self, rects):
        self.r = rects

    def free(self, x0, y0, x1, y1):
        for a in self.r:
            if x0 < a[2] and x1 > a[0] and y0 < a[3] and y1 > a[1]:
                return False
        return True

    def free_gaps(self, x0, x1, lo, hi):
        """free vertical intervals [y0, y1] of the column x0..x1 between lo and hi"""
        iv = sorted((a[1], a[3]) for a in self.r if x0 < a[2] and x1 > a[0])
        gaps, y = [], lo
        for a, b in iv:
            if b <= y:
                continue
            if a > y:
                gaps.append((y, min(a, hi)))
            y = max(y, b)
            if y >= hi:
                break
        if y < hi:
            gaps.append((y, hi))
        return [(a, b) for a, b in gaps if b > a]


def seg_hits_box(p, q, b, pad=1.0):
    """segment p-q intersects box b = [x, y, w, h] (Liang-Barsky)"""
    x0, y0, x1, y1 = b[0] - pad, b[1] - pad, b[0] + b[2] + pad, b[1] + b[3] + pad
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pp == 0:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def segs_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)


def seg_circle(p, q, c, r):
    """distance from circle centre c to segment p-q is below r"""
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((c[0] - p[0]) * dx + (c[1] - p[1]) * dy) / L))
    ex, ey = p[0] + t * dx - c[0], p[1] + t * dy - c[1]
    return ex * ex + ey * ey < r * r


class TraceGeometry:
    def __init__(self, tr: dict, area_id: str, font: Font):
        self.tr, self.font = tr, font
        self.seed = seed_of(area_id, tr["rank"], tr["qa"]["id"])
        L = Layout3D(tr, self.seed)
        P = L.run()
        self.L = L
        self.ids = [n["id"] for n in tr["nodes"]]
        self.idx = {i: k for k, i in enumerate(self.ids)}
        self.cls = [n["cls"] for n in tr["nodes"]]
        az = L.side * math.radians(16) + L.rnd.uniform(-0.12, 0.12)
        pr = project(P, az)
        zs = [pr[i][2] for i in self.ids]
        z0, z1 = min(zs), max(zs)
        span = max(1e-6, z1 - z0)
        self.depth = [(pr[i][2] - z0) / span for i in self.ids]           # 1 = nearest
        key = {L.q, L.a, L.w0} | {i for i, c in L.cls.items() if c in ("area", "term")}
        trace_nodes = self.trace_node_set()
        self.uv, self.r, self.op = [], [], []
        for k, i in enumerate(self.ids):
            u, v, _, _ = pr[i]
            self.uv.append((u, v))
            self.r.append(RADIUS[self.cls[k]])
            o = 0.4 + 0.6 * self.depth[k] ** 0.85
            if i in key or i in trace_nodes:
                o = max(o, 0.92)
            self.op.append(o)
        # links
        self.links = []
        for ln in tr["links"]:
            s, t = self.idx[ln["s"]], self.idx[ln["t"]]
            kind, cs, ct = ln["kind"], self.cls[s], self.cls[t]
            col = {"contains": ct, "applies_to": "area", "mentions": "term", "defines": "term", "realizes": "record",
                   "answers": "answer"}.get(kind)
            if kind == "cites":
                col = "other_question" if cs == "other_question" else "answer"
            d = (self.depth[s] + self.depth[t]) / 2
            self.links.append([s, t, CLASSES.index(col), round(0.38 + 0.5 * d ** 0.9, 2)])
        # traced segments: dark for text-verified paths, dashed for an unverified primary path
        style = {}
        for p in tr["paths"]:
            st = 1 if p["verified"] else (2 if p.get("primary") else 0)
            if not st:
                continue
            for a, b in zip(p["nodes"], p["nodes"][1:]):
                e = tuple(sorted((self.idx[a], self.idx[b])))
                style[e] = 1 if (style.get(e) == 1 or st == 1) else 2
        q = self.idx[L.q]
        for tm, c in sorted(self.defined_terms().items()):
            for e in ((q, self.idx[tm]), (self.idx[tm], self.idx[c])):
                style[tuple(sorted(e))] = 1
        self.trace = [[a, b, s] for (a, b), s in sorted(style.items())]
        # floor shadows under the low nodes, and one soft shadow under the bottom of the tree
        self.shadows = []
        low = [k for k, i in enumerate(self.ids) if P[i][1] < 0.3 * HS]
        for k in low:
            fx, fy = pr[self.ids[k]][3]
            self.shadows.append([fx, fy, self.r[k] * 2.3, self.r[k] * 0.75, round(0.16 + 0.12 * self.depth[k], 2)])
        if low:
            fx = [pr[self.ids[k]][3][0] for k in low]
            fy = [pr[self.ids[k]][3][1] for k in low]
            cx, cy = (min(fx) + max(fx)) / 2, sum(fy) / len(fy)
            self.shadows.insert(0, [cx, cy, (max(fx) - min(fx)) / 2 + 16, 7.0 + (max(fy) - min(fy)) / 2, 0.1])
        self.order = sorted(range(len(self.ids)), key=lambda k: (self.depth[k], k))
        # graph bounding box (nodes + shadows)
        xs0 = [u - r for (u, v), r in zip(self.uv, self.r)] + [s[0] - s[2] for s in self.shadows]
        xs1 = [u + r for (u, v), r in zip(self.uv, self.r)] + [s[0] + s[2] for s in self.shadows]
        ys0 = [v - r for (u, v), r in zip(self.uv, self.r)] + [s[1] - s[3] for s in self.shadows]
        ys1 = [v + r for (u, v), r in zip(self.uv, self.r)] + [s[1] + s[3] for s in self.shadows]
        self.bbox = (min(xs0), min(ys0), max(xs1), max(ys1))

    def defined_terms(self):
        """term -> the clause that defines it, for the terms of the trace whose defining clause was found"""
        ids = {n["id"] for n in self.tr["nodes"]}
        d = {ln["t"]: ln["s"] for ln in self.tr["links"] if ln["kind"] == "defines"}
        return {t["node"]: d[t["node"]] for t in self.tr.get("terms") or [] if t["node"] in d and d[t["node"]] in ids}

    def trace_node_set(self):
        out = set()
        for p in self.tr["paths"]:
            if p["verified"] or p.get("primary"):
                out.update(p["nodes"])
        for tm, c in self.defined_terms().items():
            out.update((tm, c))
        return out

    # ---------------------------------------------------------------- views
    def ink(self, T, view):
        """keep-out boxes of the graph under transform T = (a, tx, ty)"""
        a, tx, ty = T
        lw, halo, m = LINK_W[view] / 2 + 0.6, HALO[view] + 0.6, 1.5
        X = [(a * u + tx, a * v + ty) for u, v in self.uv]
        R = [a * r for r in self.r]
        out = [[x - r - m, y - r - m, x + r + m, y + r + m] for (x, y), r in zip(X, R)]
        for s, t, _, _ in self.links:
            (x1, y1), (x2, y2) = X[s], X[t]
            out.append([min(x1, x2) - lw, min(y1, y2) - lw, max(x1, x2) + lw, max(y1, y2) + lw])
        for s, t, _ in self.trace:
            (x1, y1), (x2, y2) = X[s], X[t]
            out.append([min(x1, x2) - halo, min(y1, y2) - halo, max(x1, x2) + halo, max(y1, y2) + halo])
        for u, v, rx, ry, _ in self.shadows:
            x, y = a * u + tx, a * v + ty
            out.append([x - a * rx, y - a * ry, x + a * rx, y + a * ry])
        return X, R, out

    def labels(self, k, view):
        """(Vietnamese, English) text of a call-out for node k"""
        n = self.tr["nodes"][k]
        vi, en = n["label_vi"], n["label_en"]
        c = n["cls"]
        if c == "term":
            vi, en = short_term(vi), short_term(en)
        if view != "card":
            pre = {"question": ("Câu hỏi", "Question"), "answer": ("Trả lời", "Answer"), "area": ("Lĩnh vực", "Area")}.get(c)
            if c in ("question", "answer"):
                num = n["id"].split(":", 1)[1]
                vi, en = f"{pre[0]} #{num}", f"{pre[1]} #{num}"
            elif c == "area":
                vi, en = f"{pre[0]}: {vi}", f"{pre[1]}: {en}"
        return vi, en

    def box(self, k, view, cfg, max_w, inline):
        """call-out lines and size; inline = 'VI · EN' on one line when it fits"""
        vi, en = self.labels(k, view)
        f, size = self.font, cfg["font"]
        if inline and max_w and f.width(f"{vi} · {en}", size) <= max_w:
            parts = [[(vi, 0), (" · ", 1), (en, 1)]]
        else:
            parts = [[(s, 0)] for s in f.wrap_balanced(vi, max_w, size)] + [[(s, 1)] for s in f.wrap_balanced(en, max_w, size)]
        widths = [sum(f.width(s, size) for s, _ in line) for line in parts]
        w = max(widths) + 2 * cfg["padx"]
        h = len(parts) * cfg["lh"] + 2 * cfg["pady"]
        return parts, w, h

    def emit_box(self, k, parts, x, y, w, h, cfg, anchor_xy, anchor_r, edge=None):
        f, size = self.font, cfg["font"]
        lines = []
        base0 = y + cfg["pady"] + (cfg["lh"] - (f.ascent + f.descent) / f.upm * size) / 2 + f.ascent / f.upm * size
        for li, line in enumerate(parts):
            cx = x + cfg["padx"]
            for s, kind in line:
                # SVG drops leading and trailing spaces of a text element: place the trimmed text after their width
                lead = s[:len(s) - len(s.lstrip(" "))]
                if s.strip():
                    lines.append([s.strip(), kind, r1(cx + f.width(lead, size) / 1.03), r1(base0 + li * cfg["lh"])])
                cx += f.width(s, size) / 1.03
        ax, ay = anchor_xy
        # leader: from the side of the box facing the node (top or bottom for the bands of the tall view)
        if x + w < ax:
            p = (x + w, min(max(ay, y + 3), y + h - 3))
        elif x > ax:
            p = (x, min(max(ay, y + 3), y + h - 3))
        elif y + h < ay:
            p = (min(max(ax, x + 3), x + w - 3), y + h)
        else:
            p = (min(max(ax, x + 3), x + w - 3), y)
        pts = [p]
        if edge is not None and abs(edge - p[0]) > 0.5:   # stub to the column's inner edge: no leader enters another box
            pts.append((edge, p[1]))
        q = pts[-1]
        dx, dy = ax - q[0], ay - q[1]
        dist = math.hypot(dx, dy) or 1.0
        pts.append((ax - dx / dist * (anchor_r + 0.8), ay - dy / dist * (anchor_r + 0.8)))
        return {"n": k, "b": [r1(x), r1(y), r1(w), r1(h)], "l": lines, "k": [r1(v) for pt in pts for v in pt]}

    def card(self):
        """Fig. 6 panel (class Panel), composition variants in order until both call-outs fit beside their nodes"""
        cfg = CARD
        W, H = cfg["w"], cfg["h"]
        ca = self.tr["callouts"]
        want = [self.idx[x] for x in (ca.get("provision"), ca.get("term")) if x]
        variants = {k: [self.box(k, "card", cfg, mw, False) for mw in (None, 124, 104, 88, 74)] for k in want}
        tries = 0
        for need in (want, want[:1], []):
            for strict in (True, False):                # first: no leader over the trace or a foreground node
                for vi, (flip, xo, dp, dt) in enumerate(PANEL_VARIANTS):
                    side = -self.L.side if flip else self.L.side
                    pan = Panel(self.tr, self.seed, cfg, side, xo, dp, dt, ca.get("term"), ca.get("provision"))
                    geo = self.panel_geo(pan, pan.run())
                    tries += 1
                    # each box on the outer side of its node: the side of the node seen from the vertex
                    pref = {k: (1 if geo["X"][k][0] > pan.xv + 0.5 else (-1 if geo["X"][k][0] < pan.xv - 0.5 else sd))
                            for k, sd in ((self.idx[x], sd) for x, sd in ((ca.get("provision"), side), (ca.get("term"), -side)) if x)}
                    rects = Rects(geo["ink"])
                    res = self.place_pair(need, variants, geo, rects, cfg, pref, strict)
                    if res is None:
                        continue
                    hits = sum(1 for c in res if not rects.free(c["b"][0], c["b"][1], c["b"][0] + c["b"][2], c["b"][1] + c["b"][3]))
                    over = sum(self.leader_over(c, geo)[0] + self.leader_over(c, geo)[1] for c in res)
                    return {"w": W, "h": H, "t": [1, 0, 0], "c": res, "n": geo["n"], "s": geo["s"], "o": geo["o"],
                            "lo": geo["lo"], "variant": vi, "tries": tries, "dropped": len(want) - len(need), "ink": hits,
                            "over": over, "arms": self.arms(geo["X"], pan.xv)}
        raise RuntimeError("no card layout")

    def panel_geo(self, pan, P):
        """card nodes [x, y, r, opacity(, 1 = background)], link opacities, floor shadows, drawing order and the
        foreground ink that a call-out may not cover (nodes, links between foreground nodes, traced segments + halo)"""
        X = [P[i] for i in self.ids]
        R = [PANEL_R[c] for c in self.cls]
        fg = [i in pan.fg for i in self.ids]
        op = [pan.op[i] for i in self.ids]
        traced = {(a, b) for a, b, _ in self.trace}
        lo = []
        for s, t, _, _ in self.links:
            e = tuple(sorted((s, t)))
            lo.append(0.9 if e in traced else (0.85 if fg[s] and fg[t] else round(min(op[s], op[t]) * 0.85, 2)))
        lw, halo, m = LINK_W["card"] / 2 + 0.6, HALO["card"] + 0.6, 1.5
        ink = [[x - r - m, y - r - m, x + r + m, y + r + m] for (x, y), r, f in zip(X, R, fg) if f]
        for s, t, _, _ in self.links:
            if fg[s] and fg[t] and tuple(sorted((s, t))) not in traced:
                (x1, y1), (x2, y2) = X[s], X[t]
                ink.append([min(x1, x2) - lw, min(y1, y2) - lw, max(x1, x2) + lw, max(y1, y2) + lw])
        for s, t, _ in self.trace:
            (x1, y1), (x2, y2) = X[s], X[t]
            ink.append([min(x1, x2) - halo, min(y1, y2) - halo, max(x1, x2) + halo, max(y1, y2) + halo])
        bgbox = [[x - r, y - r, x + r, y + r] for (x, y), r, f in zip(X, R, fg) if not f]
        sh = []
        low = [k for k in range(len(X)) if X[k][1] > pan.Y(0.32)]
        if low:
            xs = [X[k][0] for k in low]
            sh.append([r1((min(xs) + max(xs)) / 2), r1(pan.y0 + 5.0), r1((max(xs) - min(xs)) / 2 + 12.0), 3.4, 0.09])
        for k in low:
            sh.append([r1(X[k][0]), r1(pan.y0 + 4.4), r1(R[k] * 1.9), r1(R[k] * 0.55), round(0.08 + (0.08 if fg[k] else 0.0), 2)])
        order = sorted(range(len(X)), key=lambda k: (fg[k], op[k], k))
        nodes = [[r1(x), r1(y), r, op[k]] + ([] if fg[k] else [1]) for k, ((x, y), r) in enumerate(zip(X, R))]
        tp = [(s, t, bez_poly(X[s], X[t])) for s, t, _ in self.trace]
        return {"X": X, "R": R, "fg": fg, "ink": ink, "bgbox": bgbox, "lo": lo, "s": sh, "o": order, "n": nodes, "tp": tp}

    def arms(self, X, xv):
        """traced strokes leaving the vertex (question or answer): [style, side] each (side -1 = left of the vertex)"""
        q, a = self.idx[self.L.q], self.idx[self.L.a]
        out = []
        for s, t, st in self.trace:
            if {s, t} == {q, a} or not ({s, t} & {q, a}):
                continue
            o = t if s in (q, a) else s
            out.append([st, -1 if X[o][0] < xv else 1])
        return out

    @staticmethod
    def leader_over(c, geo):
        """(pieces of traced curves, foreground nodes) that the leader of call-out c crosses, away from its own node"""
        X, R, fg, k = geo["X"], geo["R"], geo["fg"], c["n"]
        (ax, ay), near = X[k], R[k] + 3.0
        pts = list(zip(c["k"][0::2], c["k"][1::2]))
        tx = fx = 0
        for p, q in zip(pts, pts[1:]):
            for _, _, poly in geo["tp"]:
                for u, v in zip(poly, poly[1:]):
                    if segs_cross(p, q, u, v) and math.hypot(u[0] - ax, u[1] - ay) > near and math.hypot(v[0] - ax, v[1] - ay) > near:
                        tx += 1
            fx += sum(1 for j, (xy, r) in enumerate(zip(X, R)) if j != k and fg[j] and seg_circle(p, q, xy, r + 0.3))
        return tx, fx

    def candidates(self, k, variants, geo, rects, cfg, pref=None, strict=False):
        """call-out boxes for node k, best first: as in the paper, at the left or right edge of the panel on the node's
        outer side, level with the node; the leader may run over the faded background but not over other foreground
        nodes or the trace"""
        W, H, m, gap = cfg["w"], cfg["h"], cfg["m"], cfg["gap"]
        X, R, bgbox = geo["X"], geo["R"], geo["bgbox"]
        (ax, ay), ar = X[k], R[k]
        out = []
        for parts, w, h in variants[k]:
            xs = {m, W - m - w}
            for g in (8, 14, 22, 32, 46, 64, 86):
                xs.add(ax - ar - g - w)
                xs.add(ax + ar + g)
            for x in sorted(xs):
                if x < m - 0.01 or x + w > W - m + 0.01:
                    continue
                if not (x + w < ax - ar - 3 or x > ax + ar + 3):
                    continue
                for g0, g1 in rects.free_gaps(x - gap / 2, x + w + gap / 2, m, H - m):
                    if g1 - g0 < h + 0.2:
                        continue
                    y = min(max(ay - h / 2, g0 + 0.1), g1 - h - 0.1)          # 0.1 inside: rounding never reaches ink
                    c = self.emit_box(k, parts, x, y, w, h, cfg, (ax, ay), ar)
                    p, e = c["k"][:2], c["k"][-2:]
                    L = math.hypot(e[0] - p[0], e[1] - p[1])
                    tx, fgx = self.leader_over(c, geo)
                    if strict and (tx or fgx):
                        continue
                    bgx = sum(1 for j, (xy, r) in enumerate(zip(X, R)) if j != k and not geo["fg"][j] and seg_circle(p, e, xy, r + 0.5))
                    score = 0.25 * L + 0.6 * abs((y + h / 2) - ay) + 12.0 * fgx + 1.5 * bgx + 30.0 * tx + 0.02 * w * h
                    if not (x <= m + 0.5 or x + w >= W - m - 0.5):
                        score += 26.0                 # not at the panel's edge
                    if pref and k in pref and (x + w / 2 - ax) * pref[k] < 0:
                        score += 40.0                 # card: the box on the inner side of its node
                    score += 1.5 * sum(1 for b in bgbox if x < b[2] and x + w > b[0] and y < b[3] and y + h > b[1])
                    out.append((score, c))
        out.sort(key=lambda t: t[0])
        return out[:40]

    def place_pair(self, need, variants, geo, rects, cfg, pref=None, strict=False):
        if not need:
            return []
        cands = [self.candidates(k, variants, geo, rects, cfg, pref, strict) for k in need]
        if any(not c for c in cands):
            return None
        if len(need) == 1:
            return [cands[0][0][1]]
        best = None
        for s1, c1 in cands[0]:
            for s2, c2 in cands[1]:
                if best is not None and s1 + s2 >= best[0]:
                    break
                if not self.compatible(c1, c2, cfg["gap"]):
                    continue
                best = (s1 + s2, [c1, c2])
        return best[1] if best else None

    @staticmethod
    def compatible(c1, c2, gap):
        b1, b2 = c1["b"], c2["b"]
        if b1[0] < b2[0] + b2[2] + gap and b2[0] < b1[0] + b1[2] + gap and b1[1] < b2[1] + b2[3] + gap and b2[1] < b1[1] + b1[3] + gap:
            return False
        l1, l2 = c1["k"], c2["k"]
        if seg_hits_box(l1[:2], l1[-2:], b2) or seg_hits_box(l2[:2], l2[-2:], b1):
            return False
        return not segs_cross(l1[:2], l1[-2:], l2[:2], l2[-2:])

    def focus_targets(self):
        """call-outs of the focus view: law, chapter, section, article of the primary path, the provisions with a
        traced path (primary first, at most 4), the terms (at most 3), question, answer and area"""
        L, tr = self.L, self.tr
        out, seen = [], set()

        def add(i):
            if i and i in self.idx and i not in seen:
                seen.add(i)
                out.append(self.idx[i])
        add(L.w0)
        chain = L.prim["nodes"][2:-1]
        for i in reversed(chain):
            if self.cls[self.idx[i]] in ("chapter", "section", "article"):
                add(i)
        provs = [L.prim["nodes"][2]] if len(L.prim["nodes"]) > 3 else []
        for p in tr["paths"]:
            if p["verified"] and len(p["nodes"]) > 3 and not p.get("primary"):
                provs.append(p["nodes"][2])
        for i in provs[:4]:
            add(i)
        for t in tr["terms"][:3]:
            add(t["node"])
        add(L.q)
        add(L.a)
        add(next((i for i, c in L.cls.items() if c == "area"), None))
        return out

    def wide(self):
        """Fig. 1: call-outs in a column on each side of the graph (left / right by the node's side), stacked in the order
        of their nodes' heights; the graph fills the width between the columns and the height follows from it"""
        cfg = WIDE
        W, m, gap = cfg["w"], cfg["m"], cfg["gap"]
        targets = self.focus_targets()
        boxes = {k: self.box(k, "wide", cfg, cfg["col"] - 2 * cfg["padx"], True) for k in targets}
        bx0, by0, bx1, by1 = self.bbox
        ucen = (bx0 + bx1) / 2
        left = [k for k in targets if self.uv[k][0] < ucen]
        right = [k for k in targets if self.uv[k][0] >= ucen]
        while len(left) > len(right) + 2:
            k = max(left, key=lambda k: self.uv[k][0])
            left.remove(k)
            right.append(k)
        while len(right) > len(left) + 2:
            k = min(right, key=lambda k: self.uv[k][0])
            right.remove(k)
            left.append(k)
        colL = max([boxes[k][1] for k in left], default=0.0)
        colR = max([boxes[k][1] for k in right], default=0.0)
        x0 = m + (colL + 34 if left else 8)
        x1 = W - m - (colR + 34 if right else 8)
        a = (x1 - x0) / (bx1 - bx0)
        if a * (by1 - by0) > 600:
            a = 600 / (by1 - by0)
        gh = a * (by1 - by0)
        stack_h = lambda ks: sum(boxes[k][2] for k in ks) + gap * max(0, len(ks) - 1)
        H = int(math.ceil(max(gh + 2 * (m + 10), stack_h(left) + 2 * m, stack_h(right) + 2 * m, 340)))
        T = (a, (x0 + x1) / 2 - a * (bx0 + bx1) / 2, H / 2 - a * (by0 + by1) / 2)
        X, R, ink = self.ink(T, "wide")
        res = self.stack(left, boxes, X, R, cfg, H, True) + self.stack(right, boxes, X, R, cfg, H, False)
        rects = Rects(ink)
        for c in res:
            b = c["b"]
            if not rects.free(b[0], b[1], b[0] + b[2], b[1] + b[3]):
                c["ink"] = True
        return {"w": W, "h": H, "t": [round(T[0], 4), r1(T[1]), r1(T[2])], "c": res}

    def stack(self, ks, boxes, X, R, cfg, H, is_left):
        m, g, W = cfg["m"], cfg["gap"], cfg["w"]
        ks = sorted(ks, key=lambda k: X[k][1])
        ys, hs = [], []
        for k in ks:
            _, w, h = boxes[k]
            ys.append(X[k][1] - h / 2)
            hs.append(h)
        for i in range(len(ys)):                  # push down, then back up from the bottom edge
            ys[i] = max(ys[i], m if i == 0 else ys[i - 1] + hs[i - 1] + g)
        for i in range(len(ys) - 1, -1, -1):
            ys[i] = min(ys[i], (H - m - hs[i]) if i == len(ys) - 1 else ys[i + 1] - g - hs[i])
        out = []
        colw = max([boxes[k][1] for k in ks], default=0.0)
        edge = (m + colw + 4) if is_left else (W - m - colw - 4)
        for k, y in zip(ks, ys):
            parts, w, h = boxes[k]
            x = m if is_left else W - m - w
            out.append(self.emit_box(k, parts, x, max(m, y), w, h, cfg, X[k], R[k], edge))
        return out

    def tall(self):
        """narrow screens: the graph on the left, the call-outs in one column on the right, stacked in the order of their
        nodes' heights; every leader leaves its box towards the graph, so no leader crosses another box"""
        cfg = TALL
        W, m, gap, col = cfg["w"], cfg["m"], cfg["gap"], cfg["col"]
        targets = self.focus_targets()
        boxes = {k: self.box(k, "tall", cfg, col - 2 * cfg["padx"], True) for k in targets}
        cw = max([boxes[k][1] for k in targets], default=0.0)
        bx0, by0, bx1, by1 = self.bbox
        x0, x1 = m + 2, W - m - cw - 22
        a = (x1 - x0) / (bx1 - bx0)
        gh = a * (by1 - by0)
        stack = sum(boxes[k][2] for k in targets) + gap * max(0, len(targets) - 1)
        H = int(math.ceil(max(gh + 2 * (m + 6), stack + 2 * m)))
        T = (a, (x0 + x1) / 2 - a * (bx0 + bx1) / 2, H / 2 - a * (by0 + by1) / 2)
        X, R, ink = self.ink(T, "tall")
        res = self.stack(targets, boxes, X, R, cfg, H, False)
        rects = Rects(ink)
        for c in res:
            b = c["b"]
            if not rects.free(b[0], b[1], b[0] + b[2], b[1] + b[3]):
                c["ink"] = True
        return {"w": W, "h": H, "t": [round(T[0], 4), r1(T[1]), r1(T[2])], "c": res}

    @staticmethod
    def crossings(view):
        """leaders that cross another call-out box, and call-out boxes that overlap each other"""
        cs, bad = view["c"], 0
        for i, c in enumerate(cs):
            for j, d in enumerate(cs):
                if i == j:
                    continue
                pts = list(zip(c["k"][0::2], c["k"][1::2]))
                if any(seg_hits_box(p, q, d["b"], pad=0.0) for p, q in zip(pts, pts[1:])):
                    bad += 1
                b1, b2 = c["b"], d["b"]
                if i < j and b1[0] < b2[0] + b2[2] and b2[0] < b1[0] + b1[2] and b1[1] < b2[1] + b2[3] and b2[1] < b1[1] + b1[3]:
                    bad += 1
        return bad

    def export(self):
        card = self.card()
        meta = {k: card.pop(k) for k in ("variant", "tries", "dropped", "ink", "over", "arms")}
        views = {"card": card, "wide": self.wide(), "tall": self.tall()}
        meta["crossings"] = sum(self.crossings(v) for v in views.values())
        return {"nodes": [[r1(u), r1(v), r1(r), round(o, 2)] for (u, v), r, o in zip(self.uv, self.r, self.op)],
                "order": self.order, "links": self.links, "trace": self.trace,
                "shadows": [[r1(a), r1(b), r1(c), r1(d), e] for a, b, c, d, e in self.shadows],
                "views": views}, meta


def short_term(s: str) -> str:
    """long tnpl term names carry a context in brackets ('Khách hàng (trong hoạt động ...)'): keep the head"""
    s = s.strip()
    if len(s) > 34 and " (" in s:
        return s.split(" (", 1)[0].strip()
    return s
