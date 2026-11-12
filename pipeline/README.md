# Upstream corpus pipeline

These scripts come from the Vietnamese legal-assistant project that VLOnto builds on. They download the source
datasets at pinned revisions and produce the processed corpus that `vlonto` reads: cleaned in-scope documents,
article chunks, the validity map (change relations between documents) and the Q&A citation labels. They need only a
CPU environment. Release v1 (1.0.0) uses the four thuvienphapluat.vn datasets (vbpl, hdpl, tnpl, htpl); the court
datasets (anle-toaan-gov-vn, cbba-toaan-gov-vn) are planned for v2 and are downloaded only with
`VLONTO_INCLUDE_COURTS=1` (without them `chunk.py` skips the anle chunks and `profile_data.py` the court profiles).

```bash
export R=/path/to/workdir HF_HOME=$R/hf      # working directory and Hugging Face cache
mkdir -p $R/code && cp pipeline/*.py pipeline/*.sh $R/code/ && cd $R/code
bash setup_env.sh                             # uv environment $R/envs/data (CPU)
PY=$R/envs/data/bin/python
$PY download.py                               # datasets at the revisions in download_manifest.json
$PY profile_data.py                           # optional: field profile of the raw data
$PY clean.py                                  # -> $R/data/clean/docs_clean.parquet (scope funnel, text normalisation)
$PY chunk.py                                  # -> $R/data/chunks/{chunks,doc_struct,anle_chunks}.parquet
$PY fix_docnums.py                            # repairs document numbers taken from URL slugs
AS_OF=2026-11-08 STATUS_FIRST=1 SAMPLE_SEED=31 $PY validity.py   # -> $R/data/validity/{relations,validity}.parquet
$PY eval_retrieval.py gold                    # -> $R/eval/gold_all.parquet (Q&A -> article labels)
```

Then build the knowledge graph with `python -m vlonto.cli all` from `vlonto/` (see the main README and the playbook,
section 5). `AS_OF` fixes the date at which document validity is evaluated; VLOnto 0.1.0 and 1.0.0 use 2026-11-08.
Always set `NPROC` (clean, chunk and validity default to 200 worker processes). Since 1.0.0 `validity.py` writes its
tables in a fixed row order, so repeated runs give identical files.

| File | Role |
|---|---|
| `setup_env.sh` | creates the CPU environment with uv |
| `download.py` | downloads the parquet shards at pinned revisions; writes `download_manifest.json` |
| `download_manifest.json` | VLOnto 1.0.0: revisions, files (bytes, rows, sha256), card sha256 of the four source datasets; the court datasets planned for v2 |
| `profile_data.py` | profiles fields and text quality |
| `vnlegal_text.py` | shared text library: Unicode normalisation, split-syllable repair, header parsing, number keys |
| `clean.py` | scope funnel (normative types, tiers 0-1) and text cleaning |
| `chunk.py` | article parsing and chunking |
| `fix_docnums.py` | document-number repair |
| `validity.py` | change relations (rules v7) and per-document validity |
| `eval_retrieval.py`, `bm25_vi.py` | the `gold` stage resolves Q&A citations to articles; the other stages evaluate retrieval and need a GPU environment |
