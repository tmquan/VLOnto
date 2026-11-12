"""The trace build as run on 2026-11-12, in order. Language-model steps (English law names, question glosses, two term
names) read cache/*.json when present; otherwise they need an `llm(requests)` callable (the session used the host's
model API; prompts are in build_traces.py). Paths come from the environment: TR (work folder with kg/ from kg_edges.py;
the outputs go to $TR/out/traces), R (rebuilt corpus), R_PREFIX (corpus with the 616 number fixes reverted), HF
(downloaded shards). The caches are read from cache/ next to this file. A title that the gloss model flagged as holding a
person name is kept in cache/glosses.json only as the sha256 of its text (it is never published), which is enough to
skip it exactly as the session did."""
import hashlib, json, os, shutil, sys
R, RP, HF, TR = (os.environ[k] for k in ("R", "R_PREFIX", "HF", "TR"))
CODE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, CODE)
import trace_lib as T
import build_traces as BT

ctx = BT.load(R, HF, TR, RP)
assert BT.check_outcomes_vs_gold(ctx, os.path.join(R, "eval", "gold_all.parquet"))["different"] == 0
BT.prepare(ctx)
cache = lambda n: json.load(open(os.path.join(CODE, "cache", n), encoding="utf-8"))
gloss, law, term_en = cache("glosses.json"), cache("law_names_en.json"), cache("term_names_en.json")
flag_titles = {g["title_vi"] for g in gloss.values() if g.get("has_person_name") and "title_vi" in g}
flag_sha = {g["title_sha256"] for g in gloss.values() if g.get("has_person_name") and "title_sha256" in g}
sha = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()
_hits = T.person_name_hits
T.person_name_hits = lambda title: _hits(title) + (["(model flag)"] if ((title or "").strip() in flag_titles or
                                                                        sha((title or "").strip()) in flag_sha) else [])
BT.T.person_name_hits = T.person_name_hits
sel = BT.select(ctx)
assert all(p["qa_id"] in gloss for v in sel.values() for p in v), "new picks need glosses (BT.gloss_prompt + GLOSS_TOOL)"
ctx["gloss"] = gloss
ctx["law_en"] = {d: (v["name_en"], v["source"]) for d, v in law.items()}
comp = BT.finalize(BT.build_all(ctx, sel), term_en)
index = json.load(open(os.path.join(CODE, "cache", "index_header.json"), encoding="utf-8"))   # version, method, classes, totals
index["areas"] = [{**{k: comp[a]["area"][k] for k in ("id", "label_vi", "label_en", "n_qas", "n_qas_with_links", "n_traces")}, "file": f"{a}.json"}
                  for a in sorted(comp, key=lambda x: -comp[x]["area"]["n_qas"])]
out = os.path.join(TR, "out", "traces")
shutil.rmtree(out, ignore_errors=True)
print(BT.write_outputs(out, BT.nfc_all(index), comp))
# then: copy $TR/out/traces/*.json to $V/build/traces/; scripts/site/build_site.py writes site/data/traces/*.js
