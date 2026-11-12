# Question traces: build code

Builds `build/traces/index.json` and one `build/traces/<area id>.json` per legal area: for each of the 27 legal areas of
`thuvienphapluat-vn-hdpl`, the 20 articles cited by the most answers of that area and one representative answer each,
traced like Fig. 1 and Fig. 6 of the paper (arXiv:2611.11426): question → answer → cited provision → clause / article →
section → chapter → law, the law's vbpl record, the terms the question names with their defining clauses, the area and
other answers of the area that cite the same law. The website turns these files into the Traces page:
`scripts/site/build_site.py` reads `$V/build/traces/` and writes `site/data/traces/*.js` with the build-time drawings
(`scripts/site/trace_site.py`, `scripts/site/trace_layout.py`).

## Inputs

| Input | What | Pinned by |
|---|---|---|
| `tmquan/thuvienphapluat-vn-vbpl` | documents, structure, numbers, English record titles | revision `705ade585384108ded5fc30f40a06fe110bdff22` |
| `tmquan/thuvienphapluat-vn-hdpl` | Q&As, citations, areas, titles (answers are read in memory for the text match only) | revision `e814ecbfa1a1c0c32727c2f2ad2498d52f04b8bd` |
| `tmquan/thuvienphapluat-vn-tnpl` | term names (definitions are read in memory to validate defining clauses only) | revision `f94d1e24852f233e85330c6d5093f43adbddde29` |
| `$R` | the pipeline outputs: `data/clean/docs_clean.parquet`, `data/chunks/chunks.parquet` (after `fix_docnums.py`), `eval/gold_all.parquet` (v1 labels) | the steps below |
| `$R_PREFIX` | the same corpus with the 616 document-number fixes reverted (what the v1 gold resolver saw) and the pipeline code in `code/` | the steps below |
| `$TR/kg/` | KG-style tables `articles`, `structure`, `edges_qa_article` (34,869 rows), `edges_qa_document`, `qas` | `kg_edges.py` |
| `cache/` | the language-model outputs of the build session (see below) | this folder |

The revisions are those of `index.json` (`source_revisions`), of `docs/licence_policy.md` and of the KG build.

## Steps

`$HF` = folder with the downloaded shards (`$HF/<dataset>/...parquet`), `$R` = work root laid out like the node
(`$R/code`, `$R/data`, `$R/eval`), `$R_PREFIX` = a second root, `$TR` = a work folder.

| Step | Command |
|---|---|
| layout | copy `pipeline/*.py` and `scripts/traces/pipeline_mac/*.py` to `$R/code`; write `$R/data/download_manifest.json` with `local_dir = $HF/<dataset>` (example: `pipeline_mac/download_manifest.mac.json`) |
| clean | `OLD_HEADER=1 R=$R NPROC=8 python $R/code/clean_mac.py` (`clean.py` with per-shard scans, streamed workers and the linear `unwrap_fast.py`; `OLD_HEADER=1` = `parse_header` without the two later PDF-artefact substitutions, as on the node) |
| chunk | `R=$R NPROC=8 python $R/code/chunk_mac.py` |
| fix numbers | `R=$R python $R/code/fix_docnums.py` |
| gold v1 | `R=$R R_PREFIX=$R_PREFIX python $R/code/revert_fixes.py`; link `$R_PREFIX/data/chunks` → `$R/data/chunks`; copy the manifest and `$R/code` to `$R_PREFIX`; `R=$R_PREFIX EV_OUT=$R/eval python $R_PREFIX/code/gold_v1.py` (the resolver that stopped at a line break, against the numbers before `fix_docnums.py`: 22,523 Q&As, as the node) |
| KG edges | `TR=$TR R=$R HF_LOCAL=$HF python scripts/traces/kg_edges.py` → `$TR/kg/*.parquet` |
| traces | `TR=$TR R=$R R_PREFIX=$R_PREFIX HF=$HF python scripts/traces/make_traces_session.py` → `$TR/out/traces/{index.json,<area>.json}` |
| site | copy `$TR/out/traces/*.json` to `$V/build/traces/`, then `python scripts/site/build_site.py --root $V` |

`make_traces_session.py` replays the build session in order: load and check the citation outcomes against
`gold_all.parquet` (0 differences), rank and select, attach the cached English names and glosses, build, finalise and
write. It uses the `vlonto` package of this repository (`vlonto/`, as of VLOnto 0.1.0) and runs as one process. With the
inputs above it reproduces the 28 JSON files byte for byte (checked 2026-11-12, see below). New picks (other inputs or
rules) need new glosses: `build_traces.gloss_prompt` and `GLOSS_TOOL` give the prompt and the tool schema.

## Cached model outputs (`cache/`)

| File | Content | Checked |
|---|---|---|
| `glosses.json` | 539 entries keyed by hdpl id: for the 538 traced questions the title as published on thuvienphapluat.vn, a machine-assisted English gloss (≤ 15 words) and the model's person-name flag; one candidate title that the model flagged as holding a person name is kept only as the sha256 of its text, so the build skips it again without publishing it | NFC; no answer text; no person names |
| `law_names_en.json` | English names of the 86 codes, laws and ordinances of the traces with their source (vbpl English record of the same number, normalised to the paper's style; or machine-assisted from the Vietnamese title) | names only |
| `term_names_en.json` | 2 English term names missing in tnpl (machine-assisted) | names only |
| `index_header.json` | version, method notes, the class legend and the totals of `index.json` | no source text |

No cache holds answer text, article / clause / point text, glossary definitions or person names. The build reads answer
and article texts in memory to compute the word 5-gram match and writes only the scores.

## Outputs and what they contain

Per trace: question (hdpl id, URL, date, title as published, English gloss), the ranked article and its counts, the law
(number, Vietnamese and English names, vbpl status string, URL), nodes with provenance (dataset, record, method,
status), links, paths with match scores and methods, terms with their defining clause and match, call-out choices and
unresolved citations. The site build drops from this, before publishing: the citations as written in the answers
(`paths[].refs`, `unresolved_citations[].ref` / `law_name`), the titles of the other answers (shown as "Câu hỏi #id ·
Question #id"), and the free text that the vbpl status field carries after the status. See `docs/licence_policy.md`.

## Reproduction check (2026-11-12)

Two runs on macOS (Python 3.11.18, polars 2.1.0, pyarrow 26.0.1, one process) from the pipeline outputs of the trace
build (`$R`, `$R_PREFIX`, `$TR/kg`) and the shards at the pinned revisions: 32 s wall each (exit status 0 recorded for the second run); the 28 files
(8,603,026 bytes) are byte-identical to the published build (`cmp`, 28 of 28 in both runs). `index.json` has sha256
`e8ed286bd43291a86e7422b7c1eaad50086903ba191b9404cfb670c040deb4e5`.
