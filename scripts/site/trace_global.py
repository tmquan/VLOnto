#!/usr/bin/env python3
"""trace_global.py - traces.html: all question traces inside the 3D legal network (stdlib only, deterministic).

The scene of traces.html is the whole 3D legal network of network-3d.html (site/data/legal_network.js: every document
at its own x / y, z = its legal-force layer, z_by_rank 750 .. 0) and the traces live in it. No grid of area cells: an
area is its 20 questions, wherever their laws are.
  * A traced law ('work') IS its document node of the network: the network node whose id is the vbpl record id of the
    trace data (provenance.record of the work, the same id as its source URL). The law's number agrees with the
    network's (case-insensitive) where the network has one; a number carried by two network documents is resolved by
    that id, never by order. The law's record node ('vbpl:<id>', linked by 'realizes') is the same document and is
    merged into it. A law that is not in the network would stay an extra node at z = 0 (none in the current data).
  * The provision chain (chapter, section, article, clause, point) hangs in a small fan directly under its law, inside
    the 150-unit gap above the next layer: depth by class (FAN_DEPTH), rings by class (FAN_RING) of a radius from the
    law's leaf count, angles shared by leaf count (siblings in natural order).
  * The Q&A side lies on planes under the lowest document layer (z = 0), one layer gap (150) apart, so a trace runs up
    through the layers as the legal force does: answers z = -150, the other answers that cite the same provisions
    just under them (-165), the terms half-way to the questions (-225; the second arm of the paper's V: question ->
    term -> defining clause), the questions z = -300, each area's label node under its questions (-380).
  * x / y of a question and its answer: the centroid of the laws on the trace's traced paths, a deterministic spiral
    around it for questions with the same centroid, then a relaxation on the plane so no two questions are closer than
    Q_GAP; a term between its defining clauses and its questions; an other answer on a spiral under the provision it
    cites first; an area's label node at the centroid of its questions (relaxed apart from the other areas').
The page (js/traces3d.js) draws the network as js/netscene.js / network-3d.html do and the trace nodes and links with
it in one WebGL scene; all 540 traces are drawn light, the selected ones solid.

Output: build_graph(areas, src, net) returns the payload of site/data/traces/graph.js (window.VLONTO["traces_graph"]):
  v 2, classes, kinds, planes {z_answer, z_other, z_term, z_question, z_area, fan: {class: depth below the law}}
  net     {nodes, z_by_rank}: the network the laws refer to (data/legal_network.js)
  i       node ids; c class index (classes)
  p       positions [x, y, z, x, y, z, ...] in the network's units (z up, as legal_network.js), tenths (integers)
  d       {node index: network document id} of the laws
  vi, en  labels; empty for questions, answers and other answers (named by id on the page; the titles of the traced
          questions stay in the area files and questions.js) and en empty when it equals vi
  u       {node index: source url}
  e       {kind: [s0, t0, s1, t1, ...]} the unique links of every kind (no 'realizes': records are their laws)
  t       per trace, in area and rank order: {"a": area index, "r": rank, "n": [nodes of the trace], "f": [foreground
          nodes: the traced path, the question, its answer and area, the call-out nodes], "e": [i, j, style, ...] traced
          segments (style 1 = text-verified path or term -> defining clause, 2 = structural primary path),
          "co": [question, answer, provision, law, term or -1, area]}
  areas   [{"id", "n": label node index, "docs": the area's documents in the whole network}] in list order
  wa      {law node index: area index (list order) of its network document}
No question titles, answer text, provision text or definitions: labels are the law, provision and term names already
published in the area files.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace_layout as TL  # noqa: E402  (class order shared with the area files)

CLASSES = TL.CLASSES
KINDS = ["contains", "cites", "mentions", "defines", "answers", "applies_to"]
STRUCT = ("chapter", "section", "article", "clause", "point")
# the Q&A planes under the lowest document layer (z = 0), in the network's units
Z = {"answer": -150.0, "other_question": -165.0, "term": -225.0, "question": -300.0, "area": -380.0}
# the provision fan under its law: depth below the law by class (inside the 150-unit layer gap), ring by class
FAN_DEPTH = {"chapter": 24.0, "section": 42.0, "article": 60.0, "clause": 80.0, "point": 98.0}
FAN_RING = {"chapter": 0.32, "section": 0.5, "article": 0.7, "clause": 0.88, "point": 1.0}
FAN_R = (10.0, 2.4, 52.0)                    # radius: at least, per square root of the leaf count, at most
Q_GAP = 16.0                                 # questions (and their answers) on their planes
T_GAP = 14.0                                 # terms
A_GAP = 120.0                                # area label nodes
GOLDEN = math.pi * (3.0 - math.sqrt(5.0))


def seed_of(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12], 16)


def nat_key(s: str):
    """natural order of structure ids ('...::dieu-9' before '...::dieu-10')"""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", s) if t]


def fold_number(s: str) -> str:
    return unicodedata.normalize("NFC", str(s or "")).strip().lower()


def relax2d(P, ids, dmin, rounds=80):
    """push nodes of one plane apart (x, y; deterministic order, grid neighbours) until none are closer than dmin"""
    for _ in range(rounds):
        moved = False
        grid = defaultdict(list)
        for k, i in enumerate(ids):
            grid[(math.floor(P[i][0] / dmin), math.floor(P[i][1] / dmin))].append(k)
        for k, i in enumerate(ids):
            gx, gy = math.floor(P[i][0] / dmin), math.floor(P[i][1] / dmin)
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    for k2 in grid.get((gx + ox, gy + oy), ()):
                        if k2 <= k:
                            continue
                        j = ids[k2]
                        a, b = P[i], P[j]
                        dx, dy = b[0] - a[0], b[1] - a[1]
                        d = math.hypot(dx, dy)
                        if d >= dmin:
                            continue
                        if d < 1e-6:
                            ang = (k + k2) * GOLDEN
                            dx, dy, d = math.cos(ang), math.sin(ang), 1.0
                        s = (dmin - d) / 2 + 0.01
                        ux, uy = dx / d, dy / d
                        P[i] = (a[0] - ux * s, a[1] - uy * s, a[2])
                        P[j] = (b[0] + ux * s, b[1] + uy * s, b[2])
                        moved = True
        if not moved:
            return


class Graph:
    def __init__(self, areas: list, src: dict, net: dict):
        self.areas, self.tab = areas, {a: i for i, a in enumerate(areas)}
        self.node, self.order = {}, []
        edges, self.traces = {}, []
        for a in areas:
            for tr in src[a]["traces"]:
                self.traces.append((a, tr))
                for n in tr["nodes"]:
                    if n["id"] not in self.node:
                        self.node[n["id"]] = {"cls": n["cls"], "vi": n.get("label_vi") or "", "en": n.get("label_en") or "",
                                              "url": n.get("url") or "", "prov": n.get("provenance") or {}}
                        self.order.append(n["id"])
                for ln in tr["links"]:
                    k = (ln["s"], ln["t"], ln["kind"])
                    if k not in edges:
                        edges[k] = len(edges)
        self.cls = {i: d["cls"] for i, d in self.node.items()}
        # a record is the document of the law it realizes: one node (the law's)
        self.alias = {s: t for (s, t, k) in edges if k == "realizes" and self.cls.get(s) == "record"}
        self.edges = {}
        for (s, t, k), n in sorted(edges.items(), key=lambda kv: kv[1]):
            if k == "realizes":
                continue
            s, t = self.alias.get(s, s), self.alias.get(t, t)
            if s != t and (s, t, k) not in self.edges:
                self.edges[(s, t, k)] = len(self.edges)
        self.order = [i for i in self.order if i not in self.alias]
        self.parent, self.children = {}, defaultdict(list)
        self.cites, self.mentions, self.defines = defaultdict(list), defaultdict(list), defaultdict(list)
        for (s, t, k) in self.edges:
            if k == "contains" and t not in self.parent:
                self.parent[t] = s
                self.children[s].append(t)
            elif k == "cites":
                self.cites[s].append(t)
            elif k == "mentions":
                self.mentions[t].append(s)            # term -> questions
            elif k == "defines":
                self.defines[t].append(s)             # term -> defining clauses
        for s in self.children:
            self.children[s].sort(key=nat_key)
        self.area_node = {}
        for a, tr in self.traces:
            for n in tr["nodes"]:
                if n["cls"] == "area":
                    self.area_node.setdefault(a, n["id"])
        self._leaves = {}
        self.net = net
        self.match = self.match_works()

    # ---------------------------------------------------------------- the laws are network documents
    def match_works(self):
        F = {f: i for i, f in enumerate(self.net["fields"])}
        nodes = self.net["nodes"]
        by_id = {str(r[F["id"]]): k for k, r in enumerate(nodes)}
        by_num = defaultdict(list)
        for k, r in enumerate(nodes):
            if r[F["number"]]:
                by_num[fold_number(r[F["number"]])].append(k)
        doc, report = {}, {"works": 0, "by_record_id": 0, "number_agrees": 0, "number_on_two_or_more": [], "number_not_in_network": [],
                           "not_in_network": []}
        for w in sorted(i for i in self.order if self.cls[i] == "work"):
            report["works"] += 1
            n = self.node[w]
            rec = str(n["prov"].get("record") or "")
            m = re.search(r"-(\d+)\.aspx", n["url"])
            k = by_id.get(rec)
            if k is None and m:
                k = by_id.get(m.group(1))
            num = fold_number(w.split(":", 1)[1])
            cand = by_num.get(num, [])
            if k is None:
                report["not_in_network"].append(w)
                continue
            doc[w] = k
            report["by_record_id"] += 1
            if k in cand:
                report["number_agrees"] += 1
            if len(cand) > 1:
                report["number_on_two_or_more"].append({"work": w, "chosen": str(nodes[k][F["id"]]),
                                                        "others": sorted(str(nodes[c][F["id"]]) for c in cand if c != k)})
            if not cand:
                report["number_not_in_network"].append({"work": w, "id": str(nodes[k][F["id"]]),
                                                        "network_number": nodes[k][F["number"]] or ""})
        self.F, self.doc = F, doc
        return report

    def root(self, i):
        while i in self.parent:
            i = self.parent[i]
        return i

    def leaves(self, i):
        if i not in self._leaves:
            kids = [k for k in self.children.get(i, ()) if self.cls.get(k) in STRUCT]
            self._leaves[i] = sum(self.leaves(k) for k in kids) if kids else 1
        return self._leaves[i]

    # ---------------------------------------------------------------- per trace
    def trace_info(self, a, tr):
        al = self.alias
        ids = {al.get(n["id"], n["id"]) for n in tr["nodes"]}
        prim = next(p for p in tr["paths"] if p.get("primary"))
        q, ans = prim["nodes"][0], prim["nodes"][1]
        style = {}
        for p in tr["paths"]:
            st = 1 if p["verified"] else (2 if p.get("primary") else 0)
            if not st:
                continue
            nodes = [al.get(x, x) for x in p["nodes"]]
            for x, y in zip(nodes, nodes[1:]):
                if x == y:
                    continue
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
        prov = al.get(prov, prov)
        traced = [p for p in tr["paths"] if p["verified"] or p.get("primary")]
        main = next((p for p in sorted(traced, key=lambda p: (not p["verified"], not p.get("primary"))) if prov in [al.get(x, x) for x in p["nodes"]]), prim)
        law = al.get(main["nodes"][-1], main["nodes"][-1])
        term = ca.get("term") if ca.get("term") in ids else None
        area = next((n["id"] for n in tr["nodes"] if n["cls"] == "area"), self.area_node.get(a))
        fg = {q, ans, prov, law, area} | ({term} if term else set())
        for (x, y) in style:
            fg.update((x, y))
        laws = sorted({x for e in style for x in e if self.cls.get(x) == "work"} | ({law} if self.cls.get(law) == "work" else set()))
        if not laws:
            laws = sorted(i for i in ids if self.cls.get(i) == "work")
        return {"q": q, "ans": ans, "prov": prov, "law": law, "term": term, "area": area, "style": style, "fg": fg,
                "ids": sorted(ids), "laws": laws}

    # ---------------------------------------------------------------- layout
    def layout(self):
        self.info = [self.trace_info(a, tr) for a, tr in self.traces]
        F, nodes = self.F, self.net["nodes"]
        P = {}
        # 1. the laws: their documents' places in the network (a law not in the network: an extra node at z = 0)
        extra = 0
        for w in sorted(i for i in self.order if self.cls[i] == "work"):
            if w in self.doc:
                r = nodes[self.doc[w]]
                P[w] = (float(r[F["x"]]), float(r[F["y"]]), float(r[F["z"]]))
            else:
                ang = extra * GOLDEN
                P[w] = (40.0 * math.sqrt(extra + 1) * math.cos(ang), 40.0 * math.sqrt(extra + 1) * math.sin(ang), 0.0)
                extra += 1
        # 2. the provision fans under their laws
        for w in sorted(i for i in self.order if self.cls[i] == "work"):
            rnd = random.Random(seed_of("traces-fan", w))
            R = min(FAN_R[2], max(FAN_R[0], FAN_R[0] + FAN_R[1] * math.sqrt(self.leaves(w))))
            th0 = rnd.uniform(0, 2 * math.pi)
            self.fan(P, w, P[w], R, th0, th0 + 2 * math.pi, rnd)
        # 3. questions and answers: the centroid of the trace's traced laws, a spiral per centroid, relaxed apart
        laws_of = defaultdict(set)
        for x in self.info:
            laws_of[x["q"]].update(x["laws"])
        cen = {}
        for q, ls in laws_of.items():
            pts = [P[w] for w in sorted(ls) if w in P]
            cen[q] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else (0.0, 0.0)
        qorder = []
        seen = set()
        for x in self.info:                                   # area and rank order
            if x["q"] not in seen:
                seen.add(x["q"])
                qorder.append(x["q"])
        k_at = Counter()
        for q in qorder:
            key = (round(cen[q][0]), round(cen[q][1]))
            k = k_at[key]
            k_at[key] += 1
            r, ang = 0.62 * Q_GAP * math.sqrt(k), k * GOLDEN
            P[q] = (cen[q][0] + r * math.cos(ang), cen[q][1] + r * math.sin(ang), Z["question"])
        relax2d(P, qorder, Q_GAP)
        for x in self.info:
            qx, qy, _ = P[x["q"]]
            P[x["ans"]] = (qx, qy, Z["answer"])
        # 4. terms: between their defining clauses and their questions
        terms = sorted((i for i in self.order if self.cls[i] == "term"), key=nat_key)
        for t in terms:
            qs = [P[q] for q in sorted(self.mentions.get(t, ())) if q in P]
            dc = [P[c] for c in sorted(self.defines.get(t, ())) if c in P]
            qc = (sum(p[0] for p in qs) / len(qs), sum(p[1] for p in qs) / len(qs)) if qs else (0.0, 0.0)
            if dc:
                cc = (sum(p[0] for p in dc) / len(dc), sum(p[1] for p in dc) / len(dc))
                x, y = (qc[0] + cc[0]) / 2, (qc[1] + cc[1]) / 2
            else:
                x, y = qc
            rnd = random.Random(seed_of("traces-term", t))
            P[t] = (x + rnd.uniform(-3, 3), y + rnd.uniform(-3, 3), Z["term"])
        relax2d(P, terms, T_GAP)
        # 5. other answers: on a spiral under the provision they cite first
        k_under = Counter()
        others = [i for i in self.order if self.cls[i] == "other_question"]
        for o in others:
            tg = next((t for t in self.cites.get(o, ()) if t in P), None)
            base = (P[tg][0], P[tg][1]) if tg else (0.0, 0.0)
            k = k_under[tg]
            k_under[tg] += 1
            rnd = random.Random(seed_of("traces-other", o))
            r, ang = 3.0 + 2.6 * math.sqrt(k), k * GOLDEN + rnd.uniform(0, 0.4)
            P[o] = (base[0] + r * math.cos(ang), base[1] + r * math.sin(ang), Z["other_question"])
        # 6. the areas' label nodes: the centroid of their questions, relaxed apart
        alabel = []
        for a in self.areas:
            an = self.area_node.get(a)
            if an is None:
                continue
            qs = [P[x["q"]] for (ar, _), x in zip(self.traces, self.info) if ar == a and x["q"] in P]
            P[an] = (sum(p[0] for p in qs) / len(qs), sum(p[1] for p in qs) / len(qs), Z["area"]) if qs else (0.0, 0.0, Z["area"])
            alabel.append(an)
        relax2d(P, alabel, A_GAP)
        for i in self.order:                                  # anything left (defensive): at the middle of the answers
            if i not in P:
                P[i] = (0.0, 0.0, Z["answer"])
        self.P, self.extra = P, extra
        return P

    def fan(self, P, n, w, R, t0, t1, rnd):
        kids = [k for k in self.children.get(n, ()) if self.cls.get(k) in STRUCT]
        if not kids:
            return
        tot = sum(self.leaves(k) for k in kids)
        t = t0
        for j, k in enumerate(kids):
            span = (t1 - t0) * self.leaves(k) / tot
            ang = t + span / 2 + rnd.uniform(-0.15, 0.15) * span
            c = self.cls[k]
            r = FAN_RING[c] * R * (1 + 0.06 * ((j % 3) - 1))
            dz = 2.5 * ((j % 3) - 1) + rnd.uniform(-1.0, 1.0)
            P[k] = (w[0] + r * math.cos(ang), w[1] + r * math.sin(ang), w[2] - FAN_DEPTH[c] + dz)
            self.fan(P, k, w, R, t, t + span, rnd)
            t += span

    # ---------------------------------------------------------------- payload
    def payload(self):
        P = self.P
        ids = sorted(self.order, key=lambda i: (CLASSES.index(self.cls[i]), nat_key(i)))
        ix = {i: k for k, i in enumerate(ids)}
        pos = []
        for i in ids:
            x, y, z = P[i]
            pos += [int(round(x * 10)), int(round(y * 10)), int(round(z * 10))]
        derived = ("question", "answer", "other_question")
        vi = ["" if self.cls[i] in derived else self.node[i]["vi"] for i in ids]
        en = ["" if (self.cls[i] in derived or self.node[i]["en"] == self.node[i]["vi"]) else self.node[i]["en"] for i in ids]
        urls = {str(ix[i]): self.node[i]["url"] for i in ids if self.node[i]["url"] and self.cls[i] not in derived}
        F, nodes = self.F, self.net["nodes"]
        doc = {str(ix[w]): str(nodes[k][F["id"]]) for w, k in sorted(self.doc.items())}
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
        lay = self.net.get("layout") or {}
        # colour by legal area (js/traces3d.js): every area's documents in the whole network (the page ranks the 27
        # colours by them, on phones too, where only the lite network is loaded) and every law's area (its network
        # document's), so a law the lite network lacks still takes its own colour
        net_area = [a[0] for a in (self.net.get("areas") or [])]

        def doc_area(k):
            v = nodes[k][F["area"]]
            return net_area[v] if isinstance(v, int) and 0 <= v < len(net_area) else None
        docs_by_area = Counter(a for a in (doc_area(k) for k in range(len(nodes))) if a is not None)
        wa = {str(ix[w]): self.tab[doc_area(k)] for w, k in sorted(self.doc.items(), key=lambda kv: ix[kv[0]]) if doc_area(k) in self.tab}
        return {
            "v": 2, "classes": CLASSES, "kinds": KINDS,
            "planes": {**{"z_" + {"other_question": "other"}.get(k, k): v for k, v in Z.items()}, "fan": FAN_DEPTH},
            "net": {"nodes": len(nodes), "z_by_rank": lay.get("z_by_rank")},
            "i": ids, "c": [CLASSES.index(self.cls[i]) for i in ids], "p": pos, "d": doc,
            "vi": vi, "en": en, "u": urls, "e": e, "t": traces,
            "areas": [{"id": a, "n": ix[self.area_node[a]], "docs": docs_by_area.get(a, 0)} for a in self.areas if self.area_node.get(a) in ix],
            "wa": wa,
        }


def build_graph(areas: list, src: dict, net: dict) -> tuple[dict, dict]:
    """areas: area ids in list order; src: area id -> area JSON (build/traces/<area>.json); net: the legal network
    (legal_network.json). Returns the payload and stats."""
    g = Graph(areas, src, net)
    g.layout()
    out = g.payload()
    P = g.P
    zs = Counter(g.cls[i] for i in g.order)
    fan_low = min((P[i][2] - P[g.root(i)][2] for i in g.order if g.cls[i] in STRUCT), default=0.0)
    traces_in_net = sum(1 for x in g.info if all(w in g.doc for w in x["ids"] if g.cls.get(w) == "work"))
    stats = {"nodes": len(out["i"]), "links": sum(len(v) // 2 for v in out["e"].values()),
             "links_by_kind": {k: len(v) // 2 for k, v in out["e"].items()}, "traces": len(out["t"]),
             "nodes_by_class": dict(sorted(zs.items())), "records_merged": len(g.alias), "laws": g.match,
             "laws_not_in_network": g.extra, "traces_with_all_laws_in_network": traces_in_net,
             "fan_lowest_below_law": round(fan_low, 1), "planes": out["planes"],
             "xy_extent_qa": [round(min(P[i][0] for i in g.order if g.cls[i] in ("question", "answer")), 1),
                              round(max(P[i][0] for i in g.order if g.cls[i] in ("question", "answer")), 1),
                              round(min(P[i][1] for i in g.order if g.cls[i] in ("question", "answer")), 1),
                              round(max(P[i][1] for i in g.order if g.cls[i] in ("question", "answer")), 1)]}
    return out, stats
