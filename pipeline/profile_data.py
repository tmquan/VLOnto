#!/usr/bin/env python3
"""Step 2 - Profiling: measure what the raw data actually contains before
deciding how to clean it (schema, null coverage, type/tier mix, statuses,
dates, text length, citation kinds, duplicates, Unicode problems, boilerplate).

Output: $R/data/profile/profile.json (+ printed summary). Read-only step.
"""
import json, os, re, sys, time, glob, hashlib, unicodedata, random
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
import polars as pl
import pyarrow.parquet as pq

R = Path(os.environ.get("R", "/path/to/vnlegal"))
MAN = json.load(open(R / "data" / "download_manifest.json"))
OUT = R / "data" / "profile"; OUT.mkdir(parents=True, exist_ok=True)
NPROC = int(os.environ.get("NPROC", "200"))

def files(repo):
    d = MAN["datasets"][repo]["local_dir"]
    return sorted(glob.glob(os.path.join(d, "documents*.parquet")))

def schema_of(fs):
    s = pq.read_schema(fs[0])
    return {n: str(t) for n, t in zip(s.names, s.types)}

def coverage(df):
    out = {}
    n = df.height
    for c, dt in df.schema.items():
        col = df[c]
        if dt == pl.Utf8:
            nn = int((col.is_not_null() & (col.str.strip_chars().str.len_chars() > 0)).sum())
        elif isinstance(dt, pl.List):
            nn = int((col.is_not_null() & (col.list.len() > 0)).sum())
        else:
            nn = int(col.is_not_null().sum())
        out[c] = {"non_empty": nn, "pct": round(100 * nn / max(n, 1), 2)}
    return out

def vc(series, k=40):
    v = series.value_counts(sort=True).head(k)
    name = series.name
    return [[None if r[0] is None else str(r[0]), int(r[1])] for r in v.iter_rows()]

# ---------------- text checks (multiprocessing) ----------------
MOJI = re.compile(r"Ã[\x80-\xbf]|Ä‘|Æ°|áº|á»")
ZW = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
OLD_TONE = re.compile(r"(?i)\b\w*(?:oà|oá|oả|oã|oạ|oè|oé|oẻ|oẽ|oẹ|uỳ|uý|uỷ|uỹ|uỵ)\b")
NEW_TONE = re.compile(r"(?i)\b\w*(?:òa|óa|ỏa|õa|ọa|òe|óe|ỏe|õe|ọe|ùy|úy|ủy|ũy|ụy)\b")

def text_stats(args):
    texts, sample_lines = args
    c = Counter()
    lines = Counter()
    hashes = []
    for t in texts:
        if t is None or len(t) == 0:
            c["empty"] += 1; hashes.append(None); continue
        if not unicodedata.is_normalized("NFC", t): c["not_nfc"] += 1
        if "\ufffd" in t: c["replacement_char"] += 1
        if ZW.search(t): c["zero_width"] += 1
        if "\u00a0" in t: c["nbsp"] += 1
        if "\u00ad" in t: c["soft_hyphen"] += 1
        if CTRL.search(t): c["control_chars"] += 1
        if MOJI.search(t): c["mojibake_like"] += 1
        if OLD_TONE.search(t): c["old_style_tone"] += 1
        if NEW_TONE.search(t): c["new_style_tone"] += 1
        if re.search(r"[\u0300-\u036f]", t): c["combining_marks"] += 1
        hashes.append(hashlib.md5(" ".join(unicodedata.normalize("NFC", t).split()).encode()).hexdigest())
        if sample_lines:
            seen = set()
            for ln in t.split("\n"):
                s = " ".join(ln.strip().strip("*#_|>").split())
                if 3 <= len(s) <= 160 and s not in seen:
                    seen.add(s); lines[s] += 1
    return c, lines, hashes

def run_text_checks(texts, sample_idx):
    n = len(texts); B = 2000
    jobs = []
    for i in range(0, n, B):
        jobs.append((texts[i:i+B], (i // B) in sample_idx))
    tot, lines, hashes = Counter(), Counter(), []
    with Pool(NPROC) as p:
        for c, l, h in p.imap(text_stats, jobs, chunksize=1):
            tot.update(c); lines.update(l); hashes.extend(h)
    return tot, lines, hashes

def main():
    t0 = time.time()
    prof = {}
    # ---------------- vbpl ----------------
    repo = "tmquan/thuvienphapluat-vn-vbpl"
    fs = files(repo)
    prof["vbpl_schema"] = schema_of(fs)
    df = pl.read_parquet(fs)
    n = df.height
    print("vbpl rows", n, "cols", df.width, f"{time.time()-t0:.0f}s", flush=True)
    noncit = df.drop(["citations"]) if "citations" in df.columns else df
    prof["vbpl_rows"] = n
    prof["vbpl_coverage"] = coverage(df)
    prof["vbpl_tier"] = vc(df["tier"])
    prof["vbpl_tier_name"] = vc(df["tier_name"])
    prof["vbpl_doc_type_top60"] = vc(df["doc_type"], 60)
    prof["vbpl_doc_type_by_tier"] = {}
    for t in [0, 1, 2, 3]:
        prof["vbpl_doc_type_by_tier"][str(t)] = vc(df.filter(pl.col("tier") == t)["doc_type"], 40)
    prof["vbpl_issuer_kind"] = vc(df["issuer_kind"], 30)
    prof["vbpl_issuer_tier01_top40"] = vc(df.filter(pl.col("tier") <= 1)["issuer"], 40)
    prof["vbpl_status"] = vc(df["status"], 40)
    prof["vbpl_section"] = vc(df["section"], 20)
    prof["vbpl_legal_area_top40"] = vc(df["legal_area"], 40)
    prof["vbpl_is_english"] = vc(df["is_english"]); prof["vbpl_has_english"] = vc(df["has_english"])
    # date formats
    def fmt_counts(col):
        s = df[col].drop_nulls()
        pat = s.str.replace_all(r"\d", "9")
        return vc(pat, 15)
    for col in ["issue_date", "effective_date", "update_date"]:
        prof[f"vbpl_{col}_formats"] = fmt_counts(col)
        prof[f"vbpl_{col}_examples"] = df[col].drop_nulls().head(5).to_list()
    prof["vbpl_year_hist"] = vc(df["year"].cast(pl.Int64), 90)
    # text lengths
    q = df.select(pl.col("vn_chars")).to_series()
    prof["vbpl_vn_chars_quantiles"] = {str(p): float(q.quantile(p)) for p in [0, .01, .05, .1, .25, .5, .75, .9, .95, .99, .999, 1]}
    prof["vbpl_vn_chars_by_tier_median"] = {str(r[0]): float(r[1]) for r in df.group_by("tier").agg(pl.col("vn_chars").median()).iter_rows()}
    prof["vbpl_num_articles_quantiles_tier01"] = {str(p): float(df.filter(pl.col("tier") <= 1)["num_articles"].quantile(p)) for p in [.1, .25, .5, .75, .9, .99]}
    prof["vbpl_num_articles_sum_by_tier"] = {str(r[0]): int(r[1]) for r in df.group_by("tier").agg(pl.col("num_articles").sum()).iter_rows()}
    # citations
    cit = df.select([pl.col("id").alias("_doc_id"), "citations"]).explode("citations").unnest("citations")
    prof["vbpl_citation_fields"] = cit.columns
    prof["vbpl_citations_total"] = int(cit["kind"].is_not_null().sum())
    prof["vbpl_citations_kind"] = vc(cit["kind"], 40)
    if "source" in cit.columns: prof["vbpl_citations_source"] = vc(cit["source"], 20)
    ex = {}
    for k in [r[0] for r in prof["vbpl_citations_kind"][:15]]:
        if k is None: continue
        ex[k] = cit.filter(pl.col("kind") == k).head(3).to_dicts()
    prof["vbpl_citations_examples_by_kind"] = ex
    del cit
    # parent_acts / article_titles sample
    prof["vbpl_parent_acts_example"] = df.filter(pl.col("parent_acts").list.len() > 0).head(3).select(["id", "title", "parent_acts"]).to_dicts()
    # duplicates (metadata)
    prof["vbpl_dup_id"] = int(n - df["id"].n_unique())
    dn = df.filter(pl.col("doc_number").is_not_null())
    g = dn.group_by("doc_number").len().filter(pl.col("len") > 1)
    prof["vbpl_doc_number_dup_groups"] = int(g.height); prof["vbpl_doc_number_dup_rows"] = int(g["len"].sum())
    prof["vbpl_doc_number_dup_examples"] = dn.filter(pl.col("doc_number").is_in(g.sort("len", descending=True).head(3)["doc_number"].to_list())).select(["id", "doc_number", "doc_type", "is_english", "title", "vn_chars"]).head(12).to_dicts()
    # text checks over all docs; line-frequency over a random 10% of batches
    texts = df["vn_text"].to_list()
    random.seed(0)
    nb = (len(texts) + 1999) // 2000
    sample_idx = set(random.sample(range(nb), max(1, nb // 10)))
    tc, lines, hashes = run_text_checks(texts, sample_idx)
    prof["vbpl_text_checks"] = dict(tc)
    nsample_docs = sum(min(2000, len(texts) - b * 2000) for b in sample_idx)
    prof["vbpl_boilerplate_sample_docs"] = nsample_docs
    prof["vbpl_top_lines_docfreq"] = [[l, c] for l, c in lines.most_common(80)]
    hc = Counter(h for h in hashes if h)
    prof["vbpl_text_dup_groups"] = sum(1 for v in hc.values() if v > 1)
    prof["vbpl_text_dup_rows_excess"] = sum(v - 1 for v in hc.values() if v > 1)
    # tier 0-1 specific
    sub = df.with_columns(pl.Series("h", hashes)).filter(pl.col("tier") <= 1)
    hc01 = Counter(h for h in sub["h"].to_list() if h)
    prof["vbpl_tier01_rows"] = sub.height
    prof["vbpl_tier01_text_dup_rows_excess"] = sum(v - 1 for v in hc01.values() if v > 1)
    prof["vbpl_tier01_doc_number_cov"] = int(sub["doc_number"].is_not_null().sum())
    prof["vbpl_tier01_status"] = vc(sub["status"], 20)
    prof["vbpl_tier01_effective_date_cov"] = int(sub["effective_date"].is_not_null().sum())
    prof["vbpl_tier01_issue_date_cov"] = int(sub["issue_date"].is_not_null().sum())
    prof["vbpl_tier01_empty_text"] = int((sub["vn_chars"] == 0).sum())
    prof["vbpl_tier01_is_english"] = int(sub["is_english"].sum())
    # one sample row (metadata + first 600 chars) for the guide
    s = df.filter((pl.col("doc_type") == "Luật") & pl.col("doc_number").is_not_null()).sort("year", descending=True).head(1)
    row = s.drop(["citations", "vn_text", "en_text"]).to_dicts()[0]
    row["vn_text_head"] = s["vn_text"][0][:600]
    row["citations_head"] = s["citations"][0][:3] if s["citations"][0] is not None else None
    prof["vbpl_sample_row"] = row
    del texts, df, sub
    print("vbpl done", f"{time.time()-t0:.0f}s", flush=True)

    # ---------------- hdpl ----------------
    repo = "tmquan/thuvienphapluat-vn-hdpl"
    fs = files(repo)
    prof["hdpl_schema"] = schema_of(fs)
    h = pl.read_parquet(fs)
    prof["hdpl_rows"] = h.height
    prof["hdpl_coverage"] = coverage(h.drop([c for c in ["answer_html"] if c in h.columns]))
    prof["hdpl_area"] = vc(h["area"], 40)
    prof["hdpl_published_year"] = vc(h["published_date"].str.slice(0, 4), 20)
    prof["hdpl_published_range"] = [h["published_date"].min(), h["published_date"].max()]
    hc_ = h.select([pl.col("id").alias("_qa_id"), "citations"]).explode("citations").unnest("citations")
    prof["hdpl_citation_fields"] = hc_.columns
    prof["hdpl_citations_total"] = int(hc_["law_name"].is_not_null().sum()) if "law_name" in hc_.columns else None
    for f in ["law_type", "law_name", "year", "ref"]:
        if f in hc_.columns:
            prof[f"hdpl_cit_{f}_top"] = vc(hc_[f].cast(pl.Utf8), 30)
    for f in hc_.columns:
        if f != "_qa_id":
            prof.setdefault("hdpl_cit_field_coverage", {})[f] = int(hc_[f].is_not_null().sum())
    prof["hdpl_citation_examples"] = hc_.filter(pl.col(hc_.columns[1]).is_not_null()).head(8).to_dicts()
    prof["hdpl_qas_with_citation"] = int((h["num_citations"] > 0).sum())
    prof["hdpl_answer_chars_quantiles"] = {str(p): float(h["answer_chars"].quantile(p)) for p in [.1, .5, .9]}
    prof["hdpl_sample_row"] = {k: (v[:400] if isinstance(v, str) else v) for k, v in h.drop([c for c in ["answer_html"] if c in h.columns]).head(1).to_dicts()[0].items()}
    del h, hc_
    # ---------------- tnpl / htpl / anle / cbba ----------------
    for key, repo in [("tnpl", "tmquan/thuvienphapluat-vn-tnpl"), ("htpl", "tmquan/thuvienphapluat-vn-htpl"),
                      ("anle", "tmquan/anle-toaan-gov-vn"), ("cbba1", "tmquan/cbba-toaan-gov-vn")]:
        fs = files(repo)
        prof[f"{key}_schema"] = schema_of(fs)
        d = pl.read_parquet(fs)
        prof[f"{key}_rows"] = d.height
        prof[f"{key}_coverage"] = coverage(d)
        for col in ["status_vi", "category", "instance_level", "court_level", "is_precedent", "fetch_status", "code"]:
            if col in d.columns:
                prof[f"{key}_{col}"] = vc(d[col], 15)
        if key == "anle":
            prof["anle_precedents"] = d.filter(pl.col("is_precedent")).select(["doc_name", "precedent_number", "official_document_id", "issued_date"]).to_dicts()
            ce = d.select([pl.col("doc_name").alias("_doc"), "citations_law"]).explode("citations_law").unnest("citations_law")
            prof["anle_citations_law_fields"] = ce.columns
            prof["anle_citations_law_kind"] = vc(ce["kind"], 10) if "kind" in ce.columns else None
            prof["anle_citations_law_example"] = ce.drop_nulls(subset=[ce.columns[1]]).head(3).to_dicts()
        for col in ["markdown_chars", "definition_char_len"]:
            if col in d.columns:
                prof[f"{key}_{col}_median"] = float(d[col].median())
    prof["wall_s"] = round(time.time() - t0, 1)
    with open(OUT / "profile.json", "w") as f:
        json.dump(prof, f, indent=1, ensure_ascii=False, default=str)
    print("profile done", prof["wall_s"], "s")

if __name__ == "__main__":
    main()
