#!/usr/bin/env python3
"""Step 1 - Acquisition: download the `documents` parquet files of the six
tmquan Vietnamese legal datasets into the shared Hugging Face cache.

Why: every later step (profiling, cleaning, chunking, evaluation) reads these
parquet files; pinning the repo revision makes the run reproducible.

Output: $R/data/download_manifest.json  (one record per dataset: revision,
files, bytes on disk, rows from parquet metadata, wall seconds).
"""
import json, os, sys, time, glob
from pathlib import Path

R = Path(os.environ.get("R", "/path/to/vnlegal"))
os.environ.setdefault("HF_HOME", str(R / "hf"))
os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")   # more parallel xet chunk fetches

import huggingface_hub as hfh
from huggingface_hub import HfApi, snapshot_download
import pyarrow.parquet as pq

DATASETS = {
    # repo                               : allow_patterns (documents config only)
    "tmquan/thuvienphapluat-vn-vbpl": ["documents-*.parquet"],
    "tmquan/thuvienphapluat-vn-hdpl": ["documents-*.parquet"],
    "tmquan/thuvienphapluat-vn-tnpl": ["documents.parquet"],
    "tmquan/thuvienphapluat-vn-htpl": ["documents.parquet"],
    "tmquan/anle-toaan-gov-vn":       ["documents-*.parquet"],
    # 1.54M court judgments: ONE shard of 16 is enough for a secondary-source demo
    "tmquan/cbba-toaan-gov-vn":       ["documents-00000-of-00016.parquet"],
}

def main():
    api = HfApi()
    try:
        import hf_xet; xet_ver = getattr(hf_xet, "__version__", "installed")
    except Exception:
        xet_ver = None
    out = {"huggingface_hub": hfh.__version__, "hf_xet": xet_ver,
           "HF_HOME": os.environ["HF_HOME"], "datasets": {}}
    t_all = time.time()
    for repo, pats in DATASETS.items():
        info = api.dataset_info(repo, files_metadata=True)
        remote = {s.rfilename: s.size for s in info.siblings if s.rfilename.startswith("documents")}
        t0 = time.time()
        local = snapshot_download(repo_id=repo, repo_type="dataset", revision=info.sha,
                                  allow_patterns=pats + ["README.md"], max_workers=16)
        wall = time.time() - t0
        files = sorted(glob.glob(os.path.join(local, "documents*.parquet")))
        nbytes = sum(os.path.getsize(os.path.realpath(f)) for f in files)
        rows = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
        rec = {"revision": info.sha, "local_dir": local, "n_files": len(files),
               "bytes": nbytes, "rows": rows, "wall_s": round(wall, 1),
               "MB_per_s": round(nbytes / 1e6 / max(wall, 1e-6), 1),
               "remote_documents_files": len(remote),
               "remote_documents_bytes": sum(v or 0 for v in remote.values())}
        out["datasets"][repo] = rec
        print(f"{repo:36s} files={len(files):3d}/{len(remote):3d} bytes={nbytes:>14,} rows={rows:>10,} wall={wall:7.1f}s", flush=True)
    out["total_wall_s"] = round(time.time() - t_all, 1)
    out["total_bytes"] = sum(d["bytes"] for d in out["datasets"].values())
    (R / "data").mkdir(parents=True, exist_ok=True)
    with open(R / "data" / "download_manifest.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"TOTAL bytes={out['total_bytes']:,} wall={out['total_wall_s']}s")

if __name__ == "__main__":
    main()
