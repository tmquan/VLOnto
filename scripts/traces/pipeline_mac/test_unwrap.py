#!/usr/bin/env python3
"""Check unwrap_fast.unwrap_lines_fast == vnlegal_text.unwrap_lines on 1,500 random tier 0-1 documents plus the 25
largest. Usage: HF=<folder with thuvienphapluat-vn-vbpl/documents-*.parquet> python test_unwrap.py"""
import glob, os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import polars as pl
import vnlegal_text as V
from unwrap_fast import unwrap_lines_fast
fs = sorted(glob.glob(os.path.join(os.environ["HF"], "thuvienphapluat-vn-vbpl", "documents-*.parquet")))
lf = pl.scan_parquet(fs).select(["id", "tier", "is_english", "vn_chars", "vn_text"]).filter(pl.col("tier") <= 1).filter(~pl.col("is_english"))
ids = lf.select("id", "vn_chars").collect()
random.seed(5)
pick = set(random.sample(ids["id"].to_list(), 1500)) | set(ids.sort("vn_chars", descending=True, nulls_last=True).head(25)["id"].to_list()) | {"643624", "52244", "333670"}
d = lf.filter(pl.col("id").is_in(list(pick))).collect()
bad = 0; t_old = t_new = 0.0
for r in d.iter_rows(named=True):
    t = V.basic_clean(r["vn_text"] or "")
    if not t:
        continue
    a0 = time.time(); a = V.unwrap_lines(t); a1 = time.time(); b = unwrap_lines_fast(t); a2 = time.time()
    t_old += a1 - a0; t_new += a2 - a1
    bad += a != b
print("docs", d.height, "diffs", bad, f"old {t_old:.1f}s new {t_new:.1f}s")
