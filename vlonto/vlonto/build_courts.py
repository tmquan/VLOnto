"""Court decisions (anle + all cbba shards), courts, precedents, applied-provision and case-to-case edges.

Pass 1 runs one process per parquet file: decision rows, court names, law citations resolved to documents /
articles / clauses / points, precedent citations, and case-citation records with the date and the text window
written next to each citation. Pass 2 resolves case citations against all decisions: number + year + symbol must
match and either the date next to the citation equals the decision date (method case-number-date) or the court
named next to the citation equals the decision's court (method case-number-court); ambiguous matches are dropped,
and so are date-only matches unless both courts are known and the same, in the same province, or the citing court
is the Supreme Court or the High Court of the cited court's region; first-instance judgments from another province, at
an impossible court level, or of the appellate court itself are dropped too.
No judgment text and no person names are written to the output tables (the windows stay in a temporary file).
"""
import glob
import multiprocessing as mp
import os
import re
import time
from collections import Counter, defaultdict

import polars as pl

from . import config as C
from . import courts_norm as CN
from . import vnlegal_text as VT
from .resolve import NAME_TYPES, DocResolver, norm_article, norm_clause, norm_point


def check_date(d, year_in_number):
    """Source decision dates outside 1945..build date, or more than one year away from the year in the decision
    number, are treated as unknown (the source sometimes carries dates taken from the text, e.g. birth dates)."""
    if not d:
        return None, "missing"
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return None, "malformed"
    y = int(d[:4])
    if y < 1945 or d > C.BUILD_DATE:
        return None, "out_of_range"
    if year_in_number is not None and abs(y - int(year_in_number)) > 1:
        return None, "year_mismatch"
    return d, "ok"

_G = {}
TMP = os.path.join(C.BUILD, "tmp", "courts")
DATE_A = re.compile(r"ngày\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})", re.I)
DATE_B = re.compile(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", re.I)
AL_RE = re.compile(r"(\d{1,3})\s*/\s*(\d{4})\s*/\s*AL\b")
YEAR_IN_ID = re.compile(r"/\s*((?:19|20)\d{2})\s*/")
# decision numbers that are really the number of a cited law or resolution (source extraction error), e.g.
# '326/2016/UBTVQH14' (court fees resolution) or '97/2015/QH13': number, code and date of such rows are dropped
# territorial jurisdiction of the three High Courts (Resolution 957/NQ-UBTVQH13 of 2015; the provinces merged in 2025
# keep the name of one of their predecessors, which lies in the same region)
HIGH_REGION = {
    "HÀ NỘI": "Hà Nội, Hải Phòng, Hà Giang, Cao Bằng, Bắc Kạn, Tuyên Quang, Lào Cai, Điện Biên, Lai Châu, Sơn La, Yên Bái, Hòa Bình, "
              "Thái Nguyên, Lạng Sơn, Quảng Ninh, Bắc Giang, Phú Thọ, Vĩnh Phúc, Bắc Ninh, Hải Dương, Hưng Yên, Thái Bình, Hà Nam, "
              "Nam Định, Ninh Bình, Thanh Hóa, Nghệ An, Hà Tĩnh",
    "ĐÀ NẴNG": "Quảng Bình, Quảng Trị, Thừa Thiên Huế, Huế, Đà Nẵng, Quảng Nam, Quảng Ngãi, Bình Định, Phú Yên, Khánh Hòa, Kon Tum, "
               "Gia Lai, Đắk Lắk",
    "HỒ CHÍ MINH": "Hồ Chí Minh, Cần Thơ, Lâm Đồng, Đắk Nông, Ninh Thuận, Bình Thuận, Bình Phước, Bình Dương, Đồng Nai, Tây Ninh, "
                   "Bà Rịa - Vũng Tàu, Long An, Đồng Tháp, Tiền Giang, An Giang, Bến Tre, Vĩnh Long, Trà Vinh, Hậu Giang, Kiên Giang, "
                   "Sóc Trăng, Bạc Liêu, Cà Mau",
}


def _pkey(p):
    return re.sub(r"[^a-z]", "", C.strip_diacritics(p or "").lower())


HIGH_REGION_KEYS = {_pkey(k): {_pkey(x) for x in v.split(", ")} for k, v in HIGH_REGION.items()}
LEGIS_NUM = re.compile(r"UBTVQH|/QH\d|N[ĐD]-?CP|/NQ-|/TT-|TTLT|Q[ĐD]-TTG|/L-CTN|/PL-", re.I)


def decision_kind(code):
    a = re.sub(r"\s", "", C.strip_diacritics(code or "").upper())
    if not a:
        return "CourtDecision"
    if a.startswith("QD"):
        return "CourtRuling"
    if re.match(r"^(DS|HS|HC|KDTM|KD|LD|HNGD|HN|PS|KT)(-|ST|PT|GDT|TT|$)", a):
        return "Judgment"
    return "CourtDecision"


def code_key(code):
    return re.sub(r"\s", "", C.strip_diacritics(code or "").upper())


def iso(d, m, y):
    try:
        import datetime
        return datetime.date(int(y), int(m), int(d)).isoformat()
    except Exception:
        return None


def precedent_id(n, y):
    return f"{int(n):02d}-{int(y)}-al", f"{int(n):02d}/{int(y)}/AL"


def _init_worker(docs_path, arts_path):
    """Spawned worker: build the resolver and the article set from small temporary parquet files
    (polars must not be used after fork, its thread pool can deadlock)."""
    d = pl.read_parquet(docs_path)
    _G["res"] = DocResolver(d.to_dicts())
    a = pl.read_parquet(arts_path)
    _G["main_art"] = set(a.iter_rows())


def resolve_law(c, at):
    res = _G["res"]
    lt = (c.get("law_type") or "").strip()
    num = (c.get("id") or "").strip()
    ref = c.get("ref") or ""
    m = AL_RE.search(num) or (AL_RE.search(ref) if lt == "Án lệ" else None)
    if m:
        return ("precedent", precedent_id(m.group(1), m.group(2)))
    if num and (VT.DOCNUM_ANY.search(num) or VT.DOCNUM_NOYEAR.search(num)):
        th = lt if lt in C.DOC_TYPES else None
        d, how = res.by_number(num, th, at)
        if d:
            return ("doc", d, how)
    name = (c.get("law_name") or "").strip()
    year = c.get("year")
    types = [lt] if lt in NAME_TYPES else (["Pháp lệnh"] if lt.startswith("Pháp lệnh") else [])
    if name and types:
        typ, nm, yr, _ = res.parse_reference(f"{types[0]} {name}")
        yr = int(year) if year else yr
        if typ in NAME_TYPES and nm:
            d, how = res.by_name(typ, nm, yr, at)
            if d:
                return ("doc", d, how)
            return ("fail", how)
    if not lt:
        return ("fail", "no_law_type")
    if lt not in C.DOC_TYPES and lt not in ("Pháp lệnh/Nghị quyết (UBTVQH)",):
        return ("fail", "type_out_of_scope:" + lt)
    return ("fail", "number_not_in_scope" if num else "no_number_no_name")


def process_file(args):
    path, source, shard = args
    t0 = time.time()
    main_art = _G["main_art"]
    cols = ["doc_name", "web_url", "official_document_id_normalized", "number", "year", "code", "category", "instance_level",
            "court", "court_level", "issued_date", "is_precedent", "precedent_number", "citations_law", "citations_case", "markdown"]
    df = pl.read_parquet(path, columns=cols)
    stats = Counter()
    dec, law, case, prec = [], [], [], []
    for r in df.iter_rows(named=True):
        did = f"{source}:{r['doc_name']}"
        md = r["markdown"] or ""
        num, yr = r["number"], r["year"]
        dnum, dcode = r["official_document_id_normalized"], r["code"]
        if dnum and LEGIS_NUM.search(dnum):
            stats["decision_number:legislative_dropped"] += 1
            dnum, dcode, num, yr = None, None, None, None
            at, dchk = None, "number_is_legislative"
        else:
            at, dchk = check_date(r["issued_date"], yr)
        if at:
            # a decision cannot predate the documents and decisions it cites (year in their numbers)
            ys = [int(m.group(1)) for c in (r["citations_law"] or []) + (r["citations_case"] or [])
                  for m in [YEAR_IN_ID.search(c.get("id") or "")] if m]
            ys = [y for y in ys if y <= int(C.BUILD_DATE[:4])]
            if ys and int(at[:4]) < max(ys):
                at, dchk = None, "before_cited_document"
        stats["issued_date:" + dchk] += 1
        cp, cmeth, cnote = CN.parse_court(r["court"], prefer="last"), "court-name:field", None
        if not isinstance(cp, dict):
            reason1 = cp
            cp, cmeth = CN.parse_court(CN.clean(md[:700]), prefer="first"), "court-name:header"
            if not isinstance(cp, dict):
                why = "masked" if "masked" in (reason1, cp) else "unparsed"
                stats["court_" + why] += 1
                cp, cmeth, cnote = None, None, why
        if cp:
            stats[f"court_kind:{cp['kind']}"] += 1
        lvl = r["court_level"] or (CN.level_of(cp) if cp else None)
        stats["court_level_inferred"] += int(r["court_level"] is None and lvl is not None)
        dec.append({"decision_id": did, "source": source, "doc_name": r["doc_name"],
                    "decision_number": dnum, "decision_code": dcode,
                    "number": int(num) if num is not None else None, "year_in_number": int(yr) if yr is not None else None,
                    "decision_kind": decision_kind(dcode), "category": r["category"], "instance_level": r["instance_level"],
                    "court_level": lvl, "court_kind": cp["kind"] if cp else None, "court_unit": cp["unit"] if cp else None,
                    "court_name": cp["name"] if cp else None, "court_name_key": cp["name_key"] if cp else None,
                    "court_province": cp["province"] if cp else None, "court_method": cmeth, "court_note": cnote,
                    "issued_date": at, "issued_date_check": dchk, "url": r["web_url"], "is_precedent_source": bool(r["is_precedent"]),
                    "precedent_number": r["precedent_number"],
                    "n_law_citations": len(r["citations_law"] or []), "n_case_citations": len(r["citations_case"] or [])})
        if r["is_precedent"] and r["precedent_number"]:
            m = AL_RE.search(r["precedent_number"])
            if m:
                pid, pnum = precedent_id(m.group(1), m.group(2))
                prec.append({"src_id": did, "precedent_id": pid, "precedent_number": pnum, "relation": "selected_from", "method": "source-metadata"})
        for c in r["citations_law"] or []:
            stats["law_raw"] += 1
            stats[f"law_raw_kind:{c.get('kind')}"] += 1
            out = resolve_law(c, at)
            sid = (c.get("sentence_id") or [None])[0]
            if out[0] == "precedent":
                stats["law_precedent"] += 1
                prec.append({"src_id": did, "precedent_id": out[1][0], "precedent_number": out[1][1], "relation": "applies", "method": "precedent-number"})
                continue
            if out[0] == "fail":
                stats["law_unresolved:" + out[1]] += 1
                continue
            d, how = out[1], out[2]
            stats["law_resolved_doc"] += 1
            a = norm_article(c.get("article"))
            art = None
            if a:
                if (d, a) in main_art:
                    art = f"{d}::dieu-{a}"
                    stats["law_resolved_article"] += 1
                else:
                    stats["law_article_not_in_document"] += 1
            law.append({"decision_id": did, "dst_doc_id": d, "dst_article_id": art, "article_cited": a,
                        "clause": norm_clause(c.get("clause")) if art else None, "point": norm_point(c.get("point")) if art else None,
                        "cit_kind": c.get("kind"), "law_type": c.get("law_type"), "ref": C.cut(c.get("ref"), 160),
                        "sentence_id": sid, "method": how})
        for c in r["citations_case"] or []:
            stats["case_raw"] += 1
            code = c.get("code") or ""
            cid = c.get("id") or ""
            m = AL_RE.search(cid) if ("AL" in code.upper() or "/AL" in cid) else None
            if m:
                pid, pnum = precedent_id(m.group(1), m.group(2))
                prec.append({"src_id": did, "precedent_id": pid, "precedent_number": pnum, "relation": "applies", "method": "precedent-number"})
                stats["case_precedent"] += 1
                continue
            if c.get("number") is None or c.get("year") is None or not code:
                stats["case_incomplete_id"] += 1
                continue
            span = (c.get("span") or [None])[0]
            if span:
                s0, e0 = span[0], span[1]
            else:
                p = md.find(cid) if cid else -1
                s0, e0 = (p, p + len(cid)) if p >= 0 else (None, None)
            win, dt = None, None
            if e0 is not None:
                w = md[e0: e0 + 240]
                dm = DATE_A.search(w[:90]) or DATE_B.search(w[:90])
                if dm:
                    dt = iso(dm.group(1), dm.group(2), dm.group(3))
                win = CN.clean(w)
            case.append({"src_id": did, "src_date": at, "cited_id": cid, "number": int(c["number"]), "year": int(c["year"]),
                         "code_key": code_key(code), "role": c.get("role"), "ctx_date": dt, "ctx_window": win})
    os.makedirs(TMP, exist_ok=True)
    pl.DataFrame(dec, infer_schema_length=None).write_parquet(f"{TMP}/dec_{shard}.parquet")
    pl.DataFrame(law, infer_schema_length=None, schema_overrides={"dst_article_id": pl.Utf8, "clause": pl.Utf8, "point": pl.Utf8,
                                                                    "article_cited": pl.Utf8, "sentence_id": pl.Utf8}).write_parquet(f"{TMP}/law_{shard}.parquet")
    pl.DataFrame(case, infer_schema_length=None, schema_overrides={"ctx_date": pl.Utf8, "ctx_window": pl.Utf8, "role": pl.Utf8,
                                                                     "src_date": pl.Utf8}).write_parquet(f"{TMP}/case_{shard}.parquet")
    pl.DataFrame(prec, infer_schema_length=None, schema={"src_id": pl.Utf8, "precedent_id": pl.Utf8, "precedent_number": pl.Utf8,
                                                         "relation": pl.Utf8, "method": pl.Utf8}).write_parquet(f"{TMP}/prec_{shard}.parquet")
    stats["rows"] = df.height
    stats["wall_s"] = round(time.time() - t0, 1)
    return shard, dict(stats)


def canonical_courts(dec, rep):
    """Resolve district names written without a province, then build one row per canonical court.

    A district-level name without a province takes the province of the same unit + name seen elsewhere with a
    province when that province is unique; when several provinces share the name the decision stays without a
    court (court_note 'ambiguous-without-province'); regional courts need the province in the text.
    """
    dk = (dec.filter((pl.col("court_kind") == "district") & pl.col("court_province").is_not_null())
             .group_by(["court_unit", "court_name_key"])
             .agg(pl.col("court_province").n_unique().alias("_np"), pl.col("court_province").first().alias("_p1")))
    dec = dec.join(dk, on=["court_unit", "court_name_key"], how="left")
    need = (pl.col("court_kind") == "district") & pl.col("court_province").is_null()
    one = need & (pl.col("_np") == 1)
    amb = need & (pl.col("_np") > 1)
    reg = (pl.col("court_kind") == "regional") & pl.col("court_province").is_null()
    dec = dec.with_columns(
        pl.when(one).then(pl.col("_p1")).otherwise(pl.col("court_province")).alias("court_province"),
        pl.when(one).then(pl.col("court_method") + pl.lit("+province-from-name")).otherwise(pl.col("court_method")).alias("court_method"),
        pl.when(amb).then(pl.lit("ambiguous-without-province")).when(reg).then(pl.lit("regional-without-province"))
          .otherwise(pl.col("court_note")).alias("court_note"),
        pl.when(amb | reg).then(pl.lit(None, dtype=pl.Utf8)).otherwise(pl.col("court_kind")).alias("court_kind"),
    ).drop("_np", "_p1")
    # rare variants that are a frequent name plus trailing words of the judgment ('ĐỐNG ĐA THÀNH', 'KRÔNG BÚK MỞ'):
    # merged into the frequent name of the same unit and province (suffix of at least two letters, base 20x larger)
    dist = dec.filter(pl.col("court_kind") == "district").group_by(["court_unit", "court_province", "court_name_key"]).len()
    base = defaultdict(list)
    for u, p_, k, c in dist.iter_rows():
        if c >= 20:
            base[(u, p_)].append((k, c))
    remap = {}
    for u, p_, k, c in dist.iter_rows():
        for bk, bc in sorted(base.get((u, p_), []), key=lambda x: -len(x[0])):
            if k != bk and k.startswith(bk) and len(k) - len(bk) >= 2 and bc >= 20 * c:
                remap[(u, p_ or "", k)] = bk
                break
    if remap:
        rm = pl.DataFrame([{"court_unit": u, "_p": p_, "court_name_key": k, "_nk": v} for (u, p_, k), v in remap.items()])
        dec = (dec.with_columns(pl.col("court_province").fill_null("").alias("_p"))
                  .join(rm, on=["court_unit", "_p", "court_name_key"], how="left")
                  .with_columns(pl.coalesce("_nk", "court_name_key").alias("court_name_key"),
                                pl.when(pl.col("_nk").is_not_null()).then(pl.lit(None, dtype=pl.Utf8)).otherwise(pl.col("court_name")).alias("court_name"))
                  .drop("_p", "_nk"))
    dec = dec.with_columns(pl.when(pl.col("court_kind").is_not_null()).then(
        pl.concat_str([pl.col(c).fill_null("") for c in ("court_kind", "court_unit", "court_name_key", "court_province")], separator="|"))
        .otherwise(pl.lit(None, dtype=pl.Utf8)).alias("_gkey"))
    # names seen fewer than 3 times are OCR fragments or anonymised initials far more often than real courts
    cnt = dec.filter(pl.col("_gkey").is_not_null()).group_by("_gkey").len()
    rare = cnt.filter(pl.col("len") < 3).select("_gkey").with_columns(pl.lit(True).alias("_rare"))
    dec = dec.join(rare, on="_gkey", how="left").with_columns(pl.col("_rare").fill_null(False))
    dec = dec.with_columns(
        pl.when(pl.col("_rare")).then(pl.lit("rare-name")).otherwise(pl.col("court_note")).alias("court_note"),
        pl.when(pl.col("_rare")).then(pl.lit(None, dtype=pl.Utf8)).otherwise(pl.col("_gkey")).alias("_gkey")).drop("_rare")
    rep["courts_merge"] = {"rare_variants_merged": len(remap), "rare_names_unlinked": rare.height}
    L = dec.filter(pl.col("_gkey").is_not_null())
    g = L.group_by("_gkey").agg(pl.col("court_kind").first(), pl.col("court_unit").first(), pl.col("court_name_key").first(),
                                 pl.col("court_province").first(), pl.len().alias("n_decisions"),
                                 pl.col("court_method").str.starts_with("court-name:header").sum().alias("n_from_header"),
                                 pl.col("court_method").str.ends_with("+province-from-name").sum().alias("n_province_from_name"))
    nm = (L.filter(pl.col("court_name").is_not_null()).group_by(["_gkey", "court_name"]).len()
           .sort(["_gkey", "len", "court_name"], descending=[False, True, False])
           .unique(subset=["_gkey"], keep="first", maintain_order=True).select("_gkey", "court_name"))
    g = g.join(nm, on="_gkey", how="left").sort("n_decisions", descending=True)
    rows, used = [], set()
    for r in g.iter_rows(named=True):
        c = {"kind": r["court_kind"], "unit": r["court_unit"], "name": r["court_name"], "name_key": r["court_name_key"],
             "province": r["court_province"]}
        disp = None
        if c["kind"] == "district":
            disp = CN.name_display(c["name"])
            cid = C.slugify(c["unit"]) + "-" + C.slugify(disp) + ("-" + C.slugify(c["province"]) if c["province"] else "")
        else:
            cid = CN.court_key(c)
        base, n = cid, 2
        while cid in used:
            cid, n = f"{base}-{n}", n + 1
        used.add(cid)
        rows.append({"_gkey": r["_gkey"], "court_id": cid, "iri": C.iri_court(cid), "label": CN.label(c, disp),
                     "court_kind": c["kind"], "court_level": CN.level_of(c),
                     "province": CN.province_display(c["province"]) if c["province"] else None, "head": CN.head(c),
                     "n_decisions": r["n_decisions"], "n_from_header": r["n_from_header"],
                     "n_province_from_name": r["n_province_from_name"]})
    courts = pl.DataFrame(rows, infer_schema_length=None)
    multi = Counter(r["head"] for r in rows if r["court_kind"] == "district")
    raw_prov = {r["_gkey"]: r["_gkey"].split("|")[3] for r in rows}
    courts = courts.with_columns(pl.struct("head", "court_kind", "_gkey").map_elements(
        lambda x: (x["head"] + (" THÀNH PHỐ " if raw_prov[x["_gkey"]] in CN.CENTRAL else " TỈNH ") + raw_prov[x["_gkey"]])
        if x["court_kind"] == "district" and multi[x["head"]] > 1 and raw_prov[x["_gkey"]] else x["head"],
        return_dtype=pl.Utf8).alias("head"))
    dec = dec.join(courts.select("_gkey", "court_id"), on="_gkey", how="left")
    dec = dec.drop("_gkey", "court_kind", "court_unit", "court_name", "court_name_key", "court_province")
    courts = courts.drop("_gkey")
    rep["courts_canonical"] = {
        "courts": courts.height, "by_kind": dict(Counter(courts["court_kind"].to_list())),
        "district_courts_without_province": int(courts.filter((pl.col("court_kind") == "district") & pl.col("province").is_null()).height),
        "decisions_linked": int(dec["court_id"].is_not_null().sum()),
        "decisions_province_from_name": int(dec["court_method"].fill_null("").str.ends_with("+province-from-name").sum()),
        "decisions_by_court_note": dict(Counter(dec["court_note"].fill_null("linked").to_list())),
        "courts_with_ge_10_decisions": int((courts["n_decisions"] >= 10).sum())}
    return dec, courts


def build_courts(docs, arts, rep, workers=17):
    t0 = time.time()
    os.makedirs(TMP, exist_ok=True)
    for f in glob.glob(f"{TMP}/*.parquet"):
        os.remove(f)
    docs_path, arts_path = f"{TMP}/_docs.parquet", f"{TMP}/_main_art.parquet"
    docs.select("doc_id", "doc_type_vi", "doc_number", "doc_number_key", "title_core", "issue_date", "effective_date") \
        .rename({"doc_type_vi": "doc_type"}).write_parquet(docs_path)
    arts.filter(pl.col("segment") == "main").select("doc_id", "article_no").write_parquet(arts_path)
    jobs = [(p, "anle", "anle") for p in sorted(glob.glob(f"{C.snapshot('anle-toaan-gov-vn')}/**/*.parquet", recursive=True))]
    cb = sorted(glob.glob(f"{C.snapshot('cbba-toaan-gov-vn')}/documents-*.parquet"))
    jobs += [(p, "cbba", f"cbba{i:02d}") for i, p in enumerate(cb)]
    rep["court_input_files"] = {"anle": sum(1 for j in jobs if j[1] == "anle"), "cbba_documents_shards": len(cb)}
    with mp.get_context("spawn").Pool(min(workers, len(jobs)), initializer=_init_worker, initargs=(docs_path, arts_path)) as pool:
        results = pool.map(process_file, jobs, chunksize=1)
    tot = Counter()
    per = {}
    for shard, st in results:
        per[shard] = {"rows": st["rows"], "wall_s": st["wall_s"]}
        tot.update({k: v for k, v in st.items() if k != "wall_s"})
    rep["court_pass1"] = {"per_file": per, "totals": dict(tot), "wall_s": round(time.time() - t0, 1)}
    dec = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f"{TMP}/dec_*.parquet"))], how="diagonal_relaxed")  # noqa
    dec = dec.with_columns(pl.concat_str([pl.lit(C.ID + "decision/"), pl.col("source"), pl.lit("/"), pl.col("doc_name")]).alias("iri"),
                           pl.col("issued_date").str.slice(0, 4).cast(pl.Int32, strict=False).alias("year"))
    # ------------------------------------------------ courts
    dec, courts = canonical_courts(dec, rep)
    # ------------------------------------------------ precedents
    pe = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f"{TMP}/prec_*.parquet"))], how="diagonal_relaxed")
    pe = pe.unique(subset=["src_id", "precedent_id", "relation"], maintain_order=True)
    precedents = (pe.group_by("precedent_id").agg(pl.col("precedent_number").first(),
                                                   pl.col("src_id").filter(pl.col("relation") == "selected_from").alias("source_decision_ids"),
                                                   (pl.col("relation") == "applies").sum().alias("n_citing_decisions"))
                  .with_columns(pl.col("precedent_id").map_elements(C.iri_precedent, return_dtype=pl.Utf8).alias("iri"))
                  .sort("precedent_id"))
    # ------------------------------------------------ law edges
    law = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f"{TMP}/law_*.parquet"))], how="diagonal_relaxed")
    rep["decision_law_records_resolved"] = law.height
    law = (law.group_by(["decision_id", "dst_doc_id", "dst_article_id", "clause", "point"], maintain_order=True)
              .agg(pl.len().alias("n_mentions"), pl.col("article_cited").first(), pl.col("cit_kind").first(), pl.col("law_type").first(),
                   pl.col("ref").first(), pl.col("sentence_id").first(), pl.col("method").first()))
    # ------------------------------------------------ case edges (pass 2)
    t1 = time.time()
    case = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f"{TMP}/case_*.parquet"))], how="diagonal_relaxed")
    idx = defaultdict(list)
    head_of = dict(zip(courts["court_id"].to_list(), courts["head"].to_list()))
    prov_of = dict(zip(courts["court_id"].to_list(), courts["province"].to_list()))
    kind_of = dict(zip(courts["court_id"].to_list(), courts["court_kind"].to_list()))
    court_of, code_of = {}, {}
    for r in dec.select("decision_id", "number", "year_in_number", "decision_code", "issued_date", "court_id").iter_rows(named=True):
        court_of[r["decision_id"]] = r["court_id"]
        code_of[r["decision_id"]] = r["decision_code"]
        if r["number"] is None or r["year_in_number"] is None or not r["decision_code"]:
            continue
        idx[(r["number"], r["year_in_number"], code_key(r["decision_code"]))].append(
            (r["decision_id"], r["issued_date"], head_of.get(r["court_id"]) if r["court_id"] else None, prov_of.get(r["court_id"])))
    cs = Counter()
    edges = []
    for r in case.iter_rows(named=True):
        cands = [x for x in idx.get((r["number"], r["year"], r["code_key"]), []) if x[0] != r["src_id"]]
        if not cands:
            cs["no_candidate_in_corpus"] += 1
            continue
        if r["src_date"]:
            cands = [x for x in cands if not x[1] or x[1] <= r["src_date"]]
            if not cands:
                cs["candidates_issued_later"] += 1
                continue
        win = r["ctx_window"] or ""
        court_ok = [x for x in cands if x[2] and len(x[2]) > 6 and re.search(r"(?:^|[\s,])" + re.escape(x[2]) + r"(?:$|[\s,.;])", win)]
        date_ok = [x for x in cands if r["ctx_date"] and x[1] == r["ctx_date"]]
        hit, how = None, None
        if len(date_ok) == 1:
            other_court = court_ok and date_ok[0] not in court_ok
            if not other_court:
                hit, how = date_ok[0], "case-number-date"
            else:
                cs["date_and_court_disagree"] += 1
        elif len(date_ok) > 1:
            both = [x for x in date_ok if x in court_ok]
            if len(both) == 1:
                hit, how = both[0], "case-number-date"
            else:
                cs["ambiguous_same_date"] += 1
        elif len(court_ok) == 1:
            hit, how = court_ok[0], "case-number-court"
        elif len(court_ok) > 1:
            cs["ambiguous_same_court"] += 1
        else:
            cs["no_date_or_court_match"] += 1
        if hit and how == "case-number-date" and hit not in court_ok:
            # a date match without the court named next to the citation: numbers restart at every court each year, so a
            # decision of a court in another province with the same number and date is usually a coincidence (the
            # cited decision of the citing court itself is often not in the corpus). Kept only when both courts are
            # known and are the same court, in the same province, or the citing court is the Supreme or a High Court.
            sc, hc = court_of.get(r["src_id"]), court_of.get(hit[0])
            sp, hp = prov_of.get(sc), prov_of.get(hc)
            if not (sc and hc):
                cs["dropped:date_match_court_unknown"] += 1
                hit = None
            elif sc != hc and kind_of.get(sc) not in ("supreme", "high") and not (sp and hp and sp == hp):
                cs["dropped:date_match_other_province"] += 1
                hit = None
            elif kind_of.get(sc) == "high" and sc != hc and kind_of.get(hc) != "supreme" \
                    and _pkey(hp) not in HIGH_REGION_KEYS.get(_pkey(sp), {_pkey(hp)}):
                cs["dropped:date_match_outside_high_court_region"] += 1   # a High Court only reviews courts of its region
                hit = None
        if hit and r["role"] == "first-instance":
            # the first-instance judgment under appeal: same province for provincial/district courts; a high court
            # hears appeals against provincial-level first-instance judgments only
            sc, hc = court_of.get(r["src_id"]), court_of.get(hit[0])
            sp, hp = prov_of.get(sc), hit[3]
            sk, hk = kind_of.get(sc), kind_of.get(hc)
            if sk in ("provincial", "district", "regional") and sp and hp and sp != hp:
                cs["dropped:first_instance_other_province"] += 1
                hit = None
            elif (sk == "high" and hk in ("district", "regional")) or (sk == "provincial" and hk in ("high", "supreme")):
                cs["dropped:first_instance_wrong_level"] += 1
                hit = None
            elif sc and sc == hc and (sk in ("high", "supreme") or "PT" in (code_of.get(r["src_id"]) or "").upper()):
                # an appellate or review judgment never reviews a first-instance judgment of its own court
                cs["dropped:first_instance_same_court"] += 1
                hit = None
        if hit:
            cs["resolved:" + how] += 1
            edges.append({"src_id": r["src_id"], "dst_id": hit[0], "dst_kind": "decision", "cited_id": r["cited_id"],
                          "role": r["role"], "method": how})
    ce = pl.DataFrame(edges, infer_schema_length=None, schema={"src_id": pl.Utf8, "dst_id": pl.Utf8, "dst_kind": pl.Utf8,
                                                               "cited_id": pl.Utf8, "role": pl.Utf8, "method": pl.Utf8})
    pa = pe.filter(pl.col("relation") == "applies").select(pl.col("src_id"), pl.col("precedent_id").alias("dst_id"),
                                                            pl.lit("precedent").alias("dst_kind"), pl.col("precedent_number").alias("cited_id"),
                                                            pl.lit(None, dtype=pl.Utf8).alias("role"), pl.col("method"))
    ce = pl.concat([ce, pa], how="diagonal_relaxed").unique(subset=["src_id", "dst_id"], maintain_order=True)
    sel = pe.filter(pl.col("relation") == "selected_from").select(pl.col("precedent_id").alias("src_id"), pl.col("src_id").alias("dst_id"), "method")
    rep["case_citations"] = {"records": case.height, **{k: v for k, v in cs.items()},
                             "edges_decision_to_decision": int((ce["dst_kind"] == "decision").sum()),
                             "edges_decision_to_precedent": int((ce["dst_kind"] == "precedent").sum()),
                             "records_with_context_window": int(case["ctx_window"].is_not_null().sum()),
                             "records_with_context_date": int(case["ctx_date"].is_not_null().sum()),
                             "wall_s": round(time.time() - t1, 1)}
    n_law = law.group_by("decision_id").len().rename({"len": "n_law_edges"})
    n_case = ce.group_by("src_id").len().rename({"src_id": "decision_id", "len": "n_case_edges"})
    dec = dec.join(n_law, on="decision_id", how="left").join(n_case, on="decision_id", how="left").with_columns(
        pl.col("n_law_edges").fill_null(0), pl.col("n_case_edges").fill_null(0))
    rep["decisions"] = dec.height
    rep["decisions_by_source"] = dict(Counter(dec["source"].to_list()))
    rep["decisions_by_kind"] = dict(Counter(dec["decision_kind"].to_list()))
    rep["decisions_with_court"] = int(dec["court_id"].is_not_null().sum())
    rep["courts"] = courts.height
    rep["precedents"] = precedents.height
    rep["precedents_with_source_decision"] = int(precedents.filter(pl.col("source_decision_ids").list.len() > 0).height)
    rep["decision_provision_edges"] = law.height
    rep["decision_provision_edges_article_level"] = int(law["dst_article_id"].is_not_null().sum())
    rep["wall_courts_s"] = round(time.time() - t0, 1)
    rep["decisions_issued_date_check"] = dict(Counter(dec["issued_date_check"].to_list()))
    dec = dec.sort("decision_id")
    courts = courts.sort(["n_decisions", "court_id"], descending=[True, False])
    return dec, courts, precedents, law, ce, sel
