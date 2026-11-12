"""3D layout of the VLOnto legal network (re-runnable by the website track).

x, y: 2D force-directed layout (igraph DrL by default, or Fruchterman-Reingold) of the undirected document graph
built from change (weight 3), legal-basis (weight 2) and citation (weight 1 + log n) links; documents without any
link are placed on an outer ring, grouped by legal area. z: legal-force layer (Constitution on top).

    python -m vlonto.layout3d [--algo drl|fr] [--seed 7] [--out $V/build/site_data/legal_network.json]
                              [--lite-out $V/build/site_data/legal_network_lite.json] [--lite-nodes 6000]

Writes the bundle JSON files and their .js twins (window.VLONTO["legal_network"] = ...).
"""
import argparse
import json
import math
import os
import random
import time
from collections import Counter, defaultdict

import polars as pl

from . import config as C
from .nfc import nfc_obj

Z_SPACING = 150


def load(kg):
    docs = pl.read_parquet(os.path.join(kg, "documents.parquet"), columns=[
        "doc_id", "doc_number", "title_vi", "doc_type_code", "year", "issuer_ids", "area_id", "validity", "legal_force_rank"])
    ch = pl.read_parquet(os.path.join(kg, "changes.parquet"), columns=["acting_doc_id", "affected_doc_id", "kind"])
    lb = pl.read_parquet(os.path.join(kg, "edges_legal_basis.parquet"), columns=["src_doc_id", "dst_doc_id", "method"])
    ci = (pl.read_parquet(os.path.join(kg, "edges_citation.parquet"), columns=["src_doc_id", "dst_doc_id"])
          .filter(pl.col("src_doc_id") != pl.col("dst_doc_id")).group_by(["src_doc_id", "dst_doc_id"]).len())
    return docs, ch, lb, ci


def compute_layout(docs, ch, lb, ci, algo="drl", seed=7):
    import igraph as ig
    idx = {d: i for i, d in enumerate(docs["doc_id"].to_list())}
    w = defaultdict(float)
    for a, b in ch.select("acting_doc_id", "affected_doc_id").iter_rows():
        if a != b:
            w[tuple(sorted((idx[a], idx[b])))] += 3.0
    for a, b in lb.select("src_doc_id", "dst_doc_id").iter_rows():
        if a != b:
            w[tuple(sorted((idx[a], idx[b])))] += 2.0
    for a, b, n in ci.iter_rows():
        w[tuple(sorted((idx[a], idx[b])))] += 1.0 + math.log1p(n)
    n = len(idx)
    deg = [0] * n
    for (a, b) in w:
        deg[a] += 1
        deg[b] += 1
    linked = [i for i in range(n) if deg[i] > 0]
    pos = {i: k for k, i in enumerate(linked)}
    g = ig.Graph(n=len(linked), edges=[(pos[a], pos[b]) for (a, b) in w], directed=False)
    g.es["weight"] = list(w.values())
    rnd = random.Random(seed)
    ig.set_random_number_generator(rnd)
    t0 = time.time()
    if algo == "fr":
        lay = g.layout_fruchterman_reingold(weights="weight", niter=1500, grid="auto")
    else:
        lay = g.layout_drl(weights="weight")
    secs = round(time.time() - t0, 1)
    xs = [p[0] for p in lay.coords]
    ys = [p[1] for p in lay.coords]
    # robust scaling to [-1000, 1000] using the 1st-99th percentile box
    def q(v, f):
        s = sorted(v)
        return s[int(f * (len(s) - 1))]
    x0, x1, y0, y1 = q(xs, 0.01), q(xs, 0.99), q(ys, 0.01), q(ys, 0.99)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sc = 1800.0 / max(x1 - x0, y1 - y0, 1e-9)
    X, Y = [0.0] * n, [0.0] * n
    for i, k in pos.items():
        X[i] = max(-1100.0, min(1100.0, (xs[k] - cx) * sc))
        Y[i] = max(-1100.0, min(1100.0, (ys[k] - cy) * sc))
    # isolated documents: outer ring, one sector per legal area, radius jitter
    areas = docs["area_id"].fill_null("none").to_list()
    iso = [i for i in range(n) if deg[i] == 0]
    area_list = sorted({areas[i] for i in iso})
    sector = {a: k for k, a in enumerate(area_list)}
    per = Counter(areas[i] for i in iso)
    seen = Counter()
    for i in iso:
        a = areas[i]
        k = sector[a]
        j = seen[a]
        seen[a] += 1
        span = 2 * math.pi / max(1, len(area_list))
        ang = k * span + span * (j + 0.5) / max(1, per[a]) * 0.9
        r = 1250 + 120 * rnd.random()
        X[i], Y[i] = r * math.cos(ang), r * math.sin(ang)
    return X, Y, deg, {"algo": algo, "seed": seed, "linked_documents": len(linked), "isolated_documents": len(iso),
                       "undirected_links": len(w), "layout_seconds": secs}


def write_js_twin(json_path, name):
    jsdir = os.path.join(os.path.dirname(json_path), "js")
    os.makedirs(jsdir, exist_ok=True)
    from .nfc import nfc
    data = nfc(open(json_path, encoding="utf-8").read())
    out = os.path.join(jsdir, f"{name}.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.VLONTO = window.VLONTO || {};\nwindow.VLONTO[" + json.dumps(name) + "] = " + data + ";\n")
    return out


def bundle(docs, ch, lb, ci, X, Y, deg, meta, keep=None):
    issuers = pl.read_parquet(os.path.join(C.KG, "issuers.parquet"), columns=["issuer_id", "label_vi", "label_en"])
    areas = pl.read_parquet(os.path.join(C.KG, "areas.parquet"), columns=["area_id", "label_vi", "label_en"])
    iss_idx = {r[0]: k for k, r in enumerate(issuers.iter_rows())}
    area_idx = {r[0]: k for k, r in enumerate(areas.iter_rows())}
    types = list(dict.fromkeys(v[2] for v in C.DOC_TYPES.values()))
    type_idx = {t: k for k, t in enumerate(types)}
    vals = list(C.VALIDITY_CONCEPT)
    val_idx = {v: k for k, v in enumerate(vals)}
    rows = docs.to_dicts()
    sel = list(range(len(rows))) if keep is None else sorted(keep)
    new = {i: k for k, i in enumerate(sel)}
    nodes = []
    for i in sel:
        r = rows[i]
        rank = int(r["legal_force_rank"])
        title = C.cut(r["title_vi"], 70) or ""
        nodes.append([r["doc_id"], r["doc_number"] or "", title, type_idx[r["doc_type_code"]], r["year"] if r["year"] is not None else -1,
                      iss_idx.get((r["issuer_ids"] or [None])[0], -1), area_idx.get(r["area_id"], -1), val_idx.get(r["validity"], len(vals) - 1),
                      rank, deg[i], int(round(X[i])), int(round(Y[i])), (5 - rank) * Z_SPACING])
    idx = {d: i for i, d in enumerate(docs["doc_id"].to_list())}
    kinds = list(C.CHANGE_CONCEPT)
    kidx = {k: j for j, k in enumerate(kinds)}
    E = {"change": [], "basis": [], "citation": []}
    for a, b, kd in ch.iter_rows():
        ia, ib = idx[a], idx[b]
        if ia in new and ib in new:
            E["change"].append([new[ia], new[ib], kidx[kd]])
    for a, b, m in lb.iter_rows():
        ia, ib = idx[a], idx[b]
        if ia in new and ib in new:
            E["basis"].append([new[ia], new[ib], 0 if m == "parent-acts" else 1])
    for a, b, n in ci.iter_rows():
        ia, ib = idx[a], idx[b]
        if ia in new and ib in new:
            E["citation"].append([new[ia], new[ib], n])
    return {
        "name": "VLOnto legal network", "version": C.VERSION, "generated": C.BUILD_DATE,
        "description": "Documents as nodes; x/y from a force layout of change + legal-basis + citation links; z = legal-force layer (Constitution on top). Edges are directed source -> target.",
        "layout": {**meta, "x_y_range": [-1370, 1370], "z_spacing": Z_SPACING, "z_by_rank": {str(k): (5 - k) * Z_SPACING for k in range(6)}},
        "fields": ["id", "number", "title", "type", "year", "issuer", "area", "validity", "rank", "degree", "x", "y", "z"],
        "types": [{"code": v[2], "class": v[0], "vi": k, "en": C.DOC_TYPE_EN[k]} for k, v in C.DOC_TYPES.items()],
        "issuers": [list(r) for r in issuers.iter_rows()], "areas": [list(r) for r in areas.iter_rows()], "validity": vals,
        "ranks": [{"rank": k, "en": v[0], "vi": v[1]} for k, v in C.RANK_LABELS.items()],
        "nodes": nodes,
        "edge_fields": {"change": ["source", "target", "kind"], "basis": ["source", "target", "method (0 parent-acts, 1 preamble)"],
                        "citation": ["source", "target", "citation edges between the two documents"]},
        "change_kinds": kinds,
        "edges": E, "counts": {"nodes": len(nodes), **{k: len(v) for k, v in E.items()}},
        "subsetting": ("Node rows are arrays in the order of 'fields'; type/issuer/area/validity are indexes into the lookup lists (-1 = none). "
                       "To subset in the browser, filter nodes (e.g. rank <= 3, a type, an area, degree >= k) and keep edges whose two endpoint "
                       "indexes survive, re-indexing them; legal_network_lite.json is such a subset (all documents of rank <= 2 plus the "
                       "highest-degree documents up to the node budget)."),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", default="drl", choices=["drl", "fr"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(C.SITE, "legal_network.json"))
    ap.add_argument("--lite-out", default=os.path.join(C.SITE, "legal_network_lite.json"))
    ap.add_argument("--lite-nodes", type=int, default=6000)
    a = ap.parse_args(argv)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    docs, ch, lb, ci = load(C.KG)
    X, Y, deg, meta = compute_layout(docs, ch, lb, ci, a.algo, a.seed)
    full = bundle(docs, ch, lb, ci, X, Y, deg, meta)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(nfc_obj(full), f, ensure_ascii=False, separators=(",", ":"))
    write_js_twin(a.out, "legal_network")
    ranks = docs["legal_force_rank"].to_list()
    keep = {i for i, r in enumerate(ranks) if r <= 2}
    for i in sorted(range(len(deg)), key=lambda i: -deg[i]):
        if len(keep) >= a.lite_nodes:
            break
        keep.add(i)
    lite = bundle(docs, ch, lb, ci, X, Y, deg, {**meta, "subset": f"rank <= 2 plus top-degree documents, {a.lite_nodes} nodes"}, keep)
    with open(a.lite_out, "w", encoding="utf-8") as f:
        json.dump(nfc_obj(lite), f, ensure_ascii=False, separators=(",", ":"))
    write_js_twin(a.lite_out, "legal_network_lite")
    info = {"full": {"path": a.out, "bytes": os.path.getsize(a.out), **full["counts"]},
            "lite": {"path": a.lite_out, "bytes": os.path.getsize(a.lite_out), **lite["counts"]}, "layout": meta}
    print(json.dumps(info, indent=1), flush=True)
    return info


if __name__ == "__main__":
    main()
