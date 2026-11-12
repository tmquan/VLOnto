#!/usr/bin/env python3
"""Write $R_PREFIX/data/clean/docs_clean.parquet = $R/data/clean/docs_clean.parquet with the 616 fix_docnums.py fixes
reverted (old number, key and title from docnum_fixes.csv): the document numbers the node's v1 gold resolver saw.
Usage: R=<rebuilt root> R_PREFIX=<new root> python revert_fixes.py  (then link $R/data/chunks and copy the manifest + code)."""
import csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polars as pl
import vnlegal_text as V
R, RP = os.environ["R"], os.environ["R_PREFIX"]
dc = pl.read_parquet(os.path.join(R, "data", "clean", "docs_clean.parquet"))
m = {r["id"]: r for r in csv.DictReader(open(os.path.join(R, "data", "clean", "docnum_fixes.csv"), encoding="utf-8"))}
old = {i: (r["old_doc_number"] or None) for i, r in m.items()}
upd = pl.DataFrame({"id": list(m), "_num": [old[i] for i in m], "_title": [m[i]["old_title_vi"] or None for i in m],
                    "_key": [V.docnum_key(old[i]) if old[i] else None for i in m]},
                   schema={"id": pl.Utf8, "_num": pl.Utf8, "_title": pl.Utf8, "_key": pl.Utf8})
hit = pl.col("id").is_in(list(m))
dc2 = (dc.join(upd, on="id", how="left")
       .with_columns(pl.when(hit).then(pl.col("_num")).otherwise(pl.col("doc_number")).alias("doc_number"),
                     pl.when(hit).then(pl.col("_key")).otherwise(pl.col("doc_number_key")).alias("doc_number_key"),
                     pl.when(hit).then(pl.col("_title")).otherwise(pl.col("title_vi")).alias("title_vi"))
       .drop(["_num", "_title", "_key"]))
os.makedirs(os.path.join(RP, "data", "clean"), exist_ok=True)
dc2.write_parquet(os.path.join(RP, "data", "clean", "docs_clean.parquet"))
print("reverted", len(m), "rows", dc2.height)
