#!/usr/bin/env python3
"""trace_global.py - the global 3D embedding of traces.html: all question traces in ONE scene (stdlib only, deterministic).

Every node of the traces appears once: a law, article or term that several traces or areas share is one node, and the
links show the sharing. The legal areas are regions of the floor in the order of the tabs (COLS per row, the first row
at the back), each drawn like the paper's Fig. 1 (arXiv:2611.11426):
  * the laws at the top, each with its chapters, sections, articles, clauses and points hanging below it in a widening
    cone (children share their parent's angle range by leaf count; the radius grows and the height falls by class);
  * the questions and their answers at the floor, under the provision their answer cites (pulled a little towards the
    middle of the region, so the chain leans in like the paper's), or, when that provision lies in another region,
    on the side of the region that faces it;
  * the terms the questions name between them, at about 40 % of the height, on the far side of the question from its
    provision (the second arm of the paper's V), joined to the clauses that define them;
  * the other answers that cite the same provisions hanging low under the provision they cite first (faded on the page);
  * the area above its region, its questions fanned out below it (applies_to links).
The page (js/traces3d.js) draws the nodes as points and the links as line segments in one WebGL context, and lights a
selected trace inside the whole graph with the traced segments listed per trace below.

Output: build_graph() returns the payload of site/data/traces/graph.js (window.VLONTO["traces_graph"]):
  v, classes, H (height of the laws, scene units), cols, ext [x0, x1, z0, z1, y1], kinds (link kinds)
  areas   [{"id", "c": [x, z], "r": radius}] in tab order
  i       node ids; c class index (classes); h home area index (areas) (point sizes follow the class on the page)
  p       positions [x, y, z, x, y, z, ...] in tenths of a unit (integers)
  vi, en  labels; empty for questions, answers and other answers (named by id on the page; the titles of the traced
          questions stay in the area files) and en empty when it equals vi
  u       {node index: source url}
  e       {kind: [s0, t0, s1, t1, ...]} the unique links of every kind
  t       per trace, in area and rank order: {"a": area index, "r": rank, "n": [nodes of the trace], "f": [foreground
          nodes: the traced path, the question, its answer and area, the call-out nodes], "e": [i, j, style, ...] traced
          segments (style 1 = text-verified path or term -> defining clause, 2 = structural primary path),
          "co": [question, answer, provision, law, term or -1, area]}
No question titles, answer text, provision text or definitions: labels are the law, provision and term names already
published in the area files.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace_layout as TL  # noqa: E402  (class order shared with the area files)

CLASSES = TL.CLASSES
KINDS = ["contains", "cites", "mentions", "defines", "answers", "applies_to", "realizes"]
STRUCT = ("chapter", "section", "article", "clause", "point")
H = 160.0                                    # height of the laws above the floor
LEVEL = {"area": 1.24, "work": 1.0, "record": 0.985, "chapter": 0.86, "section": 0.765, "article": 0.665, "clause": 0.565,
         "point": 0.48, "term": 0.42, "answer": 0.075, "question": 0.0, "other_question": 0.11}
RING = {"chapter": 0.30, "section": 0.48, "article": 0.68, "clause": 0.86, "point": 0.98}     # cone radius share by class
SIZE = {"area": 13.0, "work": 15.0, "record": 9.0, "chapter": 10.0, "section": 9.0, "article": 8.5, "clause": 7.5,
        "point": 6.5, "term": 10.0, "question": 12.0, "answer": 10.0, "other_question": 5.0}
COLS = 7                                     # regions per row
LEAF_GAP = 10.0                              # arc length per leaf on the outer ring of a cone
CONE_MIN = 18.0
GAP = 14.0                                   # between the cones of a region
REGION_GAP = 70.0                            # between regions
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def seed_of(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12], 16)


def nat_key(s: str):
    """natural order of structure ids ('...::dieu-9' before '...::dieu-10')"""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", s) if t]


def unit(dx, dz, fx=1.0, fz=0.0):
    d = math.hypot(dx, dz)
    return (dx / d, dz / d) if d > 1e-6 else (fx, fz)


class Graph:
    def __init__(self, areas: list, src: dict):
        self.areas, self.tab = areas, {a: i for i, a in enumerate(areas)}
        self.node, self.order, self.cnt = {}, [], defaultdict(Counter)
        self.edges, self.traces = {}, []
        for a in areas:
            for tr in src[a]["traces"]:
                self.traces.append((a, tr))
                for n in tr["nodes"]:
                    if n["id"] not in self.node:
                        self.node[n["id"]] = {"cls": n["cls"], "vi": n.get("label_vi") or "", "en": n.get("label_en") or "",
                                              "url": n.get("url") or ""}
                        self.order.append(n["id"])
                    self.cnt[n["id"]][a] += 1
                for ln in tr["links"]:
                    k = (ln["s"], ln["t"], ln["kind"])
                    if k not in self.edges:
                        self.edges[k] = len(self.edges)
        self.cls = {i: d["cls"] for i, d in self.node.items()}
        self.parent, self.children = {}, defaultdict(list)
        self.realizes, self.cites = {}, defaultdict(list)
        self.mentions = defaultdict(list)             # term -> questions
        for (s, t, k) in self.edges:
            if k == "contains" and t not in self.parent:
                self.parent[t] = s
                self.children[s].append(t)
            elif k == "realizes":
                self.realizes.setdefault(s, t)         # record -> work
            elif k == "cites":
                self.cites[s].append(t)
            elif k == "mentions":
                self.mentions[t].append(s)
        for s in self.children:
            self.children[s].sort(key=nat_key)
        self.area_node = {}
        for a, tr in self.traces:
            for n in tr["nodes"]:
                if n["cls"] == "area":
                    self.area_node.setdefault(a, n["id"])
        self._leaves = {}
        self.home = self.homes()

    # ---------------------------------------------------------------- homes
    def argmax(self, i):
        c = self.cnt[i]
        return min(c, key=lambda a: (-c[a], self.tab[a]))

    def root(self, i):
        while i in self.parent:
            i = self.parent[i]
        return i

    def homes(self):
        home = {}
        for i in self.order:
            c = self.cls[i]
            if c in STRUCT:
                r = self.root(i)
                home[i] = self.argmax(r) if self.cls.get(r) == "work" else self.argmax(i)
            elif c == "record":
                w = self.realizes.get(i)
                home[i] = self.argmax(w) if w in self.cnt else self.argmax(i)
            elif c != "other_question":
                home[i] = self.argmax(i)
        for a, n in self.area_node.items():
            home[n] = a
        # other answers hang under the provision they cite: in its region (their own area's region when they cite a
        # provision there), so the strands stay short, as in the paper
        for i in self.order:
            if self.cls[i] == "other_question":
                own = self.argmax(i)
                tg = [home[t] for t in self.cites.get(i, ()) if t in home]
                home[i] = own if (own in tg or not tg) else tg[0]
        return home

    def leaves(self, i):
        if i not in self._leaves:
            kids = [k for k in self.children.get(i, ()) if self.cls.get(k) in STRUCT]
            self._leaves[i] = sum(self.leaves(k) for k in kids) if kids else 1
        return self._leaves[i]

    # ---------------------------------------------------------------- per trace
    def trace_info(self, a, tr):
        ids = {n["id"] for n in tr["nodes"]}
        prim = next(p for p in tr["paths"] if p.get("primary"))
        q, ans = prim["nodes"][0], prim["nodes"][1]
        style = {}
        for p in tr["paths"]:
            st = 1 if p["verified"] else (2 if p.get("primary") else 0)
            if not st:
                continue
            for x, y in zip(p["nodes"], p["nodes"][1:]):
                e = (x, y) if x <= y else (y, x)
                style[e] = 1 if (style.get(e) == 1 or st == 1) else 2
        d = {ln["t"]: ln["s"] for ln in tr["links"] if ln["kind"] == "defines"}
        for t in tr.get("terms") or []:
            c = d.get(t["node"])
            if c in ids:
                for x, y in ((q, t["node"]), (t["node"], c)):
                    style[(x, y) if x <= y else (y, x)] = 1
        ca = tr.get("callouts") or {}
        prov = ca.get("provision") or (prim["nodes"][2] if len(prim["nodes"]) > 3 else prim["nodes"][-1])
        traced = [p for p in tr["paths"] if p["verified"] or p.get("primary")]
        main = next((p for p in sorted(traced, key=lambda p: (not p["verified"], not p.get("primary"))) if prov in p["nodes"]), prim)
        law = main["nodes"][-1]
        term = ca.get("term") if ca.get("term") in ids else None
        area = next((n["id"] for n in tr["nodes"] if n["cls"] == "area"), self.area_node.get(a))
        fg = {q, ans, prov, law, area} | ({term} if term else set())
        for (x, y) in style:
            fg.update((x, y))
        rec = next((r for r, w in self.realizes.items() if w == law and r in ids), None)
        if rec:
            fg.add(rec)
        return {"q": q, "ans": ans, "prov": prov, "law": law, "term": term, "area": area, "style": style, "fg": fg,
                "ids": [n["id"] for n in tr["nodes"]]}

    # ---------------------------------------------------------------- layout
    def layout(self):
        self.info = [self.trace_info(a, tr) for a, tr in self.traces]
        by_area = defaultdict(list)
        for i in self.order:
            by_area[self.home[i]].append(i)
        local, radius, pending = {}, {}, {}
        for a in self.areas:
            P, R, pend = self.region(a, by_area[a])
            local[a], radius[a], pending[a] = P, R, pend
        # regions on a grid in tab order: column widths and row depths from the largest region they hold
        rows = (len(self.areas) + COLS - 1) // COLS
        colw, rowd = [0.0] * COLS, [0.0] * rows
        for k, a in enumerate(self.areas):
            colw[k % COLS] = max(colw[k % COLS], 2 * radius[a])
            rowd[k // COLS] = max(rowd[k // COLS], 2 * radius[a])
        W = sum(colw) + REGION_GAP * (COLS - 1)
        D = sum(rowd) + REGION_GAP * (rows - 1)
        centre = {}
        for k, a in enumerate(self.areas):
            j, r = k % COLS, k // COLS
            x = -W / 2 + sum(colw[:j]) + REGION_GAP * j + colw[j] / 2
            z = -D / 2 + sum(rowd[:r]) + REGION_GAP * r + rowd[r] / 2
            centre[a] = (x, z)
        P = {}
        for a in self.areas:
            cx, cz = centre[a]
            for i, (x, y, z) in local[a].items():
                P[i] = (x + cx, y, z + cz)
        # questions whose provision lies in another region: on the side of their region that faces it
        for a in self.areas:
            cx, cz = centre[a]
            moved = []
            for q, ans, prov in pending[a]:
                if prov in P:
                    ux, uz = unit(P[prov][0] - cx, P[prov][2] - cz)
                else:
                    ux, uz = 1.0, 0.0
                r = 0.62 * radius[a]
                P[q] = (cx + ux * r, 0.0, cz + uz * r)
                moved.append(q)
            if moved:
                qs = [i for i in local[a] if self.cls[i] == "question"] + moved
                self.relax(P, qs, 11.0)
                for q, ans, prov in pending[a]:
                    self.place_answer(P, q, ans, prov)
        self.P, self.centre, self.radius = P, centre, radius
        self.ext = [min(p[0] for p in P.values()), max(p[0] for p in P.values()), min(p[2] for p in P.values()),
                    max(p[2] for p in P.values()), max(p[1] for p in P.values())]
        return P

    @staticmethod
    def relax(P, ids, dmin, rounds=40):
        """push floor nodes apart (deterministic order) until no two are closer than dmin"""
        for _ in range(rounds):
            moved = False
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = P[ids[i]], P[ids[j]]
                    dx, dz = b[0] - a[0], b[2] - a[2]
                    d = math.hypot(dx, dz)
                    if d >= dmin:
                        continue
                    ux, uz = unit(dx, dz, math.cos(i + j), math.sin(i + j))
                    s = (dmin - d) / 2 + 0.01
                    P[ids[i]] = (a[0] - ux * s, a[1], a[2] - uz * s)
                    P[ids[j]] = (b[0] + ux * s, b[1], b[2] + uz * s)
                    moved = True
            if not moved:
                return

    def place_answer(self, P, q, ans, prov):
        qx, _, qz = P[q]
        if prov in P:
            ux, uz = unit(P[prov][0] - qx, P[prov][2] - qz)
            d = min(5.0, 0.12 * math.hypot(P[prov][0] - qx, P[prov][2] - qz))
        else:
            ux, uz, d = 0.0, 0.0, 0.0
        P[ans] = (qx + ux * d, H * LEVEL["answer"], qz + uz * d)

    def region(self, a, members):
        """local layout of one area (region centre at x = z = 0); returns positions, radius and the questions to place
        once the regions are on the grid"""
        rnd = random.Random(seed_of("traces-global", a))
        P = {}
        cls = self.cls
        mem = set(members)
        works = sorted((i for i in members if cls[i] == "work"),
                       key=lambda w: (-self.cnt[w][a], -self.leaves(w), nat_key(w)))
        # cones: radius from the leaves on the outer ring; packed on a golden-angle spiral, largest first
        cones = []
        for w in works:
            R = max(CONE_MIN, self.leaves(w) * LEAF_GAP / (2 * math.pi * 0.86))
            if not cones:
                x = z = 0.0
            else:
                k = 0
                while True:
                    k += 1
                    rr, ang = 7.0 * math.sqrt(k), k * GOLDEN
                    x, z = rr * math.cos(ang), rr * math.sin(ang)
                    if all(math.hypot(x - px, z - pz) >= R + pr + GAP for px, pz, pr, _ in cones):
                        break
            cones.append((x, z, R, w))
        for ci, (cx, cz, R, w) in enumerate(cones):
            th0 = rnd.uniform(0, 2 * math.pi)
            P[w] = (cx, H * LEVEL["work"], cz)
            self.cone(P, w, cx, cz, R, th0, th0 + 2 * math.pi, rnd)
        # structure whose law is not in this region (never, by the home rule) or orphans: near the middle
        for i in members:
            if cls[i] in STRUCT and i not in P:
                P[i] = (rnd.uniform(-20, 20), H * LEVEL[cls[i]], rnd.uniform(-20, 20))
        for r in members:
            if cls[r] == "record":
                w = self.realizes.get(r)
                if w in P:
                    ang = rnd.uniform(0, 2 * math.pi)
                    P[r] = (P[w][0] + 11 * math.cos(ang), H * LEVEL["record"], P[w][2] + 11 * math.sin(ang))
                else:
                    P[r] = (rnd.uniform(-20, 20), H * LEVEL["record"], rnd.uniform(-20, 20))
        # questions and answers: under the provision the answer cites, pulled towards the middle
        info = [x for (ar, tr), x in zip(self.traces, self.info) if ar == a]
        qs, pend, prov_of = [], [], {}
        for x in info:
            q, ans, prov = x["q"], x["ans"], x["prov"]
            if q not in mem or q in P:
                continue
            prov_of[q] = prov
            if prov in P:
                px, _, pz = P[prov]
                P[q] = (0.82 * px, 0.0, 0.82 * pz)
                qs.append(q)
            else:
                pend.append((q, ans, prov))
        self.relax(P, qs, 11.0)
        for q in qs:
            self.place_answer(P, q, next(x["ans"] for x in info if x["q"] == q), prov_of[q])
        # terms: on the far side of their questions from the provisions, at about 40 % of the height
        terms = [i for i in members if cls[i] == "term"]
        tpos = []
        for t in sorted(terms, key=nat_key):
            pts = []
            for q in self.mentions.get(t, ()):
                if q in P and self.home.get(q) == a:
                    qx, _, qz = P[q]
                    pv = P.get(prov_of.get(q))
                    ux, uz = unit(qx - pv[0], qz - pv[2], *unit(-qx, -qz)) if pv else unit(-qx, -qz)
                    pts.append((qx + 24 * ux, qz + 24 * uz))
            if pts:
                x = sum(p[0] for p in pts) / len(pts)
                z = sum(p[1] for p in pts) / len(pts)
            else:
                ang = rnd.uniform(0, 2 * math.pi)
                x, z = 30 * math.cos(ang), 30 * math.sin(ang)
            P[t] = (x + rnd.uniform(-2, 2), H * (LEVEL["term"] + rnd.uniform(-0.035, 0.035)), z + rnd.uniform(-2, 2))
            tpos.append(t)
        self.relax(P, tpos, 10.0)
        # other answers: hanging low under the provision they cite first (this region's first)
        k_under = Counter()
        for o in members:
            if cls[o] != "other_question":
                continue
            tg = next((t for t in self.cites.get(o, ()) if t in P and self.home.get(t) == a), None)
            k = k_under[tg]
            k_under[tg] += 1
            bx, bz = (P[tg][0], P[tg][2]) if tg else (rnd.uniform(-30, 30), rnd.uniform(-30, 30))
            rr, ang = 3.0 + 2.1 * math.sqrt(k), k * GOLDEN + rnd.uniform(0, 0.4)
            y = H * (0.035 + 0.2 * ((k * 0.6180339887 + rnd.uniform(0, 0.25)) % 1.0))
            P[o] = (bx + rr * math.cos(ang), y, bz + rr * math.sin(ang))
        # the area above the middle of its region
        an = self.area_node.get(a)
        if an in mem:
            P[an] = (0.0, H * LEVEL["area"], 0.0)
        for i in members:                              # anything left (defensive)
            if i not in P:
                P[i] = (rnd.uniform(-25, 25), H * LEVEL.get(cls[i], 0.3), rnd.uniform(-25, 25))
        R = max([math.hypot(p[0], p[2]) + SIZE.get(cls[i], 8) for i, p in P.items()] + [60.0])
        R = max(R, max([c[2] + math.hypot(c[0], c[1]) for c in cones] + [0.0]) + 12.0)
        return P, R, pend

    def cone(self, P, n, cx, cz, R, t0, t1, rnd):
        kids = [k for k in self.children.get(n, ()) if self.cls.get(k) in STRUCT]
        if not kids:
            return
        tot = sum(self.leaves(k) for k in kids)
        t = t0
        for j, k in enumerate(kids):
            span = (t1 - t0) * self.leaves(k) / tot
            ang = t + span / 2 + rnd.uniform(-0.18, 0.18) * span
            # staggered rings with a little jitter: a hanging tree, not a ring of beads
            r = RING[self.cls[k]] * R * (1 + 0.07 * ((j % 3) - 1) + rnd.uniform(-0.035, 0.035))
            dh = 0.022 * ((j % 3) - 1) + rnd.uniform(-0.012, 0.012)
            P[k] = (cx + r * math.cos(ang), H * (LEVEL[self.cls[k]] + dh), cz + r * math.sin(ang))
            self.cone(P, k, cx, cz, R, t, t + span, rnd)
            t += span

    # ---------------------------------------------------------------- payload
    def payload(self):
        P = self.P
        ids = sorted(self.order, key=lambda i: (self.tab[self.home[i]], CLASSES.index(self.cls[i]), nat_key(i)))
        ix = {i: k for k, i in enumerate(ids)}
        pos = []
        for i in ids:
            x, y, z = P[i]
            pos += [int(round(x * 10)), int(round(y * 10)), int(round(z * 10))]
        derived = ("question", "answer", "other_question")
        vi = ["" if self.cls[i] in derived else self.node[i]["vi"] for i in ids]
        en = ["" if (self.cls[i] in derived or self.node[i]["en"] == self.node[i]["vi"]) else self.node[i]["en"] for i in ids]
        urls = {str(ix[i]): self.node[i]["url"] for i in ids if self.node[i]["url"] and self.cls[i] not in derived}
        e = {k: [] for k in KINDS}
        for (s, t, k) in sorted(self.edges, key=lambda x: self.edges[x]):
            e.setdefault(k, []).extend((ix[s], ix[t]))
        traces = []
        for (a, tr), x in zip(self.traces, self.info):
            seg = []
            for (u, v), st in sorted(x["style"].items(), key=lambda kv: (ix[kv[0][0]], ix[kv[0][1]])):
                seg += [ix[u], ix[v], st]
            traces.append({"a": self.tab[a], "r": tr["rank"], "n": sorted(ix[i] for i in x["ids"]),
                           "f": sorted(ix[i] for i in x["fg"]), "e": seg,
                           "co": [ix[x["q"]], ix[x["ans"]], ix[x["prov"]], ix[x["law"]], ix[x["term"]] if x["term"] else -1,
                                  ix[x["area"]]]})
        return {
            "v": 1, "classes": CLASSES, "kinds": KINDS, "H": H, "cols": COLS,
            "ext": [round(v, 1) for v in self.ext],
            "areas": [{"id": a, "c": [round(self.centre[a][0], 1), round(self.centre[a][1], 1)], "r": round(self.radius[a], 1)}
                      for a in self.areas],
            "i": ids, "c": [CLASSES.index(self.cls[i]) for i in ids], "h": [self.tab[self.home[i]] for i in ids],
            "p": pos, "vi": vi, "en": en, "u": urls, "e": e, "t": traces,
        }


def build_graph(areas: list, src: dict) -> tuple[dict, dict]:
    """areas: area ids in tab order; src: area id -> area JSON (build/traces/<area>.json). Returns the payload and stats."""
    g = Graph(areas, src)
    g.layout()
    out = g.payload()
    stats = {"nodes": len(out["i"]), "links": sum(len(v) // 2 for v in out["e"].values()),
             "links_by_kind": {k: len(v) // 2 for k, v in out["e"].items()}, "traces": len(out["t"]),
             "nodes_by_class": dict(Counter(g.cls.values())), "shared_nodes": sum(1 for i in g.order if len(g.cnt[i]) > 1),
             "ext": out["ext"], "cross_region_questions": sum(1 for x in g.info if g.home.get(x["prov"]) != g.home.get(x["q"]))}
    return out, stats
