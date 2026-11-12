#!/usr/bin/env python3
"""Step 3 - Cleaning and scoping.

Why: the raw crawl has slug titles without diacritics, slug-derived document
numbers that often belong to another (cited) law, hard-wrapped lines, words
split inside syllables, 7% non-NFC texts, English duplicate pages and empty
rows. The agent must cite '<Điều N> of <Luật X số ...>', so every in-scope
document needs a trustworthy number, date, Vietnamese title and clean text.

Scope = normative documents of tiers 0-1:
  kept types: Hiến pháp, Bộ luật, Luật, Pháp lệnh, Nghị định, Thông tư, Thông tư
  liên tịch, Nghị quyết liên tịch, and Nghị quyết / Quyết định only when their
  number has the normative 'N/YYYY/CODE' form (individual decisions are 'N/CODE').

Outputs ($R/data/clean/):
  docs_clean.parquet      in-scope docs: cleaned text + parsed metadata
  docs_tier01_meta.parquet  every tier 0-1 row with parsed metadata + exclusion reason
  clean_report.json       counts after each filter + parse coverage + examples
"""
import os, sys, json, time, re, glob, hashlib, random
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vnlegal_text as V

R = Path(os.environ.get("R", "/path/to/vnlegal"))
OUT = R / "data" / "clean"; OUT.mkdir(parents=True, exist_ok=True)
NPROC = int(os.environ.get("NPROC", "200"))
MAN = json.load(open(R / "data" / "download_manifest.json"))

KEEP_ALWAYS = ["Hiến pháp", "Bộ luật", "Luật", "Pháp lệnh", "Nghị định", "Thông tư",
               "Thông tư liên tịch", "Nghị quyết liên tịch"]
KEEP_IF_NORMATIVE_NUMBER = ["Nghị quyết", "Quyết định"]
EXCLUDED_TYPES_WHY = {
    "Văn bản hợp nhất": "consolidated text, not a normative document; duplicates the articles of the base law",
    "Chỉ thị": "directive; not a normative document type since the 2015 Law on Promulgation of Legal Documents",
    "Lệnh": "presidential promulgation order; no substantive provisions",
    "Sắc lệnh": "1945-1959 decree (historical)", "Sắc luật": "1945-1959 decree-law (historical)",
    "Hiệp định": "international agreement (treaty regime)", "Công ước": "international convention",
    "Điều ước": "international treaty",
}

MOTTO = re.compile(r"(?i)(độc\s*lập\s*-\s*tự\s*do\s*-\s*hạnh\s*phúc|^c[ộo]ng\s*h[òo]a\s*x[ãa]\s*h[ộo]i\s*ch[ủu]\s*ngh[ĩi]a\s*vi[ệe]t\s*nam\s*$)")
SEP = re.compile(r"^[-_=*.…\s]{3,}$")
SIGN = re.compile(r"^(?:TM\.|KT\.|Q\.|TL\.|TUQ\.|PP\.|T/M|K/T)\s|^\(?Đã\s+ký\)?$|^\(Đã ký\)")
NOINHAN = re.compile(r"^Nơi\s+nhận\s*:?")
BLOCK_END = re.compile(r"^(?:Điều\s+\d+|Chương\s+[IVXLCDM\d]+|CHƯƠNG\s+[IVXLCDM\d]+|PHỤ\s+LỤC|Phụ\s+lục|QUY\s+CHẾ|QUY\s+ĐỊNH|ĐIỀU\s+LỆ|QUY\s+TRÌNH|HƯỚNG\s+DẪN|DANH\s+MỤC|BIỂU|MẪU|Mẫu\s+số|[\(\[]?Ban\s+hành\s+kèm)")

FREQ = None
def _init(freq):
    global FREQ
    FREQ = freq

def strip_boilerplate(lines):
    out = []; i = 0; removed = Counter()
    n = len(lines)
    while i < n:
        l = lines[i]
        if NOINHAN.match(l):
            j = i + 1
            while j < n and j - i < 40 and not BLOCK_END.match(lines[j]):
                j += 1
            removed["noi_nhan_block_lines"] += j - i
            i = j; continue
        if MOTTO.search(l) and len(l) < 160:
            removed["motto"] += 1; i += 1; continue
        if SEP.match(l):
            removed["separator"] += 1; i += 1; continue
        if SIGN.match(l) and len(l) < 120:
            removed["signature"] += 1; i += 1; continue
        out.append(re.sub(r"\s*-{4,}\s*$", "", l))
        i += 1
    return out, removed

def process(row):
    raw = row["vn_text"] or ""
    stats = Counter()
    if raw and not __import__("unicodedata").is_normalized("NFC", raw):
        stats["nfc_fixed"] = 1
    t = V.basic_clean(raw)
    hdr = V.parse_header(t, row["doc_type"]) if t else {"doc_number": None, "issue_date": None, "title_core": None, "title_raw": None}
    t = V.unwrap_lines(t) if t else ""
    lines = []
    for l in t.split("\n"):
        l2, m = V.repair_split_syllables(l, FREQ)
        stats["syllable_merges"] += m
        lines.append(l2)
    lines, rem = strip_boilerplate(lines)
    stats.update(rem)
    text = "\n".join(lines).strip()
    norm = " ".join(text.split())
    h = hashlib.md5(norm.encode()).hexdigest() if norm else None
    meta_num = V.norm_docnum(row["doc_number"]) if row["doc_number"] else None
    if meta_num and not re.match(r"^\d{1,5}[a-zA-Z]?/(?:\d{4}/)?[A-ZĐ][A-ZĐ0-9\-]*$", meta_num):
        meta_num_clean = None              # slug garbage appended, e.g. '204/2004/ND-CP-CHE-DO-...'
    else:
        meta_num_clean = meta_num
    num = hdr["doc_number"] or meta_num_clean
    num_src = "header" if hdr["doc_number"] else ("metadata" if meta_num_clean else None)
    st_code, st_date = V.norm_status(row["status"])
    issue_meta = V.parse_dmy(row["issue_date"])
    issue = issue_meta or hdr["issue_date"]
    title_vi = V.make_title(row["doc_type"], num, hdr["title_core"])
    return {
        "id": row["id"], "text": text, "text_chars": len(text), "text_hash": h,
        "doc_number": num, "doc_number_src": num_src, "doc_number_key": V.docnum_key(num) if num else None,
        "doc_number_meta": row["doc_number"], "doc_number_header": hdr["doc_number"],
        "number_has_year": V.has_year_format(num),
        "issue_date": issue, "issue_date_src": "metadata" if issue_meta else ("header" if hdr["issue_date"] else None),
        "issue_date_header": hdr["issue_date"],
        "effective_date_meta": V.parse_dmy(row["effective_date"]),
        "status_raw": row["status"], "status_code": st_code, "status_date": st_date,
        "title_vi": title_vi, "title_core": hdr["title_core"], "title_raw": hdr["title_raw"],
        "stats": dict(stats),
    }

def main():
    t0 = time.time()
    rep = {"funnel": []}
    fs = sorted(glob.glob(os.path.join(MAN["datasets"]["tmquan/thuvienphapluat-vn-vbpl"]["local_dir"], "documents-*.parquet")))
    cols = ["id", "doc_type", "doc_number", "year", "tier", "issuer", "issuer_kind", "legal_area", "title", "url",
            "is_english", "issue_date", "effective_date", "status", "vn_chars", "vn_text"]
    df = pl.read_parquet(fs, columns=cols)
    rep["funnel"].append(["F0 all vbpl rows", df.height])
    df = df.filter(pl.col("tier") <= 1)
    rep["funnel"].append(["F1 tier 0-1", df.height])
    df = df.filter(~pl.col("is_english"))
    rep["funnel"].append(["F2 drop English-translation pages (is_english)", df.height])
    if os.environ.get("SAMPLE"):
        df = df.sample(int(os.environ["SAMPLE"]), seed=1)
        global OUT
        OUT = OUT / "sample"; OUT.mkdir(parents=True, exist_ok=True)
    # syllable frequency table from a sample (for split-repair tie breaks)
    sample = df.sample(min(3000, df.height), seed=0)["vn_text"].to_list()
    freq = Counter()
    for s in sample:
        for w in V.basic_clean(s or "").lower().split():
            if V._ALPHA.match(w) and V.valid_syllable(w):
                freq[w] += 1
    freq = dict(freq.most_common(20000))
    rows = df.to_dicts()
    print("rows to clean", len(rows), f"{time.time()-t0:.0f}s", flush=True)
    with Pool(NPROC, initializer=_init, initargs=(freq,)) as p:
        res = p.map(process, rows, chunksize=64)
    print("cleaned", f"{time.time()-t0:.0f}s", flush=True)
    agg = Counter()
    for r in res:
        agg.update(r.pop("stats"))
    rep["cleaning_stats"] = dict(agg)
    meta = pl.DataFrame([{k: v for k, v in r.items() if k != "text"} for r in res], infer_schema_length=None)
    base = df.drop(["vn_text", "doc_number", "issue_date", "effective_date", "status"]).rename({"title": "title_slug"})
    meta = base.join(meta, on="id", how="left")
    texts = {r["id"]: r["text"] for r in res}
    del res, rows
    # ---- filters with reasons
    meta = meta.with_columns(pl.lit(None, dtype=pl.Utf8).alias("excluded_reason"))
    def mark(cond, reason):
        nonlocal meta
        meta = meta.with_columns(pl.when(pl.col("excluded_reason").is_null() & cond).then(pl.lit(reason)).otherwise(pl.col("excluded_reason")).alias("excluded_reason"))
        kept = meta.filter(pl.col("excluded_reason").is_null()).height
        rep["funnel"].append([reason, kept])
    mark(pl.col("text_chars") < 200, "F3 drop empty / near-empty text (<200 chars after cleaning)")
    mark(~pl.col("doc_type").is_in(KEEP_ALWAYS + KEEP_IF_NORMATIVE_NUMBER), "F4 keep normative document types")
    mark(pl.col("doc_type").is_in(KEEP_IF_NORMATIVE_NUMBER) & ~pl.col("number_has_year"),
         "F5 Nghị quyết/Quyết định: keep only normative numbers N/YYYY/CODE")
    # F6 exact duplicate text: keep the row with status/effective metadata, then longest, then smallest id
    live = meta.filter(pl.col("excluded_reason").is_null()).with_columns(
        (pl.col("status_code").is_not_null().cast(pl.Int8) + pl.col("effective_date_meta").is_not_null().cast(pl.Int8)).alias("_m"),
        pl.col("id").cast(pl.Int64, strict=False).alias("_idn"))
    keep_ids = set(live.sort(["_m", "text_chars", "_idn"], descending=[True, True, False]).unique(subset=["text_hash"], keep="first", maintain_order=True)["id"].to_list())
    mark(~pl.col("id").is_in(list(keep_ids)), "F6 drop exact duplicate texts")
    # F7 duplicate (doc_type, doc_number_key, issue year): keep richer/longer
    live = meta.filter(pl.col("excluded_reason").is_null()).with_columns(
        (pl.col("status_code").is_not_null().cast(pl.Int8) + pl.col("effective_date_meta").is_not_null().cast(pl.Int8)).alias("_m"),
        pl.col("issue_date").str.slice(0, 4).alias("_y"), pl.col("id").cast(pl.Int64, strict=False).alias("_idn"))
    withnum = live.filter(pl.col("doc_number_key").is_not_null())
    keep2 = set(withnum.sort(["_m", "text_chars", "_idn"], descending=[True, True, False]).unique(subset=["doc_type", "doc_number_key", "_y"], keep="first")["id"].to_list())
    nonum = set(live.filter(pl.col("doc_number_key").is_null())["id"].to_list())
    mark(~pl.col("id").is_in(list(keep2 | nonum)), "F7 drop duplicate (doc_type, doc_number, year) records")
    meta.write_parquet(OUT / "docs_tier01_meta.parquet")
    final = meta.filter(pl.col("excluded_reason").is_null())
    final = final.with_columns(pl.Series("text", [texts[i] for i in final["id"].to_list()]))
    final.write_parquet(OUT / "docs_clean.parquet")
    # ---- report
    rep["kept_doc_types"] = final.group_by("doc_type").len().sort("len", descending=True).rows()
    rep["kept_by_tier"] = final.group_by("tier").len().sort("tier").rows()
    rep["excluded_by_reason"] = meta.group_by("excluded_reason").len().sort("len", descending=True).rows()
    rep["excluded_types_in_tier01"] = meta.filter(pl.col("excluded_reason") == "F4 keep normative document types").group_by("doc_type").len().sort("len", descending=True).rows()
    rep["excluded_types_why"] = EXCLUDED_TYPES_WHY
    rep["F5_examples_dropped"] = meta.filter(pl.col("excluded_reason").str.starts_with("F5")).select(["id", "doc_type", "doc_number", "title_vi"]).head(5).to_dicts()
    n = final.height
    rep["parse_coverage_in_scope"] = {
        "docs": n,
        "doc_number_any": int(final["doc_number"].is_not_null().sum()),
        "doc_number_from_header": int((final["doc_number_src"] == "header").sum()),
        "doc_number_meta_present": int(final["doc_number_meta"].is_not_null().sum()),
        "meta_vs_header_both": int((final["doc_number_meta"].is_not_null() & final["doc_number_header"].is_not_null()).sum()),
        "meta_vs_header_prefix_agree": int(sum(1 for a, b in zip(final["doc_number_meta"].to_list(), final["doc_number_header"].to_list())
                                              if a and b and (V.docnum_key(a) or "").startswith(V.docnum_key(b) or "~"))),
        "issue_date_any": int(final["issue_date"].is_not_null().sum()),
        "issue_date_from_header": int((final["issue_date_src"] == "header").sum()),
        "effective_date_meta": int(final["effective_date_meta"].is_not_null().sum()),
        "status_any": int(final["status_code"].is_not_null().sum()),
        "title_from_header": int(final["title_core"].is_not_null().sum()),
    }
    rep["status_codes_in_scope"] = final.group_by("status_code").len().sort("len", descending=True).rows()
    rep["text_chars_quantiles_in_scope"] = {str(q): float(final["text_chars"].quantile(q)) for q in [.05, .25, .5, .75, .95, .99]}
    rep["total_chars_in_scope"] = int(final["text_chars"].sum())
    known = ["10/2012/QH13", "45/2019/QH14", "45/2013/QH13", "31/2024/QH15", "58/2014/QH13", "41/2024/QH15"]
    rep["known_laws"] = final.filter(pl.col("doc_number").is_in(known)).select(
        ["id", "doc_type", "doc_number", "doc_number_src", "doc_number_meta", "title_vi", "issue_date", "effective_date_meta", "status_raw", "text_chars"]).to_dicts()
    ex = final.filter(pl.col("id") == "333670")
    if ex.height:
        r = ex.drop("text").to_dicts()[0]; r["text_head"] = ex["text"][0][:700]
        rep["example_cleaned_doc"] = r
    raw = df.filter(pl.col("id") == "333670")
    if raw.height:
        rep["example_raw_head"] = raw["vn_text"][0][:700]
    rep["wall_s"] = round(time.time() - t0, 1)
    json.dump(rep, open(OUT / "clean_report.json", "w"), ensure_ascii=False, indent=1, default=str)
    for f in rep["funnel"]:
        print(f"{f[1]:>9,}  {f[0]}")
    print("in-scope types", rep["kept_doc_types"])
    print("coverage", rep["parse_coverage_in_scope"])
    print("wall", rep["wall_s"])

if __name__ == "__main__":
    main()
