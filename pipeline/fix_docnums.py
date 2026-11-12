#!/usr/bin/env python3
"""Step 3b - repair document numbers that fell back to the URL slug.

clean.py parsed 'Số: <number>' from the raw header; when PDF extraction split the
syllable ('S ố:') or the digits ('1 56 /2018'), the number fell back to the metadata
slug, e.g. '259/2026/ND-CP-TUYEN-DUNG-SU-DUNG-VA-QUAN-LY-VIEN-CHUC'.
This script re-parses the header of every in-scope document whose number did not
come from the header (vnlegal_text.parse_header now tolerates both artefacts) and
  - accepts the header number only if its 'N/YYYY' prefix equals the slug's prefix;
  - otherwise, for slug numbers with appended words, truncates to N/YYYY/TYPE-ISSUER
    (Đ restored for known codes).
It patches docs_clean.parquet and chunks.parquet in place (doc_number, doc_number_key,
doc_number_src, title_vi, chunk context) and writes docnum_fixes.csv.
Re-run validity.py afterwards. Embeddings/BM25 are NOT recomputed (context strings
changed only in the number/title prefix).
"""
import os, re, sys, json, glob
from collections import Counter
import polars as pl
R = os.environ["R"]; sys.path.insert(0, os.path.join(R, "code"))
import vnlegal_text as V

SLUG = set("""VE CUA VA HUONG DAN QUY DINH SUA DOI BO SUNG THI HANH NAM LUAT CHI TIET BAN CAC CHO TRONG VIEC NGUOI THUC HIEN
CONG TAC TO CHUC HOAT DONG QUAN LY NHA NUOC TAI DAT THUE PHI LE BAI THAY THE MOT SO DIEU NGHI QUYET THONG TU TRA AN DUNG XAY
GIAO DUC Y TE PHAT TRIEN KHOAN MUC CAP GIAY PHEP DANH SAN PHAM HANG HOA XU VI CHINH TRINH THU TUC THAM DU QUOC GIA""".split())
ISSUER = {"CP": "CP", "TTG": "TTg", "BTC": "BTC", "BYT": "BYT", "BCA": "BCA", "BQP": "BQP", "BNV": "BNV", "BTP": "BTP", "BXD": "BXD",
          "BCT": "BCT", "BKHDT": "BKHĐT", "BGDDT": "BGDĐT", "BLDTBXH": "BLĐTBXH", "BNNPTNT": "BNNPTNT", "BNNMT": "BNNMT", "BTNMT": "BTNMT",
          "BGTVT": "BGTVT", "BVHTTDL": "BVHTTDL", "BTTTT": "BTTTT", "BKHCN": "BKHCN", "NHNN": "NHNN", "TANDTC": "TANDTC",
          "VKSNDTC": "VKSNDTC", "UBDT": "UBDT", "TTCP": "TTCP", "KTNN": "KTNN", "BNG": "BNG", "VPCP": "VPCP", "HDTP": "HĐTP",
          "UBTVQH": "UBTVQH", "QH": "QH", "BDTTG": "BDTTG", "UBND": "UBND", "HDND": "HĐND", "BDTDT": "BDTDT"}
TYPE = {"ND": "NĐ", "QD": "QĐ", "NQ": "NQ", "TT": "TT", "TTLT": "TTLT", "NQLT": "NQLT", "L": "L", "PL": "PL", "CT": "CT"}

def is_garbage(x):
    if not x or x.count("/") < 2:
        return False
    segs = x.split("/", 2)[2].split("-")
    return len(segs) >= 4 and sum(s in SLUG for s in segs) >= 2

def prefix(num):
    k = V.docnum_key(num) or ""
    m = re.match(r"^(\d+[A-Z]?/\d{4})/", k)
    return m.group(1) if m else None

def truncate(x):
    n, y, code = x.split("/", 2)
    segs = code.split("-")
    out = [TYPE.get(segs[0], segs[0])]
    for s in segs[1:]:
        if re.match(r"^UBTVQH\d+$|^QH\d+$", s) or s in ISSUER:
            out.append(ISSUER.get(s, s))
            if out[0] not in ("TTLT", "NQLT"):
                break
        else:
            break
    return f"{n}/{y}/" + "-".join(out) if len(out) >= 2 else None

def main():
    man = json.load(open(os.path.join(R, "data", "download_manifest.json")))
    vb = man["datasets"]["tmquan/thuvienphapluat-vn-vbpl"]["local_dir"]
    dc_path = os.path.join(R, "data", "clean", "docs_clean.parquet")
    dc = pl.read_parquet(dc_path)
    cand = dc.filter(pl.col("excluded_reason").is_null() & (pl.col("doc_number_src") != "header"))
    ids = cand["id"].to_list()
    raw = (pl.scan_parquet(sorted(glob.glob(vb + "/documents-*.parquet"))).filter(pl.col("id").is_in(ids))
           .select(["id", pl.col("vn_text").str.slice(0, 6000)]).collect())
    head = dict(zip(raw["id"].to_list(), raw["vn_text"].to_list()))
    fixes, st = [], Counter()
    for r in cand.iter_rows(named=True):
        old = r["doc_number"]
        hdr = V.parse_header(V.basic_clean(head.get(r["id"]) or ""), r["doc_type"])
        new, src, core = hdr["doc_number"], "header_v2", hdr["title_core"] or r["title_core"]
        yr = str(r.get("year") or "") or (r.get("issue_date") or "")[:4]
        if old is None and new and V.has_year_format(new) and not is_garbage(new) and prefix(new) and prefix(new).endswith("/" + yr):
            src = "header_v2_was_missing"            # no number before; header number with matching issue year
        elif not (new and V.has_year_format(new) and old and prefix(new) == prefix(old) and not is_garbage(new)):
            new = None
        if new is None and is_garbage(old):
            new, src, core = truncate(old), "metadata_truncated", r["title_core"]
        if not new or new == old or (old is None and src != "header_v2_was_missing"):
            st["unchanged" if not is_garbage(old) else "garbage_unfixed"] += 1
            continue
        st[src] += 1
        fixes.append({"id": r["id"], "doc_type": r["doc_type"], "old_doc_number": old, "new_doc_number": new, "method": src,
                      "old_title_vi": r["title_vi"], "new_title_vi": V.make_title(r["doc_type"], new, core), "was_garbage": is_garbage(old)})
    fx = pl.DataFrame(fixes, infer_schema_length=None)
    fx.write_csv(os.path.join(R, "data", "clean", "docnum_fixes.csv"))
    m = {f["id"]: f for f in fixes}
    # docs_clean
    upd = pl.DataFrame({"id": list(m), "_num": [m[i]["new_doc_number"] for i in m], "_src": [m[i]["method"] for i in m],
                        "_title": [m[i]["new_title_vi"] for i in m], "_key": [V.docnum_key(m[i]["new_doc_number"]) for i in m]})
    dc2 = (dc.join(upd, on="id", how="left")
             .with_columns(pl.coalesce("_num", "doc_number").alias("doc_number"), pl.coalesce("_src", "doc_number_src").alias("doc_number_src"),
                           pl.coalesce("_title", "title_vi").alias("title_vi"), pl.coalesce("_key", "doc_number_key").alias("doc_number_key"))
             .drop(["_num", "_src", "_title", "_key"]))
    assert dc2.height == dc.height
    dc2.write_parquet(dc_path + ".tmp"); os.replace(dc_path + ".tmp", dc_path)
    # chunks
    cp = os.path.join(R, "data", "chunks", "chunks.parquet")
    ch = pl.read_parquet(cp)
    n_before = ch.height
    rows = ch.filter(pl.col("doc_id").is_in(list(m)))
    ctx = [(c or "").replace(m[d]["old_title_vi"] or "\x00", m[d]["new_title_vi"]).replace(m[d]["old_doc_number"], m[d]["new_doc_number"])
           for d, c in zip(rows["doc_id"].to_list(), rows["context"].to_list())]
    cu = pl.DataFrame({"chunk_id": rows["chunk_id"], "_num": [m[d]["new_doc_number"] for d in rows["doc_id"].to_list()],
                       "_title": [m[d]["new_title_vi"] for d in rows["doc_id"].to_list()], "_ctx": ctx})
    ch2 = (ch.with_row_index("_row").join(cu, on="chunk_id", how="left").sort("_row").drop("_row")
             .with_columns(pl.coalesce("_num", "doc_number").alias("doc_number"), pl.coalesce("_title", "title_vi").alias("title_vi"),
                           pl.coalesce("_ctx", "context").alias("context"))
             .drop(["_num", "_title", "_ctx"]))
    assert ch2.height == n_before and ch2["chunk_id"].to_list() == ch["chunk_id"].to_list()
    ch2.write_parquet(cp + ".tmp"); os.replace(cp + ".tmp", cp)
    rep = {"candidates_non_header": cand.height, "garbage_before": int(sum(is_garbage(x) for x in cand["doc_number"].to_list())),
           "fixed": len(fixes), "by_method": dict(st), "chunks_patched": rows.height,
           "examples": fx.select(["id", "old_doc_number", "new_doc_number", "method", "new_title_vi"]).head(8).to_dicts() if len(fixes) else []}
    dcf = dc2.filter(pl.col("excluded_reason").is_null())
    rep["garbage_after"] = int(sum(is_garbage(x) for x in dcf["doc_number"].to_list()))
    json.dump(rep, open(os.path.join(R, "data", "clean", "docnum_fix_report.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
