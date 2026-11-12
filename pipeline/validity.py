#!/usr/bin/env python3
"""Step 5 - Validity / supersession map.

Why: the agent must not present a repealed provision as current law and must
say which law replaced it and since when. Evidence sources:
 (a) the source 'status' field ('Hết hiệu lực: dd/mm/yyyy', 'Còn hiệu lực', ...)
 (b) citations.kind values - checked; none encodes replacement/amendment
     (kinds: external_mention, self, external, anaphora, parent_law[_mention])
 (c) regex over each newer in-scope document's operative text (preamble
     excluded): 'thay thế', 'hết hiệu lực', 'bãi bỏ', 'sửa đổi, bổ sung' + a
     document number in the same sentence.
Outputs ($R/data/validity/): validity.parquet (one row per in-scope document),
relations.parquet (old -> new with evidence), validity_report.json,
validity_sample.csv (30 relations for manual precision check).
"""
import os, sys, re, json, time, random
from multiprocessing import Pool
from pathlib import Path
from datetime import date
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vnlegal_text as V

R = Path(os.environ.get("R", "/path/to/vnlegal"))
OUT = R / "data" / "validity"; OUT.mkdir(parents=True, exist_ok=True)
TODAY = os.environ.get("AS_OF", "2026-11-08")
STATUS_FIRST = os.environ.get("STATUS_FIRST", "1") == "1"   # v7: curated 'Còn hiệu lực' status wins over a text-derived supersession

NUM = re.compile(r"(?<![\w/])(\d{1,5}[a-z]?/\d{4}/[A-ZĐ][A-ZĐa-z0-9]*(?:[-/][A-ZĐa-z0-9]+)*|\d{1,5}/[A-ZĐ][A-ZĐ0-9]*-[A-ZĐa-z0-9]+(?:-[A-ZĐa-z0-9]+)*|\d{1,5}-[A-ZĐ]{1,4}(?:/[A-ZĐ]+)*)(?![\w])")
KW = re.compile(r"(?i)(thay\s+thế|bãi\s+bỏ|sửa\s+đổi,?\s+bổ\s+sung|sửa\s+đổi|hết\s+hiệu\s+lực)")
STRUCT = re.compile(r"(?i)(\bđiều\s+\d+|\bcác\s+điều\b|\bmột\s+số\s+điều\b|\bkhoản\s+\d+|\bcác\s+khoản\b|\bđiểm\s+[a-zđ]\b|\bcụm\s+từ|\btừ\s+ngữ|\bphụ\s+lục|\bmẫu\s+số|\bbiểu\s+mẫu|\bbiểu\s+số|\bchương\s+[ivxlc\d]+\b|\bmục\s+\d+|\btên\s+gọi|\bdanh\s+mục|\bnội\s+dung|\bquy\s+định\s+tại|\bcác\s+quy\s+định|\bquy\s+định\s+tương\s+ứng|\bquy\s+định\s+về|\btại\s+(?:các\s+)?(?:Thông\s+tư|Nghị\s+định|Quyết\s+định|Luật|Bộ\s+luật|Nghị\s+quyết|Pháp\s+lệnh|văn\s+bản)|\bmột\s+số\s+(?:quy\s+định|điểm|khoản|chương|mục|nội\s+dung|phụ\s+lục|biểu\s+mẫu|mẫu))")
# a number that follows a description verb since the previous number is part of another document's description
DESC = re.compile(r"(?i)(hướng\s+dẫn|quy\s+định\s+chi\s+tiết|sửa\s+đổi,?\s+bổ\s+sung|thi\s+hành|thực\s+hiện|ban\s+hành\s+kèm|căn\s+cứ|theo\s+quy\s+định|được\s+sửa\s+đổi)")
# operative clause start: sentence start, list marker, 'Điều N.', or '... này' (this document)
CLAUSE_START = re.compile(r"(?i)(?:^|[\.:;]\s*|\d{1,3}[\.\)]\s*|[a-zđ]\)\s*|Điều\s+\d+[a-zđ]?\.\s*|\bnày\b[^.;]{0,200})$")
AMENDER_CUE = re.compile(r"(?i)(sửa\s+đổi,?\s+bổ\s+sung[^.;]{0,80}?(theo|bởi|tại)\s*$|(theo|bởi)\s+(?:Luật|Nghị\s+định|Thông\s+tư|Nghị\s+quyết|Quyết\s+định|Pháp\s+lệnh)(?:\s+số)?\s*$)")
PASSIVE_AMEND = re.compile(r"(?i)(?:được|đã\s+được)\s+sửa\s+đổi(?:,?\s+bổ\s+sung)?[^.;]{0,120}?\b(?:theo|bởi|tại)\b")
PARTIAL_SUBJ = re.compile(r"(?i)\b(điều|khoản|điểm|mục|chương|phần)\b[^.;]{0,160}\bcủa\s+(?:\S+\s+){0,8}?(?:số\s*)?$")
SENT = re.compile(r"(?<=[\.;])\s+|\n")

def classify(sent, m, own_key, prev_end=0, prev_desc=False):
    """Return (relation, evidence) for number match m in sentence, ("__desc__", None) when the
    number is part of another document's description, or None.
    prev_end = end offset of the previous document number in the sentence; prev_desc = the
    previous number was itself inside a description (v4: lists continue the description)."""
    num = V.norm_docnum(m.group(1)); key = V.docnum_key(num)
    if not key or key == own_key:
        return None
    before = sent[:m.start()]; after = sent[m.end():]
    kws = [k for k in KW.finditer(before) if not before[:k.start()].rstrip().endswith("(")]
    since_prev = before[max(prev_end, kws[-1].end() if kws else 0):]
    if DESC.search(since_prev):
        return ("__desc__", None)                            # number inside another document's description
    between = sent[prev_end:m.start()]
    dated = re.match(r"\s*,?\s*(?:ngày|ban\s+hành\s+ngày)\s+\d", after[:25])
    if prev_desc and not dated and len(between) < 160 and not KW.search(between) and not re.search(r"[.;:]", between):
        return ("__desc__", None)   # v4/v6: '... về việc lùi hiệu lực của BLHS số A, BLTTHS số B ... hết hiệu lực' - an undated item continues A's description
    if AMENDER_CUE.search(before[-120:]):
        return None                                          # '... được sửa đổi, bổ sung theo Luật số N' : N is an amender
    cue = list(PASSIVE_AMEND.finditer(before))
    if cue:
        tail = before[cue[-1].end():]
        if len(tail) < 400 and not KW.search(tail):
            return None                                      # N is one of a list of amenders of an earlier document
    if kws:
        k = kws[-1]; kw = k.group(1).lower(); gap = before[k.end():]
        if len(gap) <= 250 and not kw.startswith("hết") and CLAUSE_START.search(before[:k.start()]):
            if kw.startswith("thay"):
                if re.search(r"(?i)được\s*$", before[:k.start()][-12:]) or STRUCT.search(gap):
                    return ("amended", num)                  # phrase / annex replacement = partial amendment
                return ("replaced", num)
            if kw.startswith("bãi"):
                return ("partially_repealed", num) if STRUCT.search(gap) else ("repealed", num)
            if kw.startswith("sửa"):
                if NUM.search(before[:k.start()][-60:]):
                    return None                              # '<other doc> sửa đổi, bổ sung ... <num>': other doc is the amender
                return ("amended", num)
    m2 = re.match(r"(?i)^[^;]{0,450}?hết\s+hiệu\s+lực", after)
    if m2:
        mid = after[:m2.end()]
        if re.search(r"(?i)một\s+phần", mid) or re.match(r"(?i)^\s*(?:,|và)?\s*(?:Điều|khoản|điểm)", after) :
            return ("partially_expired", num)
        # a provision-level subject before the number ('Điều 5 của Thông tư số N hết hiệu lực') = partial
        if re.search(r"(?i)\b(điều|khoản|điểm)\s+\w+\s+(?:của\s+)?(?:\w+\s+){0,4}(?:số\s*)?$", before[-80:]) or PARTIAL_SUBJ.search(before[-240:]):
            return ("partially_expired", num)
        # v7: structural subject anywhere in the clause ('Các Điều 6, 11 và 12 Nghị định số N', 'Chương II Nghị định số N', 'Nội dung ... quy định tại ...')
        cut = max(before.rfind(ch) for ch in ".;:\n")
        subj = before[cut + 1:][-250:]
        subj = re.split(r"(?:^|\s)(?:\d{1,2}|[a-zđ])[\.\)]\s", subj)[-1]
        if STRUCT.search(subj):
            return ("partially_expired", num)
        return ("replaced", num)
    return None

def scan_doc(d):
    text = d["text"]; pos = d["first_article_pos"]
    if pos is None or pos < 0:
        cc = [m.end() for m in re.finditer(r"(?m)^(?:Căn\s+cứ|Theo\s+đề\s+nghị|Xét\s).*$", text)]
        pos = cc[-1] if cc else 0
    body = text[pos:]
    own = d["doc_number_key"]; rels = []
    for sent in SENT.split(body):
        if len(sent) < 15 or not KW.search(sent) or not NUM.search(sent):
            continue
        prev_end = 0; prev_desc = False
        for m in NUM.finditer(sent):
            r = classify(sent, m, own, prev_end, prev_desc)
            prev_end = m.end()
            prev_desc = bool(r) and r[0] == "__desc__"
            if r and r[0] == "__desc__":
                r = None
            if r:
                s0 = max(0, m.start() - 160); s1 = min(len(sent), m.end() + 160)
                md = re.match(r"\s*,?\s*ngày\s+(\d{1,2})\s*(?:/|-|tháng)\s*(\d{1,2})\s*(?:/|-|năm)\s*(\d{4})", sent[m.end():m.end() + 60])
                rels.append({"new_id": d["id"], "relation": r[0], "old_number": r[1], "old_key": V.docnum_key(r[1]),
                             "old_date_mentioned": V.mkdate(*md.groups()) if md else None,
                             "evidence": sent[s0:s1].strip()})
    seen = set(); out = []
    for r in rels:
        k = (r["old_key"], r["relation"])
        if k not in seen:
            seen.add(k); out.append(r)
    return out

def main():
    t0 = time.time()
    docs = pl.read_parquet(R / "data" / "clean" / "docs_clean.parquet",
                           columns=["id", "doc_type", "doc_number", "doc_number_key", "title_vi", "issue_date",
                                    "effective_date_meta", "status_raw", "status_code", "status_date", "tier", "text"])
    st = pl.read_parquet(R / "data" / "chunks" / "doc_struct.parquet", columns=["id", "first_article_pos", "eff_text_date", "eff_text_src"])
    docs = docs.join(st, on="id", how="left")
    # best effective date: metadata (site, reflects later changes) > text of the effect article > issue date
    docs = docs.with_columns(
        pl.coalesce(["effective_date_meta", "eff_text_date"]).alias("effective_date"),
        pl.when(pl.col("effective_date_meta").is_not_null()).then(pl.lit("metadata"))
          .when(pl.col("eff_text_date").is_not_null()).then(pl.concat_str([pl.lit("text:"), pl.col("eff_text_src")]))
          .otherwise(pl.lit(None)).alias("effective_date_src"))
    rows = docs.select(["id", "doc_number_key", "text", "first_article_pos"]).to_dicts()
    with Pool(int(os.environ.get("NPROC", "200"))) as p:
        res = p.map(scan_doc, rows, chunksize=64)
    rel = pl.DataFrame([r for rs in res for r in rs], infer_schema_length=None)
    print("raw relations", rel.height, f"{time.time()-t0:.0f}s", flush=True)
    meta = docs.select(["id", "doc_number", "doc_number_key", "doc_type", "title_vi", "issue_date", "effective_date"])
    # resolve old_key -> in-scope doc(s); keep only targets issued no later than the new doc
    new = meta.rename({c: "new_" + c for c in meta.columns if c != "id"}).rename({"id": "new_id"})
    old = meta.rename({c: "old_" + c for c in meta.columns if c != "id"}).rename({"id": "old_id", "old_doc_number_key": "old_key"})
    rel = rel.join(new, on="new_id", how="left").join(old, on="old_key", how="left")
    rep = {"raw_relations": rel.height, "raw_by_relation": rel.group_by("relation").len().sort("len", descending=True).rows()}
    rel = rel.with_columns(pl.col("old_id").is_not_null().alias("resolved"))
    rep["resolved_to_in_scope_doc"] = int(rel["resolved"].sum())
    rel = rel.filter(pl.col("resolved"))
    rel = rel.filter(pl.col("old_issue_date").is_null() | pl.col("new_issue_date").is_null() | (pl.col("old_issue_date") <= pl.col("new_issue_date")))
    rel = rel.filter(pl.col("old_id") != pl.col("new_id"))
    # year-less numbers ('29/TT-LB', '01/BYT-TT') are not unique: require the date stated next to the
    # number to equal the candidate's issue date; with a year-format number a stated date must match the year
    nyear = ~pl.col("old_number").str.contains(r"^\d{1,5}[a-zA-Z]?/\d{4}/")
    rep["dropped_yearless_unverified"] = int(rel.filter(nyear & ~(pl.col("old_date_mentioned").is_not_null() & (pl.col("old_date_mentioned") == pl.col("old_issue_date")))).height)
    rel = rel.filter(~nyear | (pl.col("old_date_mentioned").is_not_null() & (pl.col("old_date_mentioned") == pl.col("old_issue_date"))))
    rel = rel.filter(pl.col("old_date_mentioned").is_null() | pl.col("old_issue_date").is_null() |
                     (pl.col("old_date_mentioned").str.slice(0, 4) == pl.col("old_issue_date").str.slice(0, 4)))
    # ambiguous no-year numbers resolving to several docs: keep the latest one issued before the new doc
    rel = rel.sort(["new_id", "old_key", "relation", "old_issue_date"], descending=[False, False, False, True]).unique(subset=["new_id", "old_key", "relation"], keep="first")
    rep["relations_kept"] = rel.height
    rep["kept_by_relation"] = rel.group_by("relation").len().sort("len", descending=True).rows()
    # v5/v6 (C): legal hierarchy - an act cannot replace, repeal or amend an act of higher legal force
    def _rank(t, num):
        code = (num or "").split("/")[-1].upper()
        if t == "Hiến pháp": return 0
        if t in ("Bộ luật", "Luật"): return 1
        if t == "Nghị quyết": return 2 if "UBTVQH" in code else (1 if re.search(r"(^|-)QH\d*$", code) else 3)
        if t == "Pháp lệnh": return 2
        if t in ("Nghị định", "Nghị quyết liên tịch"): return 3
        if t == "Quyết định": return 4 if "TTG" in code else 5
        if t in ("Thông tư", "Thông tư liên tịch"): return 5
        return 9
    rk = rel.select(["new_doc_type", "new_doc_number", "old_doc_type", "old_doc_number"]).to_dicts()
    ok = [not (_rank(r["new_doc_type"], r["new_doc_number"]) > _rank(r["old_doc_type"], r["old_doc_number"])) for r in rk]
    rel = rel.with_columns(pl.Series("hierarchy_ok", ok))
    strong = pl.col("relation").is_in(["replaced", "repealed", "partially_repealed", "partially_expired", "amended"])   # v6: all kinds
    rep["dropped_hierarchy_violation"] = int(rel.filter(strong & ~pl.col("hierarchy_ok")).height)
    rep["dropped_hierarchy_examples"] = rel.filter(strong & ~pl.col("hierarchy_ok")).select(["relation", "old_doc_number", "old_doc_type", "new_doc_number", "new_doc_type"]).head(8).to_dicts()
    rel = rel.filter(~strong | pl.col("hierarchy_ok")).drop("hierarchy_ok")
    rep["relations_kept"] = rel.height
    rep["kept_by_relation"] = rel.group_by("relation").len().sort("len", descending=True).rows()
    # deterministic row order (VLOnto 1.0.0): polars unique()/join do not keep row order, so without this sort the same
    # relations came out in a different order on every run (change ids of repeated relations and samples then varied)
    rel = rel.sort(["new_id", "relation", "old_key", "old_id", "old_number", "evidence"], nulls_last=True)
    rel.write_parquet(OUT / "relations.parquet")
    # ---- per-document validity
    # display label for the acting document; a few acts have no parsed number -> 'doc_id:<id>'
    rel = rel.with_columns(pl.coalesce(pl.col("new_doc_number"), pl.lit("doc_id:") + pl.col("new_id").cast(pl.Utf8)).alias("new_doc_number"))
    full = rel.filter(pl.col("relation").is_in(["replaced", "repealed"]))
    sup = full.group_by("old_id").agg(
        pl.col("new_doc_number").alias("superseded_by"), pl.col("new_id").alias("superseded_by_ids"),
        pl.col("new_effective_date").min().alias("superseded_from"), pl.col("relation").first().alias("supersession_kind"),
        pl.col("evidence").first().alias("supersession_evidence"))
    amd = rel.filter(~pl.col("relation").is_in(["replaced", "repealed"])).group_by("old_id").agg(
        pl.col("new_doc_number").unique(maintain_order=True).alias("amended_by"), pl.col("new_id").unique(maintain_order=True).alias("amended_by_ids"),
        pl.col("relation").unique(maintain_order=True).alias("amendment_kinds"), pl.col("evidence").first().alias("amendment_evidence"))
    v = docs.drop(["text", "first_article_pos"]).join(sup.rename({"old_id": "id"}), on="id", how="left").join(amd.rename({"old_id": "id"}), on="id", how="left")
    T = TODAY
    # v4/v5: the curated source status 'Còn hiệu lực' (in force) / 'Còn hiệu lực đến <future date>' wins over a
    # text-derived supersession; the conflict is kept as a flag so the agent can ask the user to verify.
    status_in_force = (pl.col("status_code") == "in_force") | ((pl.col("status_code") == "in_force_until") & (pl.col("status_date") > T))
    sup_due = pl.col("superseded_from").is_not_null() & (pl.col("superseded_from") <= T)
    v = v.with_columns((status_in_force & sup_due).fill_null(False).alias("status_text_conflict"))
    v = v.with_columns(
        pl.when((pl.col("status_code") == "expired") & (pl.col("status_date").is_null() | (pl.col("status_date") <= T))).then(pl.lit("expired"))
          .when(sup_due & (pl.lit(not STATUS_FIRST) | ~status_in_force.fill_null(False))).then(pl.lit("superseded"))   # v7: source status 'in force' wins (STATUS_FIRST=1)
          .when((pl.col("status_code") == "not_yet_effective") | (pl.col("effective_date") > T)).then(pl.lit("not_yet_effective"))
          .when(pl.col("status_code") == "in_force_until").then(pl.when(pl.col("status_date") > T).then(pl.lit("in_force")).otherwise(pl.lit("expired")))
          .when(pl.col("status_code") == "partially_expired").then(pl.lit("partially_expired"))
          .when(pl.col("status_code") == "in_force").then(pl.when(pl.col("amended_by").is_not_null()).then(pl.lit("in_force_amended")).otherwise(pl.lit("in_force")))
          .when(pl.col("amended_by").is_not_null() & (pl.col("effective_date").is_null() | (pl.col("effective_date") <= T))).then(pl.lit("presumed_in_force_amended"))
          .when(pl.col("amended_by").is_not_null()).then(pl.lit("amended_status_unknown"))
          .when(pl.col("status_code") == "not_applicable").then(pl.lit("not_applicable"))
          .otherwise(pl.lit("unknown")).alias("validity"),
    )
    v = v.with_columns(
        pl.when(pl.col("validity").is_in(["expired", "superseded", "not_applicable"])).then(pl.lit(False))
          .when(pl.col("validity") == "not_yet_effective").then(pl.lit(False))
          .when(pl.col("validity").is_in(["in_force", "in_force_amended", "partially_expired", "presumed_in_force_amended"])).then(pl.lit(True))
          .otherwise(pl.lit(None, dtype=pl.Boolean)).alias("in_force"),
        pl.when(pl.col("status_code") == "expired").then(pl.col("status_date"))
          .when(pl.col("superseded_from").is_not_null() & (pl.lit(not STATUS_FIRST) | ~pl.col("status_text_conflict"))).then(pl.col("superseded_from")).otherwise(pl.lit(None)).alias("expiry_date"),
        pl.when(pl.col("status_code").is_not_null() & pl.col("superseded_by").is_not_null()).then(pl.lit("status+text"))
          .when(pl.col("status_code").is_not_null()).then(pl.lit("status"))
          .when(pl.col("superseded_by").is_not_null() | pl.col("amended_by").is_not_null()).then(pl.lit("text")).otherwise(pl.lit("none")).alias("evidence_source"),
        pl.lit(T).alias("as_of"))
    v = v.sort("id")
    v.write_parquet(OUT / "validity.parquet")
    rep["validity_counts"] = v.group_by("validity").len().sort("len", descending=True).rows()
    rep["in_force_counts"] = v.group_by("in_force").len().rows()
    rep["evidence_source_counts"] = v.group_by("evidence_source").len().sort("len", descending=True).rows()
    rep["docs_with_superseded_by"] = int(v["superseded_by"].is_not_null().sum())
    rep["status_in_force_but_text_superseded"] = int(v["status_text_conflict"].sum())
    rep["conflict_examples"] = v.filter(pl.col("status_text_conflict")).select(["doc_number", "title_vi", "status_raw", "superseded_by", "superseded_from"]).head(12).to_dicts()
    (v.filter(pl.col("status_text_conflict")).select(["id", "doc_number", "doc_type", "title_vi", "status_raw", pl.col("superseded_by").list.join(", "), "superseded_from", "supersession_kind", "supersession_evidence"])
       .write_csv(OUT / "status_text_conflicts.csv"))
    rep["docs_with_amended_by"] = int(v["amended_by"].is_not_null().sum())
    # agreement between (a) status 'expired' and (c) text supersession
    both = v.filter(pl.col("status_code").is_not_null() & pl.col("superseded_by").is_not_null())
    rep["status_vs_text"] = {"docs_with_status_and_text_relation": both.height,
                             "status_expired": int((both["status_code"] == "expired").sum()),
                             "status_expired_same_date": int(((both["status_code"] == "expired") & (both["status_date"] == both["superseded_from"])).sum())}
    exp = v.filter(pl.col("status_code") == "expired")
    rep["status_expired_docs"] = exp.height
    rep["status_expired_docs_with_text_supersession"] = int(exp["superseded_by"].is_not_null().sum())
    # known cases
    kc = {}
    for old_n, new_n, eff in [("10/2012/QH13", "45/2019/QH14", "2021-01-01"), ("45/2013/QH13", "31/2024/QH15", "2024-08-01"), ("58/2014/QH13", "41/2024/QH15", "2025-07-01")]:
        o = v.filter(pl.col("doc_number") == old_n).select(["id", "doc_number", "title_vi", "status_raw", "validity", "in_force", "expiry_date",
                                                            "superseded_by", "superseded_from", "supersession_evidence", "amended_by"]).to_dicts()
        n = v.filter(pl.col("doc_number") == new_n).select(["id", "doc_number", "effective_date", "effective_date_src", "eff_text_date", "validity", "in_force"]).to_dicts()
        kc[old_n] = {"expected_new": new_n, "expected_effective": eff, "old": o, "new": n,
                     "pass": bool(o and n and new_n in (o[0]["superseded_by"] or []) and n[0]["effective_date"] == eff and o[0]["in_force"] is False)}
    rep["known_cases"] = kc
    # 30 relations for manual precision check: 15 replaced/repealed, 10 amended, 5 partial
    random.seed(13)
    parts = []
    for rels_, k in [(["replaced", "repealed"], 15), (["amended"], 10), (["partially_repealed", "partially_expired"], 5)]:
        pool = rel.filter(pl.col("relation").is_in(rels_))
        parts.append(pool.sample(min(k, pool.height), seed=int(os.environ.get('SAMPLE_SEED', '13'))))
    samp = pl.concat(parts).select(["relation", "old_doc_number", "old_title_vi", "new_doc_number", "new_title_vi", "new_effective_date", "evidence"])
    samp.write_csv(OUT / "validity_sample_unlabelled.csv")
    rep["wall_s"] = round(time.time() - t0, 1)
    json.dump(rep, open(OUT / "validity_report.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: rep[k] for k in rep if k != "known_cases"}, ensure_ascii=False, default=str)[:3000])
    for k, x in kc.items():
        print(k, "PASS" if x["pass"] else "FAIL", x["old"][:1], x["new"][:1])

if __name__ == "__main__":
    main()
