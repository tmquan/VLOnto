#!/usr/bin/env python3
"""derive_site_data.py - website-owned data derived from the publishable VLOnto KG tables (inputs are read-only).

Run with the KG environment (polars), from the repo root:
    $V/envs/kg/bin/python scripts/site/derive_site_data.py --kg $V/build/kg --site-data $V/build/site_data --out $V/build/site_extra

Writes JSON files that build_site.py turns into site/data/*.js with tools/json2js.py:
  doc_links.json        all change events (15,035), all legal-basis edges (99,038) and per-document counts
                        (articles, basis, citations, Q&As, court decisions, news), indexed like legal_network.json
  doc_details_NN.json   per-document issue/effective/expiry dates, source status, issuers, source URL and the
                        evidence sentence of the change events that affect the document, in shards of 4,096
  dash_extra.json       per-document columns for the dashboard filters (type, year, area, issuer, validity, rank),
                        change events (kind, year, affected document) and the 400 most-cited documents/articles per source
Licence policy: only metadata that is already in the publishable KG tables (no text bodies, no person names,
evidence quotes <= 300 characters, headings <= 200 characters); build/kg_local is never read.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import polars as pl

SHARD = 4096
URL_PREFIX = "https://thuvienphapluat.vn/van-ban/"
TOP_N = 400


def nfc(s):
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s


def dump(obj, path: Path):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path.stat().st_size


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kg", type=Path, required=True)
    ap.add_argument("--site-data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if "kg_local" in str(a.kg):
        print("refusing to read kg_local (not publishable)", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    T = lambda name, cols=None: pl.read_parquet(a.kg / f"{name}.parquet", columns=cols)

    net = json.loads((a.site_data / "legal_network.json").read_text(encoding="utf-8"))
    F = {f: i for i, f in enumerate(net["fields"])}
    ids = [n[F["id"]] for n in net["nodes"]]
    idx = {d: i for i, d in enumerate(ids)}
    N = len(ids)
    issuer_idx = {row[0]: i for i, row in enumerate(net["issuers"])}
    area_idx = {row[0]: i for i, row in enumerate(net["areas"])}
    type_idx = {t["code"]: i for i, t in enumerate(net["types"])}
    validity_idx = {v: i for i, v in enumerate(net["validity"])}
    kinds = list(net["change_kinds"])
    kind_idx = {k: i for i, k in enumerate(kinds)}
    report = {"documents": N}

    docs = T("documents")
    assert docs.height == N, (docs.height, N)
    drows = {r["doc_id"]: r for r in docs.iter_rows(named=True)}
    assert set(drows) == set(ids)

    # ------------------------------------------------------------------ counts per document
    lb = T("edges_legal_basis", ["src_doc_id", "dst_doc_id", "method"])
    ci = T("edges_citation", ["src_doc_id", "dst_doc_id"]).filter(pl.col("src_doc_id") != pl.col("dst_doc_id"))
    qa_doc = T("edges_qa_document", ["qa_id", "dst_doc_id"])
    qa_art = T("edges_qa_article", ["qa_id", "dst_doc_id", "dst_article_id"])
    dp = T("edges_decision_provision", ["decision_id", "dst_doc_id", "dst_article_id"])
    ne = T("edges_news_document", ["news_id", "dst_doc_id"])

    def count_map(df, key, val=None):
        if val is None:
            t = df.group_by(key).agg(pl.len().alias("n"))
        else:
            t = df.group_by(key).agg(pl.col(val).n_unique().alias("n"))
        out = [0] * N
        for k, n in t.iter_rows():
            if k in idx:
                out[idx[k]] = int(n)
        return out

    qa_docs = pl.concat([qa_doc.select("qa_id", "dst_doc_id"), qa_art.select("qa_id", "dst_doc_id")])
    counts = {
        "n_articles": [int(drows[d]["n_articles_main"] or 0) + int(drows[d]["n_articles_appendix"] or 0) for d in ids],
        "basis_out": count_map(lb, "src_doc_id"),
        "basis_in": count_map(lb, "dst_doc_id"),
        "cite_out": count_map(ci, "src_doc_id", "dst_doc_id"),
        "cite_in": count_map(ci, "dst_doc_id", "src_doc_id"),
        "qa": count_map(qa_docs, "dst_doc_id", "qa_id"),
        "decisions": count_map(dp, "dst_doc_id", "decision_id"),
        "news": count_map(ne, "dst_doc_id", "news_id"),
    }

    # ------------------------------------------------------------------ change events and basis edges
    ch = T("changes", ["change_id", "acting_doc_id", "affected_doc_id", "kind", "effective_date", "evidence"])
    changes, evidence_by_affected = [], defaultdict(dict)
    skipped_changes = 0
    for cid, a_id, f_id, kind, eff, ev in ch.iter_rows():
        if a_id not in idx or f_id not in idx or kind not in kind_idx:
            skipped_changes += 1
            continue
        ci_ = len(changes)
        changes.append([idx[a_id], idx[f_id], kind_idx[kind], eff])
        if ev:
            evidence_by_affected[idx[f_id]][ci_] = nfc(ev)[:300]
    basis = []
    skipped_basis = 0
    method_names = ["parent-acts", "preamble-citation", "constitution-preamble"]
    method_idx = {m: i for i, m in enumerate(method_names)}
    for s, d, m in lb.iter_rows():
        if s in idx and d in idx:
            basis += [idx[s], idx[d], method_idx.get(m, -1)]
        else:
            skipped_basis += 1
    doc_links = {
        "version": net.get("version"), "documents": N,
        "note": "Indexes refer to the node order of legal_network.json. changes: [acting, affected, kind index, effective date]; "
                "basis: flat triples (citing, basis, method index); counts: per document; ids/numbers/titles/year/validity: per document "
                "(titles shortened as in legal_network.json).",
        "change_kinds": kinds, "basis_methods": method_names, "validity_names": list(net["validity"]),
        "ids": ids,
        "numbers": [nfc(n[F["number"]]) or "" for n in net["nodes"]],
        "titles": [nfc(n[F["title"]]) or "" for n in net["nodes"]],
        "year": [int(n[F["year"]]) if n[F["year"]] else -1 for n in net["nodes"]],
        "validity": [n[F["validity"]] if n[F["validity"]] is not None else -1 for n in net["nodes"]],
        "type": [n[F["type"]] if n[F["type"]] is not None else -1 for n in net["nodes"]],
        "changes": changes, "basis": basis, "counts": counts,
    }
    report["doc_links_bytes"] = dump(doc_links, a.out / "doc_links.json")
    report["changes"] = len(changes)
    report["changes_skipped"] = skipped_changes
    report["basis_edges"] = len(basis) // 3
    report["basis_skipped"] = skipped_basis

    # ------------------------------------------------------------------ per-document details (sharded)
    shards = []
    url_other = 0
    for s0 in range(0, N, SHARD):
        rows = []
        ev = {}
        for i in range(s0, min(N, s0 + SHARD)):
            r = drows[ids[i]]
            url = r["url"] or ""
            if url.startswith(URL_PREFIX):
                url = url[len(URL_PREFIX):]
            else:
                url_other += 1
                url = "=" + url  # full URL marker
            status = nfc(r["status_raw"]) if (r["status_code"] and r["status_code"] != "unknown") else None
            iss = [issuer_idx[c] for c in (r["issuer_ids"] or []) if c in issuer_idx]
            rows.append([r["issue_date"], r["effective_date"], r["expiry_date"], status, nfc(url), iss,
                         r["validity_evidence"], bool(r["status_text_conflict"]), nfc(r["title_vi"] or "")[:300]])
            if i in evidence_by_affected:
                for k, v in evidence_by_affected[i].items():
                    ev[str(k)] = v
        name = f"doc_details_{s0 // SHARD:02d}"
        obj = {"start": s0, "url_prefix": URL_PREFIX,
               "fields": ["issue_date", "effective_date", "expiry_date", "source_status", "url", "issuers", "validity_evidence",
                          "status_text_conflict", "title_vi"],
               "rows": rows, "evidence": ev}
        size = dump(obj, a.out / f"{name}.json")
        shards.append({"name": name, "start": s0, "count": len(rows), "bytes": size})
    report["detail_shards"] = shards
    report["urls_without_common_prefix"] = url_other

    # ------------------------------------------------------------------ dashboard columns + most cited
    col_type = [type_idx.get(drows[d]["doc_type_code"], -1) for d in ids]
    col_year = [int(drows[d]["year"]) if drows[d]["year"] is not None else -1 for d in ids]
    col_area = [area_idx.get(drows[d]["area_id"], -1) for d in ids]
    col_valid = [validity_idx.get(drows[d]["validity"], -1) for d in ids]
    col_rank = [int(drows[d]["legal_force_rank"]) for d in ids]
    col_iss = []
    extra_iss = []
    for i, d in enumerate(ids):
        lst = [issuer_idx[c] for c in (drows[d]["issuer_ids"] or []) if c in issuer_idx]
        col_iss.append(lst[0] if lst else -1)
        for j in lst[1:]:
            extra_iss += [i, j]
    ch_kind = [c[2] for c in changes]
    ch_year = []
    for c in changes:
        y = (c[3] or "")[:4]
        ch_year.append(int(y) if y.isdigit() else -1)
    ch_aff = [c[1] for c in changes]

    def top_docs(df, src_col):
        t = df.group_by("dst_doc_id").agg(pl.col(src_col).n_unique().alias("citing")).sort(["citing", "dst_doc_id"], descending=[True, False]).head(TOP_N)
        return [[idx[d], int(c)] for d, c in t.iter_rows() if d in idx]

    arts = T("articles", ["article_id", "article_no", "heading", "doc_id"])
    am = {r[0]: r for r in arts.iter_rows()}

    def top_arts(df, src_col):
        t = (df.filter(pl.col("dst_article_id").is_not_null()).group_by("dst_article_id")
             .agg(pl.col(src_col).n_unique().alias("citing")).sort(["citing", "dst_article_id"], descending=[True, False]).head(TOP_N))
        out = []
        for a_id, c in t.iter_rows():
            r = am.get(a_id)
            if not r or r[3] not in idx:
                continue
            out.append([idx[r[3]], a_id, r[1], nfc(r[2] or "")[:200], int(c)])
        return out

    ci_all = T("edges_citation", ["src_doc_id", "dst_doc_id", "dst_article_id"])
    top = {
        "documents": {
            "vbpl_citations": top_docs(ci_all.filter(pl.col("src_doc_id") != pl.col("dst_doc_id")), "src_doc_id"),
            "qa": top_docs(qa_docs, "qa_id"),
            "court_decisions": top_docs(dp, "decision_id"),
        },
        "articles": {
            "vbpl_citations": top_arts(ci_all, "src_doc_id"),
            "qa": top_arts(qa_art, "qa_id"),
            "court_decisions": top_arts(dp, "decision_id"),
        },
    }
    # consistency with the KG track's dashboard.json (top 50, same definitions)
    dash = json.loads((a.site_data / "dashboard.json").read_text(encoding="utf-8"))
    check = {}
    for src in ("vbpl_citations", "qa", "court_decisions"):
        ref = [(r["id"], r["citing"]) for r in dash["most_cited_documents"][src]]
        mine = [(ids[i], c) for i, c in top["documents"][src][:len(ref)]]
        check["documents_" + src] = {"n": len(ref), "same_counts": sorted(c for _, c in ref) == sorted(c for _, c in mine),
                                      "same_ids": sum(1 for x in mine if x in set(ref))}
        refa = [(r["id"], r["citing"]) for r in dash["most_cited_articles"][src]]
        minea = [(x[1], x[4]) for x in top["articles"][src][:len(refa)]]
        check["articles_" + src] = {"n": len(refa), "same_counts": sorted(c for _, c in refa) == sorted(c for _, c in minea),
                                     "same_ids": sum(1 for x in minea if x in set(refa))}
    report["most_cited_consistency"] = check
    labels = {}
    for grp in top.values():
        for lst in grp.values():
            for row in lst:
                i = row[0]
                n = net["nodes"][i]
                labels[str(i)] = [n[F["number"]], nfc(drows[ids[i]]["title_vi"]), ids[i]]
    dash_extra = {
        "version": net.get("version"),
        "note": "Columns are indexed like legal_network.json nodes; lookups (types, areas, issuers, validity) are those of legal_network.json. "
                "most_cited = number of distinct citing documents / Q&As / court decisions (same definition as dashboard.json, top 400).",
        "types": net["types"], "areas": net["areas"], "issuers": net["issuers"], "validity": net["validity"], "ranks": net["ranks"],
        "change_kinds": kinds,
        "docs": {"type": col_type, "year": col_year, "area": col_area, "issuer": col_iss, "validity": col_valid, "rank": col_rank,
                 "extra_issuers": extra_iss},
        "changes": {"kind": ch_kind, "year": ch_year, "affected": ch_aff},
        "most_cited": top, "doc_labels": labels,
    }
    report["dash_extra_bytes"] = dump(dash_extra, a.out / "dash_extra.json")
    (a.out / "derive_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False)[:3000])
    bad = [k for k, v in check.items() if not v["same_counts"]]
    if bad:
        print("WARNING most-cited lists differ from dashboard.json for", bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
