"""Build the per-area question traces (see trace_lib.py for the rules). Run inside a Python session:

    import build_traces as BT
    ctx = BT.load(R, HF)              # tables, citation outcomes and text matches for every linked Q&A
    sel = BT.select(ctx)              # 27 areas x 20 articles -> representative Q&A
    ...glosses (host.llm) -> ctx["gloss"]...
    out = BT.build_all(ctx, sel)      # {area_id: area json}
"""
import glob
import importlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

import polars as pl

import trace_lib as T
from trace_lib import C, V

HDPL_COLS = ["id", "url", "summary", "question", "answer", "category", "area", "published_date", "citations"]
MAX_NODES = 60
MAX_OTHER = 20
MAX_TERMS = 3


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ loading
def load(R, HF, TR, R_PREFIX):
    """R: rebuilt corpus root (post fix_docnums, as the KG); R_PREFIX: the same corpus with the 616 document-number fixes
    reverted, which is what the node's v1 gold resolver saw. The per-citation replay uses R_PREFIX + the v1
    explicit_mention (gold_v1.py) so that it reproduces gold_all.parquet; labels and document citations use R."""
    t0 = time.time()
    ctx = {"R": R, "HF": HF, "TR": TR}
    os.environ["R"] = R_PREFIX
    sys.path.insert(0, os.path.join(R_PREFIX, "code"))
    ER = importlib.import_module("eval_retrieval")
    G1 = importlib.import_module("gold_v1")
    ER.explicit_mention = G1.explicit_mention_v1
    ctx["ER"] = ER
    docs = pl.read_parquet(os.path.join(R, "data", "clean", "docs_clean.parquet"),
                           columns=["id", "doc_type", "doc_number", "doc_number_key", "doc_number_src", "title_vi", "title_core",
                                    "issue_date", "effective_date_meta", "status_raw", "status_code", "status_date", "url",
                                    "excluded_reason"]).filter(pl.col("excluded_reason").is_null())
    ctx["docs"] = {r["id"]: r for r in docs.to_dicts()}
    kg = os.path.join(TR, "kg")
    arts = pl.read_parquet(os.path.join(kg, "articles.parquet"))
    st = pl.read_parquet(os.path.join(kg, "structure.parquet"))
    ctx["arts"] = {r["article_id"]: r for r in arts.to_dicts()}
    ctx["struct"] = {r["struct_id"]: r for r in st.to_dicts()}
    abd = defaultdict(list)
    for r in arts.filter(pl.col("segment") == "main").select("article_id", "doc_id", "position").sort(["doc_id", "position"]).iter_rows(named=True):
        abd[r["doc_id"]].append(r["article_id"])
    ctx["arts_by_doc"] = abd
    ctx["main_art_set"] = set(arts.filter(pl.col("segment") == "main").select("doc_id", "article_no").iter_rows())
    e = pl.read_parquet(os.path.join(kg, "edges_qa_article.parquet"))
    q = pl.read_parquet(os.path.join(kg, "qas.parquet"), columns=["qa_id", "area_id", "published_date", "url"])
    e = e.join(q.select("qa_id", "area_id", "published_date"), on="qa_id", how="left")
    ctx["edges"] = e
    ctx["qas"] = q
    log("tables", e.height, "edges", f"{time.time()-t0:.0f}s")
    # hdpl rows of every Q&A that has an article edge (texts stay in memory only)
    ids = e["qa_id"].unique().to_list()
    fs = sorted(glob.glob(os.path.join(HF, "thuvienphapluat-vn-hdpl", "documents-*.parquet")))
    h = pl.scan_parquet(fs).select(HDPL_COLS).filter(pl.col("id").is_in(ids)).collect()
    ctx["hdpl"] = {r["id"]: r for r in h.to_dicts()}
    tn = pl.read_parquet(glob.glob(os.path.join(HF, "thuvienphapluat-vn-tnpl", "*.parquet"))[0],
                         columns=["term_id", "term_name_vi", "term_name_en", "term_name_source", "definition_vi", "area_name_vi",
                                  "status_vi", "source_url", "fetch_status"]).filter((pl.col("fetch_status") == "ok") & (pl.col("term_name_vi").str.len_chars() > 0))
    ctx["tnpl"] = {r["term_id"]: r for r in tn.to_dicts()}
    ctx["term_idx"] = T.build_term_index(ctx["tnpl"].values())
    log("hdpl", len(ctx["hdpl"]), "tnpl", len(ctx["tnpl"]), "term keys", len(ctx["term_idx"]), f"{time.time()-t0:.0f}s")
    # resolvers (same objects as stage_gold / build_qa)
    dd, by_key, by_name = ER.load_docs()
    ctx["d_by_id"] = {r["id"]: r for r in dd.to_dicts()}
    ctx["by_key"], ctx["by_name"] = by_key, by_name
    ch_idx = pl.read_parquet(os.path.join(R, "data", "chunks", "chunks.parquet"), columns=["doc_id", "article_no"])  # same file in both roots
    ctx["arts_set"] = set(zip(ch_idx["doc_id"].to_list(), ch_idx["article_no"].to_list()))
    del ch_idx
    from vlonto.resolve import DocResolver
    rows = []
    for r in ctx["docs"].values():
        issue = r["issue_date"]
        ny = re.search(r"/((?:19|20)\d{2})/", r["doc_number"] or "")
        if issue and ny and abs(int(issue[:4]) - int(ny.group(1))) > 1:
            issue = None
        rows.append({"doc_id": r["id"], "doc_type": r["doc_type"], "doc_number": r["doc_number"], "doc_number_key": r["doc_number_key"],
                     "title_core": r["title_core"], "issue_date": issue, "effective_date": r["effective_date_meta"]})
    ctx["doc_resolver"] = DocResolver(rows)
    # per-citation outcomes for every linked Q&A
    outc = {}
    for qid in ids:
        outc[qid] = T.citation_outcomes(ctx["hdpl"][qid], ER, ctx["d_by_id"], by_key, by_name, ctx["arts_set"], ctx["main_art_set"],
                                        ctx["doc_resolver"])
    ctx["outcomes"] = outc
    log("citation outcomes", sum(len(v) for v in outc.values()), f"{time.time()-t0:.0f}s")
    # article texts for every cited document (texts stay in memory only)
    need = set(e["dst_doc_id"].unique().to_list())
    for v in outc.values():
        for c in v:
            if c.get("doc_id"):
                need.add(c["doc_id"])
    ch = pl.scan_parquet(os.path.join(R, "data", "chunks", "chunks.parquet")).select(
        ["chunk_id", "doc_id", "article_no", "part", "text"]).filter(pl.col("doc_id").is_in(list(need))).collect()
    ctx["S"] = T.Structure(T.article_texts(ch))
    del ch
    log("article texts", len(ctx["S"].art_text), "docs", len(need), f"{time.time()-t0:.0f}s")
    # text match of every resolved provision citation
    match = {}
    for qid, v in outc.items():
        ag = T.AnswerGrams(ctx["hdpl"][qid]["answer"])
        for c in v:
            if c["kind"] != "provision" or c["status"] != "resolved":
                continue
            aid = f"{c['doc_id']}::dieu-{c['article_no']}"
            kind, uid, k, p, text, note = ctx["S"].resolve(aid, c["clause"], c["point"])
            m5 = T.containment(text, ag, 5)
            m4 = T.containment(text, ag, 4)
            c.update(aid=aid, unit_kind=kind, unit_id=uid, unit_clause=k, unit_point=p, unit_note=note,
                     match=None if m5 is None else round(m5, 4), match4=None if m4 is None else round(m4, 4))
            key = (qid, uid)
            if key not in match or (m5 or 0) > (match[key] or 0):
                match[key] = m5
    ctx["match"] = match
    log("matches", len(match), f"{time.time()-t0:.0f}s")
    return ctx


# ------------------------------------------------------------------ checks against the gold table
def check_outcomes_vs_gold(ctx, gold_path):
    g = pl.read_parquet(gold_path, columns=["qa_id", "gold_articles"])
    gold = {r["qa_id"]: set(r["gold_articles"]) for r in g.to_dicts()}
    same = diff = 0
    ex = []
    for qid, v in ctx["outcomes"].items():
        mine = set()
        for c in v:
            if c["kind"] == "provision" and c.get("doc_id") and c.get("reason") in (None, "appendix_or_unmatched_article"):
                mine.add(f"{c['doc_id']}::{(c['article'] or '').strip()}")
        if mine == gold.get(qid, set()):
            same += 1
        else:
            diff += 1
            if len(ex) < 5:
                ex.append((qid, sorted(mine), sorted(gold.get(qid, set()))))
    return {"qas_checked": same + diff, "same_article_set_as_gold": same, "different": diff, "examples": ex}


# ------------------------------------------------------------------ selection
def best_match_for_article(ctx, qid, aid):
    best, best_c = None, None
    for c in ctx["outcomes"][qid]:
        if c.get("aid") == aid and c["status"] == "resolved":
            if best is None or (c["match"] or 0) > (best or 0):
                best, best_c = c["match"], c
    return best, best_c


def select(ctx, n_top=20):
    e = ctx["edges"].filter(pl.col("area_id").is_not_null())
    n_all = dict(e.group_by("dst_article_id").agg(pl.col("qa_id").n_unique().alias("n")).iter_rows())
    per = e.group_by(["area_id", "dst_article_id", "dst_doc_id"]).agg(pl.col("qa_id").n_unique().alias("n"))
    issue = {d: (r["issue_date"] or "") for d, r in ctx["docs"].items()}
    sel = {}
    for area in sorted(per["area_id"].unique().to_list()):
        rows = per.filter(pl.col("area_id") == area).to_dicts()
        rows.sort(key=lambda r: (-r["n"], -n_all[r["dst_article_id"]], -_dnum(issue.get(r["dst_doc_id"])), r["dst_article_id"]))
        top = rows[:n_top]
        used = set()
        picks = []
        cand_by_art = defaultdict(list)
        for r in e.filter((pl.col("area_id") == area) & pl.col("dst_article_id").is_in([t["dst_article_id"] for t in top])).select(
                "qa_id", "dst_article_id", "published_date").unique().iter_rows(named=True):
            cand_by_art[r["dst_article_id"]].append(r)
        for rank, t in enumerate(top, 1):
            aid = t["dst_article_id"]
            cands = []
            for r in cand_by_art[aid]:
                qid = r["qa_id"]
                m, c = best_match_for_article(ctx, qid, aid)
                title = ctx["hdpl"][qid]["summary"] or ""
                names = T.person_name_hits(title)
                ver = m is not None and m >= T.VERIFY_AT
                cands.append({"qa_id": qid, "match": m, "verified": ver, "names": names, "pub": r["published_date"] or "",
                              "used": qid in used, "cit": c})
            cands.sort(key=lambda x: (bool(x["names"]), not x["verified"], x["used"], -_dnum(x["pub"]), -int(x["qa_id"])))
            best = cands[0]
            used.add(best["qa_id"])
            picks.append({"rank": rank, "article_id": aid, "doc_id": t["dst_doc_id"], "n_answers": t["n"], "n_answers_all": n_all[aid],
                          "qa_id": best["qa_id"], "match": best["match"], "verified": best["verified"], "n_candidates": len(cands),
                          "n_verified_candidates": sum(x["verified"] for x in cands), "reused_qa": best["used"],
                          "title_name_hits": best["names"]})
        sel[area] = picks
    return sel


def _dnum(d):
    """'2024-03-14...' -> 20240314; missing -> 0 (oldest)."""
    return int(d[:10].replace("-", "")) if d and re.match(r"^\d{4}-\d{2}-\d{2}", d) else 0


# ------------------------------------------------------------------ laws
NAMED = ("Bộ luật", "Luật", "Pháp lệnh", "Hiến pháp")


def law_year(r):
    m = re.search(r"/((?:19|20)\d{2})/", r["doc_number"] or "")
    if m:
        return int(m.group(1))
    return int(r["issue_date"][:4]) if r.get("issue_date") else None


def english_names(ctx, HF, doc_ids):
    """doc_id -> (English name, source) for codes, laws, ordinances, constitutions: the vbpl English record of the same
    number, else of another version of the same law (same type and title core), else None (machine-assisted later)."""
    fs = sorted(glob.glob(os.path.join(HF, "thuvienphapluat-vn-vbpl", "documents-*.parquet")))
    en = pl.scan_parquet(fs).filter(pl.col("is_english")).select(["id", "doc_type", "doc_number", "title"]).collect()
    by_key = {}
    for r in en.iter_rows(named=True):
        num = r["doc_number"] or ""
        m = re.match(r"^(\d{1,5}[a-zA-Z]?/\d{4}/[A-Za-zĐđ0-9]+(?:-[A-Za-zĐđ]*\d+)?)", num)
        if not m:
            continue
        k = V.docnum_key(m.group(1))
        by_key.setdefault(k, r)
    out = {}
    fam = defaultdict(list)
    for d, r in ctx["docs"].items():
        if r["doc_type"] in NAMED and r["title_core"]:
            fam[(r["doc_type"], V.name_key(r["title_core"]))].append(d)
    for d in doc_ids:
        r = ctx["docs"][d]
        if r["doc_type"] not in NAMED:
            continue
        rec = by_key.get(r["doc_number_key"]) if r["doc_number_key"] else None
        name = T.english_name_from_record(rec["title"], r["doc_type"]) if rec else None
        if name:
            out[d] = (name, f"vbpl English record {rec['id']}")
            continue
        for d2 in sorted(fam.get((r["doc_type"], V.name_key(r["title_core"] or "")), []), key=lambda x: ctx["docs"][x]["issue_date"] or "", reverse=True):
            r2 = ctx["docs"][d2]
            rec2 = by_key.get(r2["doc_number_key"]) if r2["doc_number_key"] else None
            name = T.english_name_from_record(rec2["title"], r2["doc_type"]) if rec2 else None
            if name:
                out[d] = (name, f"vbpl English record {rec2['id']} (version {r2['doc_number']})")
                break
    return out


def law_info(ctx, d):
    r = ctx["docs"][d]
    typ = r["doc_type"]
    type_en = C.DOC_TYPE_EN.get(typ, typ)
    num = r["doc_number"]
    year = law_year(r)
    title = BD.clean_title(r["title_vi"], typ, r["issue_date"]) if typ == "Hiến pháp" else r["title_vi"]
    en, en_src = ctx["law_en"].get(d, (None, None))
    if typ in NAMED:
        amend = bool(re.search(r"(?i)sửa đổi|bổ sung|bãi bỏ", title or ""))
        if title and len(title) <= 60 and not amend:
            core = re.sub(r"\s+(?:năm\s+)?(?:19|20)\d{2}$", "", title)
            short_vi = f"{core} {year}" if year else core
            short_en = f"{en} {year}" if en and year else (en or f"{type_en} {num or d}")
            base_vi, base_en = core, (en or f"{type_en} {num or d}")
        else:
            short_vi = f"{typ} {num}" if num else C.cut(title, 60)
            short_en = f"{type_en} {num}" if num else (en or f"{type_en} (vbpl {d})")
            base_vi, base_en = short_vi, short_en
    else:
        short_vi = f"{typ} {num}" if num else C.cut(title, 60)
        short_en = f"{type_en} {num}" if num else f"{type_en} (vbpl {d})"
        base_vi, base_en = short_vi, short_en
        en, en_src = short_en, "document type + number"
    status = r["status_raw"] if r["status_raw"] else None
    return {"doc_id": d, "number": num, "type_vi": typ, "type_en": type_en, "name_vi": C.cut(title, 200),
            "name_en": en or base_en, "name_en_source": en_src or "document type + number", "year": year, "url": r["url"],
            "status": C.cut(status, 80), "status_code": r["status_code"], "label_vi": short_vi, "label_en": short_en,
            "base_vi": base_vi, "base_en": base_en}


# ------------------------------------------------------------------ one trace
def fmt(m):
    return None if m is None else f"{m:.2f}"


def match_status(m):
    if m is None:
        return "no text to match"
    return ("validated · match " if m >= T.VERIFY_AT else "structural · match ") + fmt(m)


class Builder:
    def __init__(self, ctx, area, pick):
        self.ctx, self.area, self.pick = ctx, area, pick
        self.g = T.TraceGraph()
        self.lk = {}

    # -------------------------------------------------- primitives
    def L(self, s, t, kind):
        k = self.g.link(s, t, kind)
        self.lk[(s, t)] = k
        return k

    def work(self, d):
        info = law_info(self.ctx, d)
        wid = f"wk:{info['number']}" if info["number"] else f"wk:vbpl-{d}"
        if wid in self.g.nodes and self.g.nodes[wid]["provenance"].get("record") != d:
            wid = f"{wid}#{d}"
        r = self.ctx["docs"][d]
        self.g.node(wid, "work", info["label_vi"], info["label_en"], url=info["url"],
                    prov={"dataset": "vbpl", "record": d, "method": f"number from {r['doc_number_src'] or 'none'}",
                          "status": info["status"] or "no status in source"})
        self.workid[d] = wid
        return wid

    def record(self, d):
        info = law_info(self.ctx, d)
        rid = f"vbpl:{d}"
        self.g.node(rid, "record", f"{info['base_vi']} — bản tiếng Việt", f"{info['base_en']} — Vietnamese record", url=info["url"],
                    prov={"dataset": "vbpl", "record": d, "method": "source record", "status": info["status"] or "no status in source"})
        self.L(rid, self.work(d), "realizes")
        return rid

    def chain(self, aid):
        """Article node and its section/chapter parents up to the work. Returns [article, section?, chapter?, work]."""
        ctx = self.ctx
        a = ctx["arts"][aid]
        d = a["doc_id"]
        lv, le = T.unit_labels("article", aid)
        self.g.node(aid, "article", lv, le, prov={"dataset": "vbpl", "record": d, "method": "structure_parse", "status": "parsed"})
        seq = [aid]
        pid, pk = a["parent_id"], a["parent_kind"]
        while pk in ("Section", "Chapter", "Part", "Appendix"):
            s = ctx["struct"][pid]
            if pk in ("Section", "Chapter"):
                cls = "section" if pk == "Section" else "chapter"
                sv, se = T.struct_labels(pk, s["number"], s["heading"])
                self.g.node(pid, cls, sv, se, prov={"dataset": "vbpl", "record": d, "method": "structure_parse", "status": "parsed"})
                self.L(pid, seq[-1], "contains")
                seq.append(pid)
            pid, pk = s["parent_id"], s["parent_kind"]
        w = self.work(d)
        self.L(w, seq[-1], "contains")
        seq.append(w)
        return seq

    def unit_chain(self, kind, uid, aid, k, p):
        """[point?, clause?] + chain(article)."""
        art = self.chain(aid)
        d = self.ctx["arts"][aid]["doc_id"]
        if kind == "article":
            return art
        seq = []
        if k:
            cid = f"{aid}::khoan-{k}"
            lv, le = T.unit_labels("clause", aid, k)
            self.g.node(cid, "clause", lv, le, prov={"dataset": "vbpl", "record": d, "method": "structure_parse", "status": "parsed"})
            self.L(aid, cid, "contains")
            seq = [cid]
        if kind == "point":
            lv, le = T.unit_labels("point", aid, k, p)
            self.g.node(uid, "point", lv, le, prov={"dataset": "vbpl", "record": d, "method": "structure_parse", "status": "parsed"})
            self.L(seq[0] if seq else aid, uid, "contains")
            seq = [uid] + seq
        return seq + art

    # -------------------------------------------------- the trace
    def build(self):
        ctx, pick = self.ctx, self.pick
        self.workid = {}
        qid = pick["qa_id"]
        h = ctx["hdpl"][qid]
        pub = (h["published_date"] or "")[:10]
        q = self.g.node(f"q:{qid}", "question", f"Câu hỏi #{qid}", f"Question #{qid}", url=h["url"],
                        prov={"dataset": "hdpl", "record": qid, "method": "source record", "status": f"published {pub}"})
        a = self.g.node(f"a:{qid}", "answer", f"Trả lời #{qid}", f"Answer #{qid}", url=h["url"],
                        prov={"dataset": "hdpl", "record": qid, "method": "gold resolver (eval_retrieval.py gold)", "status": ""})
        self.L(a, q, "answers")
        av, ae = C.AREA_LABELS[self.area]
        n_area = ctx["area_counts"][self.area]
        ar = self.g.node(f"area:{self.area}", "area", av, ae,
                         prov={"dataset": "hdpl", "record": self.area, "method": "hdpl category", "status": f"{n_area:,} Q&As"})
        self.L(q, ar, "applies_to")
        primary_doc = pick["doc_id"]
        # ---- sources: resolved provision citations (one per unit) and document citations
        units = {}
        for c in ctx["outcomes"][qid]:
            if c["kind"] == "provision" and c["status"] == "resolved":
                u = units.get(c["unit_id"])
                if u is None or (c["match"] or 0) > (u["match"] or 0):
                    refs = (u["refs"] if u else [])
                    units[c["unit_id"]] = dict(c, refs=refs)
                if c["ref"] and c["ref"] not in units[c["unit_id"]]["refs"]:
                    units[c["unit_id"]]["refs"].append(c["ref"])
        if not any(u["aid"] == pick["article_id"] for u in units.values()):
            # the KG edge exists but the per-citation replay found no resolved citation for it (should not happen)
            e = ctx["edges"].filter((pl.col("qa_id") == qid) & (pl.col("dst_article_id") == pick["article_id"])).row(0, named=True)
            kind, uid, k, p, text, note = ctx["S"].resolve(pick["article_id"], e["clause"], e["point"])
            ag = T.AnswerGrams(h["answer"])
            m5, m4 = T.containment(text, ag, 5), T.containment(text, ag, 4)
            units[uid] = {"aid": pick["article_id"], "unit_id": uid, "unit_kind": kind, "unit_clause": k, "unit_point": p, "unit_note": note,
                          "match": m5, "match4": m4, "method": e["method_detail"], "refs": [e["ref"]] if e["ref"] else [], "doc_id": pick["doc_id"]}
        order = sorted(units.values(), key=lambda u: (u["aid"] != pick["article_id"], -(u["match"] or 0), u["unit_id"]))
        paths = []
        prim = None
        for u in order:
            seq = self.unit_chain(u["unit_kind"], u["unit_id"], u["aid"], u["unit_clause"], u["unit_point"])
            self.L(a, seq[0], "cites")
            m = u["match"]
            ver = m is not None and m >= T.VERIFY_AT
            n0 = self.g.nodes[seq[0]]
            n0["provenance"]["status"] = match_status(m)
            n0["provenance"]["method"] = "structure_parse" + (f" ({u['unit_note'].replace('_', ' ')})" if u["unit_note"] else "")
            p = {"nodes": [q, a] + seq, "verified": ver, "match": None if m is None else round(m, 2),
                 "match_4gram": None if u["match4"] is None else round(u["match4"], 2), "method": u["method"], "unit": u["unit_kind"],
                 "refs": u["refs"][:3], "primary": False}
            if u["unit_note"]:
                p["note"] = u["unit_note"]
            if prim is None and u["aid"] == pick["article_id"]:
                p["primary"] = True
                prim = p
            paths.append(p)
        drawn_docs = {self.ctx["arts"][u["aid"]]["doc_id"] for u in order}
        doc_cits = {}
        for c in ctx["outcomes"][qid]:
            if c["kind"] == "document" and c["status"] == "resolved" and c["doc_id"] not in drawn_docs:
                doc_cits.setdefault(c["doc_id"], c)
        for d, c in doc_cits.items():
            w = self.work(d)
            self.L(a, w, "cites")
            paths.append({"nodes": [q, a, w], "verified": False, "match": None, "match_4gram": None, "method": f"document citation ({c['method']})",
                          "unit": "work", "refs": [c["number"]] if c["number"] else [], "primary": False})
        self.record(primary_doc)
        # ---- highlight: verified paths dark, the ranked article's path always on the trace
        for p in paths:
            if p["verified"] or p["primary"]:
                self.g.mark_path(p["nodes"], p["verified"], self.lk)
        nver = sum(p["verified"] for p in paths)
        self.g.nodes[a]["provenance"]["status"] = f"{len(paths)} sources · {nver} verified"
        # ---- terms the question mentions, with their defining clause in the laws of the trace
        texts = [("title", h["summary"] or ""), ("question", h["question"] or "")]
        mentions = T.find_term_mentions(texts, ctx["term_idx"])
        docs_order = [primary_doc] + [d for d in dict.fromkeys(list(drawn_docs) + list(doc_cits)) if d != primary_doc]
        cands = []
        for key, src, pos in mentions[:15]:
            rows = ctx["term_idx"][key]
            name_raw = T.term_base(rows[0]["term_name_vi"])
            du = T.find_defining_unit(key, docs_order, ctx["arts_by_doc"], ctx["S"], name_raw)
            cands.append((key, src, pos, rows, du))
        def _qualified(r):
            return "(" in (r["term_name_vi"] or "")

        def _same_area(r):
            return C.slugify(r["area_name_vi"] or "") == self.area

        # a name whose every tnpl entry is scope-qualified ('Hồ sơ (trong hoạt động lưu trữ)') and from another area is
        # not the sense the question uses: keep it only when the laws of the trace define it
        cands = [x for x in cands if x[4] is not None or any(not _qualified(r) or _same_area(r) for r in x[3])]
        cands.sort(key=lambda x: (x[4] is None, x[1] != "title", -len(x[0]), x[2]))
        terms = []
        for key, src, pos, rows, du in cands[:T_MAX]:
            if du:
                kind, uid, aid, k, p, utext = du
                ug = T.AnswerGrams(utext)
                scored = [(T.containment(re.sub(r"^\s*là\s+", "", r["definition_vi"] or "", flags=re.I), ug, 5) or 0, r) for r in rows]
                best = max(scored, key=lambda x: (x[0], x[1]["status_vi"] == "Còn hiệu lực", -x[1]["term_id"]))
                trow, dm = best[1], best[0]
            else:
                trow = sorted(rows, key=lambda r: (_qualified(r), not _same_area(r), r["status_vi"] != "Còn hiệu lực", r["term_id"]))[0]
                dm = None
            tid = f"term:{trow['term_id']}"
            st = "no defining clause in the laws of this trace"
            if du:
                seq = self.unit_chain(du[0], du[1], du[2], du[3], du[4])
                unit_node = self.g.nodes[seq[0]]
                st = f"defined in {unit_node['label_en']} of {self.g.nodes[seq[-1]]['label_en']} · " + ("validated" if dm >= T.VERIFY_AT else "candidate") + f" · match {fmt(dm)}"
            self.g.node(tid, "term", trow["term_name_vi"], trow["term_name_en"], url=trow["source_url"],
                        prov={"dataset": "tnpl", "record": str(trow["term_id"]), "method": f"name in question {'title' if src == 'title' else 'text'}"
                              + (" · EN machine-translated in tnpl" if trow.get("term_name_source") == "mt" else ""), "status": st})
            self.L(q, tid, "mentions")
            if du:
                self.L(seq[0], tid, "defines")
                if unit_node["provenance"]["status"] == "parsed":
                    unit_node["provenance"]["method"] = "definitional pattern 'X là …'"
                    unit_node["provenance"]["status"] = ("validated" if dm >= T.VERIFY_AT else "candidate") + f" · match {fmt(dm)}"
            terms.append({"node": tid, "defined_by": seq[0] if du else None, "definition_match": None if dm is None else round(dm, 2)})
        # ---- other answers in the same area that cite the same law
        others = self.others(primary_doc, qid)
        # ---- callouts: the provision the answer quotes most closely, and one term
        # the provision the answer quotes most closely among the verified sources; without one, the ranked article's source
        best_p = max([p for p in paths if p["unit"] != "work" and p["verified"]], key=lambda p: ((p["match"] or 0), p["primary"]), default=prim)
        callouts = {"provision": best_p["nodes"][2] if best_p else None,
                    "term": next((t["node"] for t in terms if t["defined_by"]), terms[0]["node"] if terms else None)}
        unresolved = []
        for c in ctx["outcomes"][qid]:
            if c["status"] != "resolved":
                x = {k: c[k] for k in ("kind", "ref", "law_type", "law_name", "number", "article", "clause", "point") if c.get(k)}
                x["reason"] = c["reason"]
                unresolved.append(x)
        return {"paths": paths, "terms": terms, "others": others, "callouts": callouts, "unresolved": unresolved, "primary": prim}

    def others(self, d, rep_qid):
        """Up to MAX_OTHER other answers in the same area that cite the same law, spread over its articles like the
        comb of Fig. 1: up to FIRST_SAME on the ranked article, then one per article in turn (articles ordered: already
        in the graph, then most cited by these answers, then document order); inside an article verified citations
        first, then the most recent. Stops at MAX_OTHER answers or MAX_NODES nodes."""
        ctx = self.ctx
        e = ctx["edges_by_area_doc"].get((self.area, d), {})
        pos = {}
        cands = []
        for oq, aids in e.items():
            if oq == rep_qid:
                continue
            for aid in aids:
                pos[aid] = ctx["arts"][aid]["position"]
            cands.append(oq)
        art_freq = Counter(aid for oq in cands for aid in e[oq])
        ranked = self.pick["article_id"]
        groups = defaultdict(list)
        for oq in cands:
            aids = e[oq]
            if ranked in aids:
                tgt = ranked
            else:
                ing = [x for x in aids if x in self.g.nodes]
                tgt = min(ing or aids, key=lambda x: (-art_freq[x], pos[x]))
            m = best_match_for_article(ctx, oq, tgt)[0]
            pub = (ctx["hdpl"][oq]["published_date"] or "")[:10]
            groups[tgt].append({"qa_id": oq, "tgt": tgt, "m": m, "ver": (m or 0) >= T.VERIFY_AT, "pub": pub})
        for g in groups.values():
            g.sort(key=lambda r: (not r["ver"], -_dnum(r["pub"]), -int(r["qa_id"])))
        order = sorted(groups, key=lambda a: (a != ranked, a not in self.g.nodes, -len(groups[a]), pos[a]))
        queue = []
        if ranked in groups:
            queue += groups[ranked][:FIRST_SAME]
            groups[ranked] = groups[ranked][FIRST_SAME:]
        while any(groups[a] for a in order):
            for a in order:
                if groups[a]:
                    queue.append(groups[a].pop(0))
        out = []
        for r in queue:
            if len(out) >= MAX_OTHER:
                break
            tgt = r["tgt"]
            new = 1 + (0 if tgt in self.g.nodes else self._chain_cost(tgt))
            if len(self.g.nodes) + new > MAX_NODES:
                continue
            self.chain(tgt)
            oq = r["qa_id"]
            h = ctx["hdpl"][oq]
            title = (h["summary"] or "").strip()
            show = title if (title and len(title) <= SHORT_TITLE and not T.person_name_hits(title)) else None
            m = r["m"]
            nid = self.g.node(f"oq:{oq}", "other_question", show or f"Câu hỏi #{oq}", f"Question #{oq}", url=h["url"],
                              prov={"dataset": "hdpl", "record": oq, "method": "gold resolver",
                                    "status": match_status(m) + f" · {(h['published_date'] or '')[:10]}"})
            k = self.L(nid, tgt, "cites")
            if m is not None and m >= T.VERIFY_AT:
                self.g.links[k]["verified"] = True
            out.append({"node": nid, "article": tgt, "match": None if m is None else round(m, 2), "title_shown": bool(show)})
        return out

    def _chain_cost(self, aid):
        n = 0
        a = self.ctx["arts"][aid]
        if aid not in self.g.nodes:
            n += 1
        pid, pk = a["parent_id"], a["parent_kind"]
        while pk in ("Section", "Chapter", "Part", "Appendix"):
            if pk in ("Section", "Chapter") and pid not in self.g.nodes:
                n += 1
            s = self.ctx["struct"][pid]
            pid, pk = s["parent_id"], s["parent_kind"]
        return n


T_MAX = MAX_TERMS
SHORT_TITLE = 70
FIRST_SAME = 3


# ------------------------------------------------------------------ assembly
CLASSES = [("work", "Văn bản", "Work"), ("record", "Bản ghi", "Record"), ("chapter", "Chương", "Chapter"), ("section", "Mục", "Section"),
           ("article", "Điều", "Article"), ("clause", "Khoản", "Clause"), ("point", "Điểm", "Point"), ("term", "Thuật ngữ", "Term"),
           ("question", "Câu hỏi", "Question"), ("answer", "Trả lời", "Answer"), ("area", "Lĩnh vực", "Area"),
           ("other_question", "Câu hỏi khác", "Other question")]


def prepare(ctx):
    """Indexes used by Builder.others and the area table."""
    e = ctx["edges"]
    ebad = defaultdict(lambda: defaultdict(list))
    for r in e.select("area_id", "dst_doc_id", "qa_id", "dst_article_id").unique().sort(["qa_id", "dst_article_id"]).iter_rows(named=True):
        if r["area_id"]:
            lst = ebad[(r["area_id"], r["dst_doc_id"])][r["qa_id"]]
            if r["dst_article_id"] not in lst:
                lst.append(r["dst_article_id"])
    ctx["edges_by_area_doc"] = ebad
    ctx["area_counts"] = dict(ctx["qas"].group_by("area_id").len().iter_rows())
    ctx["area_linked"] = dict(e.group_by("area_id").agg(pl.col("qa_id").n_unique()).iter_rows())


def build_all(ctx, sel):
    out = {}
    for area, picks in sel.items():
        traces = []
        for pick in picks:
            b = Builder(ctx, area, pick)
            res = b.build()
            qid = pick["qa_id"]
            h = ctx["hdpl"][qid]
            gl = ctx["gloss"].get(qid, {})
            info = law_info(ctx, pick["doc_id"])
            title = (h["summary"] or "").strip()
            flags = []
            if T.person_name_hits(title) or gl.get("has_person_name"):
                flags.append("possible_person_name")
            nodes = [b.g.nodes[n] for n in b.g.order]
            links = list(b.g.links.values())
            av, ae = T.unit_labels("article", pick["article_id"])
            tr = {"rank": pick["rank"],
                  "article": {"node": pick["article_id"], "label_vi": av, "label_en": ae, "n_answers": pick["n_answers"],
                              "n_answers_all": pick["n_answers_all"]},
                  "qa": {"id": qid, "url": h["url"], "published_date": (h["published_date"] or "")[:10], "title_vi": title,
                         "title_en": gl.get("title_en"), **({"title_flags": flags} if flags else {})},
                  "law": {k: info[k] for k in ("doc_id", "number", "type_vi", "type_en", "name_vi", "name_en", "name_en_source", "year", "url",
                                               "status", "label_vi", "label_en")},
                  "verified": bool(res["primary"] and res["primary"]["verified"]),
                  "match": res["primary"]["match"] if res["primary"] else None,
                  "nodes": nodes, "links": links, "paths": res["paths"], "terms": res["terms"], "callouts": res["callouts"],
                  "unresolved_citations": res["unresolved"],
                  "counts": {"nodes": len(nodes), "links": len(links), "sources": len(res["paths"]),
                             "verified_sources": sum(p["verified"] for p in res["paths"]), "terms": len(res["terms"]),
                             "other_answers": len(res["others"]), "unresolved_citations": len(res["unresolved"])}}
            traces.append(tr)
        av, ae = C.AREA_LABELS[area]
        out[area] = {"area": {"id": area, "label_vi": av, "label_en": ae, "n_qas": ctx["area_counts"].get(area, 0),
                              "n_qas_with_links": ctx["area_linked"].get(area, 0), "n_traces": len(traces)},
                     "traces": traces}
    return out


GLOSS_TOOL = {"name": "gloss", "description": "English gloss of a Vietnamese legal Q&A title",
              "input_schema": {"type": "object", "properties": {
                  "gloss": {"type": "string", "description": "short natural English gloss, at most 15 words"},
                  "has_person_name": {"type": "boolean", "description": "true if the title names a person (private individual or public figure); place, organisation and law names do not count"}},
                  "required": ["gloss", "has_person_name"]}}


def gloss_prompt(title, max_words=15):
    return ("Vietnamese legal Q&A title (as published on thuvienphapluat.vn):\n" + title + "\n\n"
            f"Write a short, natural English gloss of this title in at most {max_words} words, for a figure caption. Keep it a question "
            "if the title is a question. Keep numbers, dates, amounts and document numbers (e.g. 45/2019/QH14, 05/KK-TNCN). Use plain "
            "words a reader outside Vietnam understands (e.g. 'red book' for Sổ đỏ is fine, 'social insurance', 'personal income tax'). "
            "Examples: 'Cách tính thời gian báo trước khi nghỉ việc của người lao động năm 2024? Báo trước 30 hay 45 ngày?' -> 'How to "
            "calculate the notice period for an employee's resignation in 2024? 30 or 45 days' notice?'; 'Đặt camera quay lén có phạm "
            "tội không?' -> 'Is installing a hidden camera a crime?'. Also report whether the title contains a person's name.")


LAW_TOOL = {"name": "law_name", "description": "English name of a Vietnamese law",
            "input_schema": {"type": "object", "properties": {"name_en": {"type": "string"}}, "required": ["name_en"]}}


def law_prompt(name_vi, typ):
    return ("Give the usual English name of this Vietnamese " + typ + ", without number or year, in the style 'Labor Code', "
            "'Civil Code', 'Criminal Code', 'Law on Land', 'Law on Social Insurance', 'Law on Personal Income Tax', 'Law on Marriage "
            "and Family', 'Ordinance on ...', 'Constitution':\n" + name_vi)


def word_count(s):
    return len((s or "").split())


def write_outputs(out_dir, index, areas):
    import json as _json
    os.makedirs(out_dir, exist_ok=True)
    sizes = {}
    for area, data in areas.items():
        p = os.path.join(out_dir, f"{area}.json")
        with open(p, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        sizes[p] = os.path.getsize(p)
    p = os.path.join(out_dir, "index.json")
    with open(p, "w", encoding="utf-8") as f:
        _json.dump(index, f, ensure_ascii=False, indent=1)
    sizes[p] = os.path.getsize(p)
    return sizes


# ------------------------------------------------------------------ compact output (as written)
def nfc_all(o):
    import unicodedata
    if isinstance(o, str):
        return unicodedata.normalize("NFC", o)
    if isinstance(o, list):
        return [nfc_all(x) for x in o]
    if isinstance(o, dict):
        return {nfc_all(k): nfc_all(v) for k, v in o.items()}
    return o


def compact(areas):
    """Booleans only when true, url only when known; other-question nodes carry no url (their hdpl id is in provenance)."""
    out = {}
    for a, d in areas.items():
        traces = []
        for t in d["traces"]:
            t2 = dict(t)
            nodes = []
            for n in t["nodes"]:
                m = {"id": n["id"], "cls": n["cls"], "label_vi": n["label_vi"], "label_en": n["label_en"]}
                if n["url"] and n["cls"] != "other_question":
                    m["url"] = n["url"]
                if n["on_trace"]:
                    m["on_trace"] = True
                if n["verified"]:
                    m["verified"] = True
                m["provenance"] = n["provenance"]
                nodes.append(m)
            links = []
            for l in t["links"]:
                m = {"s": l["s"], "t": l["t"], "kind": l["kind"]}
                if l["on_trace"]:
                    m["on_trace"] = True
                if l["verified"]:
                    m["verified"] = True
                links.append(m)
            t2["nodes"], t2["links"] = nodes, links
            traces.append(t2)
        out[a] = {"area": d["area"], "traces": traces}
    return out


def finalize(areas, term_en_fallback):
    """compact + English names for the few tnpl terms without one (machine-assisted, flagged) + NFC everywhere."""
    c = compact(areas)
    for d in c.values():
        for t in d["traces"]:
            for n in t["nodes"]:
                if n["cls"] == "term" and not n["label_en"]:
                    n["label_en"] = term_en_fallback[n["id"]]
                    n["provenance"]["method"] += " · EN machine-assisted (missing in tnpl)"
    return nfc_all(c)
