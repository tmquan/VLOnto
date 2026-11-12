#!/usr/bin/env python3
"""Step 7 - Retrieval evaluation on held-out hdpl questions.

Stages (python eval_retrieval.py <stage>):
  gold    resolve hdpl citations to (in-scope doc_id, article) and select a
          stratified held-out set of ~1,000 questions (published >= 2024 first)
  run     BM25 (syllable / +bigram), dense (Nemotron-3-Embed-8B 4096-d and the
          1024-d Matryoshka slice), hybrid RRF -> top-100 chunks per query
  rerank  rerank hybrid top-30 with nvidia/Nemotron-3.5-Rerank-8B-BF16
          (sentence-transformers CrossEncoder), one process per GPU
  metrics recall@1/5/10/20 (hit = >=1 gold item in top-k), fractional recall,
          MRR@100 at article and document level -> retrieval_metrics.csv
"""
import os, sys, re, json, time, random, glob
from collections import Counter, defaultdict
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vnlegal_text as V

R = os.environ.get("R", "/path/to/vnlegal")
EV = os.path.join(R, "eval"); os.makedirs(EV, exist_ok=True)
MAN = json.load(open(os.path.join(R, "data", "download_manifest.json")))
LAWTYPES = r"(Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết liên tịch|Nghị quyết|Pháp lệnh|Quyết định|Hiến pháp)"
NUMPAT = r"\d{1,5}[a-z]?/\d{4}/[A-ZĐ][A-ZĐa-z0-9]*(?:[-/][A-ZĐa-z0-9]+)*|\d{1,5}/[A-ZĐ][A-ZĐ0-9]*-[A-ZĐa-z0-9]+(?:-[A-ZĐa-z0-9]+)*"
NAME_TYPES = {"Bộ luật", "Luật", "Pháp lệnh", "Hiến pháp"}
N_HELDOUT = int(os.environ.get("N_HELDOUT", "1000"))

# ------------------------------------------------------------------ gold
def load_docs():
    d = pl.read_parquet(os.path.join(R, "data", "clean", "docs_clean.parquet"),
                        columns=["id", "doc_type", "doc_number", "doc_number_key", "title_core", "title_vi", "issue_date", "effective_date_meta"])
    by_key = defaultdict(list); by_name = defaultdict(list)
    for r in d.iter_rows(named=True):
        if r["doc_number_key"]:
            by_key[r["doc_number_key"]].append(r)
        if r["doc_type"] in NAME_TYPES and r["title_core"] and not re.match(r"(?i)(sửa đổi|bổ sung|về |quy định)", r["title_core"]):
            by_name[(r["doc_type"], V.name_key(r["title_core"]))].append(r)
    return d, by_key, by_name

def pick_version(cands, year=None, pub=None):
    if year:
        c = [r for r in cands if r["issue_date"] and r["issue_date"][:4] == str(year)]
        if c:
            return c[0], "year"
        c = [r for r in cands if r["effective_date_meta"] and r["effective_date_meta"][:4] == str(year)]
        if c:
            return c[0], "year_effective"
        return None, None
    if pub:
        c = [r for r in cands if r["issue_date"] and r["issue_date"] <= pub]
        c2 = [r for r in c if (r["effective_date_meta"] or r["issue_date"]) <= pub]
        c = c2 or c
        if c:
            return max(c, key=lambda r: (r["effective_date_meta"] or r["issue_date"])), "in_force_at_published_date"
    return None, None

def resolve_name(by_name, typ, name, year, pub):
    k = (typ, V.name_key(name))
    cands = by_name.get(k)
    method = "name"
    if not cands:
        pref = [key for key in by_name if key[0] == typ and key[1].startswith(V.name_key(name)) and len(V.name_key(name)) >= 4]
        if len({p[1] for p in pref}) == 1:
            cands = by_name[pref[0]]; method = "name_prefix"
    if not cands:
        return None, None
    r, how = pick_version(cands, year, pub)
    return (r, f"{method}+{how}") if r else (None, None)

def explicit_mention(answer, article):
    """Find 'Điều <article> <law reference>' in the answer text."""
    for m in re.finditer(r"Điều\s+%s(?![\w/])" % re.escape(article), answer):
        win = " ".join(answer[m.end(): m.end() + 240].split())      # hyperlink artefacts put the law name on its own line
        win = re.split(r"(?<=[a-zđàáảãạ\)])\.\s", win)[0]
        mm = re.match(r"^\s*(?:,\s*)?(?:của\s+)?" + LAWTYPES + r"\s+(?:số\s+)?(" + NUMPAT + ")", win)
        if mm:
            return ("num", mm.group(1), mm.group(2), None)
        mm = re.match(r"^\s*(?:,\s*)?(?:của\s+)?" + LAWTYPES + r"\s+([^\d\n,.;:()“”\"]{2,80}?)\s+(?:năm\s+)?(\d{4})(?!\d|/)", win)
        if mm:
            return ("name_year", mm.group(1), mm.group(2).strip(), mm.group(3))
        mm = re.match(r"^\s*(?:,\s*)?(?:của\s+)?" + LAWTYPES + r"\s+([^\d\n,.;:()“”\"]{2,80}?)\s*(?:quy định|như sau|về|thì|có|được|nêu|,|\.|;|:|\(|$)", win)
        if mm and mm.group(1) in NAME_TYPES:
            return ("name", mm.group(1), mm.group(2).strip(), None)
    return None

def stage_gold():
    t0 = time.time()
    d, by_key, by_name = load_docs()
    ch = pl.read_parquet(os.path.join(R, "data", "chunks", "chunks.parquet"), columns=["doc_id", "article_no"])
    arts = set(zip(ch["doc_id"].to_list(), ch["article_no"].to_list()))
    fs = sorted(glob.glob(os.path.join(MAN["datasets"]["tmquan/thuvienphapluat-vn-hdpl"]["local_dir"], "documents-*.parquet")))
    h = pl.read_parquet(fs, columns=["id", "question", "answer", "area", "published_date", "citations", "url", "content_flag_summary"])
    stats = Counter(); rows = []
    for q in h.iter_rows(named=True):
        cits = q["citations"] or []
        if not cits:
            continue
        pub = (q["published_date"] or "")[:10]
        ans = V.nfc(q["answer"] or "")
        docs_of_type = defaultdict(set)
        for c in cits:
            if c["kind"] == "document" and c["id"]:
                for r in by_key.get(V.docnum_key(c["id"]), []):
                    docs_of_type[c["law_type"]].add(r["id"])
        gold, gold_docs_only = [], set()
        for c in cits:
            if c["kind"] == "document":
                if c["id"]:
                    rr = by_key.get(V.docnum_key(c["id"]), [])
                    if rr:
                        gold_docs_only.add(rr[0]["id"])
                continue
            art = (c["article"] or "").strip()
            if not art or not re.match(r"^\d{1,3}[a-zđ]?$", art):
                stats["provision_bad_article"] += 1; continue
            stats["provisions"] += 1
            typ, name, year = c["law_type"], (c["law_name"] or "").strip(), c["year"]
            res, method = None, None
            ex = explicit_mention(ans, art)
            if ex:
                if ex[0] == "num":
                    rr = by_key.get(V.docnum_key(ex[2]), [])
                    if rr:
                        res, method = rr[0], "answer_text:number"
                elif ex[1] in NAME_TYPES:
                    res, how = resolve_name(by_name, ex[1], ex[2], ex[3], pub)
                    method = f"answer_text:{how}" if res else None
            if res is None and name and typ in NAME_TYPES:
                res, how = resolve_name(by_name, typ, name, year, pub)
                method = f"citation_field:{how}" if res else None
            if res is None and not name and len(docs_of_type.get(typ, ())) == 1:
                did = next(iter(docs_of_type[typ]))
                res = d.filter(pl.col("id") == did).to_dicts()[0]; method = "unique_document_of_type"
            if res is None:
                stats["unresolved_doc"] += 1; continue
            stats["resolved_doc"] += 1
            if (res["id"], art) not in arts:
                stats["article_not_in_chunks"] += 1; continue
            stats["resolved_article"] += 1
            stats[f"method:{method.split('+')[0]}"] += 1
            gold.append({"doc_id": res["id"], "doc_number": res["doc_number"], "doc_type": res["doc_type"],
                         "title": res["title_vi"], "article": art, "clause": c["clause"], "point": c["point"],
                         "ref": c["ref"], "method": method})
        if gold:
            uniq = {(g["doc_id"], g["article"]): g for g in gold}
            rows.append({"qa_id": q["id"], "area": q["area"], "published_date": pub, "question": q["question"],
                         "answer": q["answer"], "url": q["url"], "gold": list(uniq.values()),
                         "gold_articles": [f"{a}::{b}" for a, b in uniq], "gold_docs": sorted({g["doc_id"] for g in gold}),
                         "has_ad": bool((q["content_flag_summary"] or {}).get("has_ad"))})
    g = pl.DataFrame(rows, infer_schema_length=None)
    g.write_parquet(os.path.join(EV, "gold_all.parquet"))
    rep = {"qas_with_citations": int(h.filter(pl.col("citations").list.len() > 0).height), "stats": dict(stats),
           "qas_with_article_gold": g.height,
           "gold_by_area": g.group_by("area").len().sort("len", descending=True).rows(),
           "gold_by_year": g.group_by(pl.col("published_date").str.slice(0, 4)).len().sort("published_date").rows()}
    # ---- stratified held-out: proportional to area size, floor 10, published >= 2024 preferred
    random.seed(2024)
    pool = g.filter(~pl.col("has_ad") & (pl.col("question").str.len_chars() >= 20))
    recent = pool.filter(pl.col("published_date") >= "2024-01-01")
    areas = recent.group_by("area").len().sort("len", descending=True)
    total = recent.height
    alloc = {}
    for a, n in areas.iter_rows():
        alloc[a] = max(10, round(N_HELDOUT * n / total)) if n >= 10 else n
    scale = N_HELDOUT / sum(alloc.values())
    alloc = {a: max(min(10, n), int(round(n * scale))) for a, n in alloc.items()}
    picked = []
    for a, k in alloc.items():
        ids = recent.filter(pl.col("area") == a)["qa_id"].to_list()
        random.shuffle(ids); picked += ids[:k]
    held = g.filter(pl.col("qa_id").is_in(picked))
    held.write_parquet(os.path.join(EV, "heldout.parquet"))
    rep["heldout"] = held.height
    rep["heldout_by_area"] = held.group_by("area").len().sort("len", descending=True).rows()
    rep["heldout_published_min_max"] = [held["published_date"].min(), held["published_date"].max()]
    rep["heldout_gold_articles_mean"] = float(held["gold_articles"].list.len().mean())
    rep["heldout_methods"] = Counter(x["method"].split("+")[0] for gl in held["gold"].to_list() for x in gl)
    rep["heldout_gold_doc_types"] = Counter(x["doc_type"] for gl in held["gold"].to_list() for x in gl)
    rep["wall_s"] = round(time.time() - t0, 1)
    json.dump(rep, open(os.path.join(EV, "gold_report.json"), "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(rep, ensure_ascii=False, default=str)[:4000])

def resolve_qa(q, by_key, by_name, d, arts, with_answer_text=False):
    """Resolve one Q&A row (needs id, answer, citations, published_date) -> gold list."""
    cits = q["citations"] or []; pub = (q["published_date"] or "")[:10]; ans = V.nfc(q["answer"] or "")
    docs_of_type = defaultdict(set)
    for c in cits:
        if c["kind"] == "document" and c["id"]:
            for r in by_key.get(V.docnum_key(c["id"]), []):
                docs_of_type[c["law_type"]].add(r["id"])
    gold = {}
    for c in cits:
        if c["kind"] != "provision":
            continue
        art = (c["article"] or "").strip()
        if not re.match(r"^\d{1,3}[a-zđ]?$", art):
            continue
        typ, name, year = c["law_type"], (c["law_name"] or "").strip(), c["year"]
        res = method = None
        ex = explicit_mention(ans, art)
        if ex:
            if ex[0] == "num":
                rr = by_key.get(V.docnum_key(ex[2]), [])
                if rr:
                    res, method = rr[0], "answer_text:number"
            elif ex[1] in NAME_TYPES:
                res, how = resolve_name(by_name, ex[1], ex[2], ex[3], pub)
                method = f"answer_text:{how}" if res else None
        if res is None and name and typ in NAME_TYPES:
            res, how = resolve_name(by_name, typ, name, year, pub)
            method = f"citation_field:{how}" if res else None
        if res is None and not name and len(docs_of_type.get(typ, ())) == 1:
            did = next(iter(docs_of_type[typ])); res = d[did]; method = "unique_document_of_type"
        if res is not None and (res["id"], art) in arts:
            gold[(res["id"], art)] = method
    if with_answer_text:
        for m in re.finditer(r"Điều\s+(\d{1,3}[a-zđ]?)(?![\w/])", ans):
            art = m.group(1); ex = explicit_mention(ans[m.start():], art); res = None
            if ex and ex[0] == "num":
                rr = by_key.get(V.docnum_key(ex[2]), []); res = rr[0] if rr else None
            elif ex and ex[1] in NAME_TYPES:
                res, _ = resolve_name(by_name, ex[1], ex[2], ex[3], pub)
            if res and (res["id"], art) in arts and (res["id"], art) not in gold:
                gold[(res["id"], art)] = "answer_text_mention"
    return gold

def stage_gold_variants():
    """Same 1,000 held-out questions, re-labelled: v2 = fixed resolver on the hdpl citation
    list; aug = v2 + every 'Điều N <law reference>' explicitly cited in the answer text."""
    docs, by_key, by_name = load_docs()
    d = {r["id"]: r for r in docs.to_dicts()}
    ch = pl.read_parquet(os.path.join(R, "data", "chunks", "chunks.parquet"), columns=["doc_id", "article_no"])
    arts = set(zip(ch["doc_id"].to_list(), ch["article_no"].to_list()))
    held = pl.read_parquet(os.path.join(EV, "heldout.parquet"))
    fs = sorted(glob.glob(os.path.join(MAN["datasets"]["tmquan/thuvienphapluat-vn-hdpl"]["local_dir"], "documents-*.parquet")))
    h = pl.read_parquet(fs, columns=["id", "answer", "citations", "published_date"]).filter(pl.col("id").is_in(held["qa_id"].to_list()))
    hm = {r["id"]: r for r in h.to_dicts()}
    rep = {}
    for name, aug in [("v2", False), ("aug", True)]:
        rows, meth = [], Counter()
        for q in held.iter_rows(named=True):
            gold = resolve_qa(hm[q["qa_id"]], by_key, by_name, d, arts, with_answer_text=aug)
            meth.update(m.split("+")[0] for m in gold.values())
            rows.append({"qa_id": q["qa_id"], "gold_articles": [f"{a}::{b}" for a, b in gold], "gold_docs": sorted({a for a, _ in gold})})
        df = pl.DataFrame(rows, schema={"qa_id": pl.Utf8, "gold_articles": pl.List(pl.Utf8), "gold_docs": pl.List(pl.Utf8)})
        df.write_parquet(os.path.join(EV, f"heldout_gold_{name}.parquet"))
        rep[name] = {"questions_with_gold": int((df["gold_articles"].list.len() > 0).sum()), "gold_articles_mean": float(df["gold_articles"].list.len().mean()),
                     "methods": dict(meth)}
    v1 = {r["qa_id"]: set(r["gold_articles"]) for r in held.select(["qa_id", "gold_articles"]).to_dicts()}
    v2 = {r["qa_id"]: set(r["gold_articles"]) for r in pl.read_parquet(os.path.join(EV, "heldout_gold_v2.parquet")).to_dicts()}
    rep["v1_vs_v2_identical"] = sum(1 for k in v1 if v1[k] == v2.get(k))
    rep["v1_articles_kept_in_v2"] = sum(len(v1[k] & v2.get(k, set())) for k in v1) / max(1, sum(len(v1[k]) for k in v1))
    json.dump(rep, open(os.path.join(EV, "gold_variants_report.json"), "w"), indent=1, default=str)
    print(json.dumps(rep, indent=1, default=str))

# ------------------------------------------------------------------ runs
def rrf(lists, k=60, top=100):
    s = defaultdict(float)
    for L in lists:
        for r, i in enumerate(L):
            s[i] += 1.0 / (k + r + 1)
    return [i for i, _ in sorted(s.items(), key=lambda x: -x[1])[:top]]

def encode_queries(texts, gpu):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    from vllm import LLM
    llm = LLM(model="nvidia/Nemotron-3-Embed-8B-BF16", gpu_memory_utilization=0.3, max_model_len=8192)
    res = llm.embed(["query: " + t for t in texts], use_tqdm=False)
    return np.asarray([r.outputs.embedding for r in res], dtype=np.float32)

def stage_run():
    import bm25_vi as B
    t0 = time.time()
    held = pl.read_parquet(os.path.join(EV, "heldout.parquet"))
    qs = held["question"].to_list(); qids = held["qa_id"].to_list()
    ids = pl.read_parquet(os.path.join(R, "index", "emb_vbpl_ids.parquet"))["chunk_id"].to_list()
    rep = {"n_queries": len(qs)}
    runs = {}
    for name, bi in [("bm25_uni", False), ("bm25_bi", True)]:
        idx = B.BM25Index(os.path.join(R, "index", name), bigrams=bi)
        t1 = time.time()
        runs[name] = [idx.search(q, k=100)[0].tolist() for q in qs]
        rep[f"{name}_ms_per_query"] = round(1000 * (time.time() - t1) / len(qs), 1)
        del idx
    # dense: encode queries with vLLM, search on GPU with torch
    t1 = time.time()
    Q = encode_queries(qs, int(os.environ.get("EVAL_GPU", "4")))
    rep["query_encode_s"] = round(time.time() - t1, 1)
    np.save(os.path.join(EV, "heldout_query_emb.npy"), Q.astype(np.float16))
    import torch
    E = torch.from_numpy(np.load(os.path.join(R, "index", "emb_vbpl_4096_f16.npy"))).cuda()
    for name, dim in [("dense_4096", 4096), ("dense_1024", 1024)]:
        t1 = time.time()
        Qt = torch.from_numpy(Q[:, :dim]).cuda().half()
        Qt = torch.nn.functional.normalize(Qt.float(), dim=1).half()
        if dim == 4096:
            Ed = E
        else:
            Ed = torch.nn.functional.normalize(E[:, :dim].float(), dim=1).half()
        out = []
        for s in range(0, len(qs), 256):
            sc = Qt[s:s + 256] @ Ed.T
            out += torch.topk(sc.float(), 100, dim=1).indices.cpu().tolist()
        torch.cuda.synchronize()
        rep[f"{name}_ms_per_query"] = round(1000 * (time.time() - t1) / len(qs), 2)
        runs[name] = out
        del Ed
    runs["hybrid_rrf"] = [rrf([a, b]) for a, b in zip(runs["bm25_bi"], runs["dense_4096"])]
    runs["hybrid_rrf_uni"] = [rrf([a, b]) for a, b in zip(runs["bm25_uni"], runs["dense_4096"])]
    out = []
    for m, L in runs.items():
        for qi, lst in zip(qids, L):
            out.append({"qa_id": qi, "method": m, "chunk_ids": [ids[i] for i in lst]})
    pl.DataFrame(out).write_parquet(os.path.join(EV, "runs.parquet"))
    rep["wall_s"] = round(time.time() - t0, 1)
    json.dump(rep, open(os.path.join(EV, "run_report.json"), "w"), indent=1)
    print(rep)
    sys.stdout.flush(); os._exit(0)

# ------------------------------------------------------------------ rerank
RERANK_MODEL = "nvidia/Nemotron-3.5-Rerank-8B-BF16"

def load_reranker():
    """Card path 1: sentence-transformers CrossEncoder; path 2 (fallback): Transformers
    AutoModelForSequenceClassification + processor chat template (query/document roles)."""
    import torch
    try:
        from sentence_transformers import CrossEncoder
        m = CrossEncoder(RERANK_MODEL, device="cuda", trust_remote_code=True,
                         model_kwargs={"dtype": torch.bfloat16, "attn_implementation": "sdpa"}, max_length=2048)
        def score(q, docs):
            return np.asarray(m.predict([(q, d) for d in docs], batch_size=8, show_progress_bar=False), dtype=np.float32)
        return score, "sentence-transformers CrossEncoder"
    except Exception as e:
        err = repr(e)[:300]
        from transformers import AutoModelForSequenceClassification, AutoProcessor
        proc = AutoProcessor.from_pretrained(RERANK_MODEL)
        model = AutoModelForSequenceClassification.from_pretrained(RERANK_MODEL, trust_remote_code=True, dtype=torch.bfloat16,
                                                                   device_map={"": "cuda:0"}, attn_implementation="sdpa").eval()
        def score(q, docs):
            out = []
            for d in docs:
                inp = proc.apply_chat_template([{"role": "query", "content": [{"type": "text", "text": q}]},
                                                {"role": "document", "content": [{"type": "text", "text": d}]}],
                                               tokenize=True, add_generation_prompt=False, return_dict=True, return_tensors="pt").to("cuda:0")
                with torch.inference_mode():
                    out.append(float(model(**inp).logits.squeeze().float()))
            return np.asarray(out, dtype=np.float32)
        return score, f"transformers fallback (CrossEncoder failed: {err})"

def rerank_worker(rank, world, gpu, topn, base="hybrid_rrf"):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    held = pl.read_parquet(os.path.join(EV, "heldout.parquet")).select(["qa_id", "question"])
    runs = pl.read_parquet(os.path.join(EV, "runs.parquet")).filter(pl.col("method") == base)
    ch = pl.read_parquet(os.path.join(R, "data", "chunks", "chunks.parquet"), columns=["chunk_id", "context", "text"])
    txt = dict(zip(ch["chunk_id"].to_list(), [(c or "") + "\n" + (t or "") for c, t in zip(ch["context"].to_list(), ch["text"].to_list())]))
    del ch
    q = dict(zip(held["qa_id"].to_list(), held["question"].to_list()))
    rows = runs.to_dicts()[rank::world]
    t0 = time.time()
    score, path = load_reranker()
    load_s = time.time() - t0; t1 = time.time(); out = []
    for r in rows:
        cands = r["chunk_ids"][:topn]
        sc = score(q[r["qa_id"]], [txt[c][:5000] for c in cands])
        order = np.argsort(-sc, kind="stable")
        out.append({"qa_id": r["qa_id"], "method": f"{base}+rerank{topn}", "chunk_ids": [cands[i] for i in order] + r["chunk_ids"][topn:]})
    os.makedirs(os.path.join(EV, "rerank_parts"), exist_ok=True)
    pl.DataFrame(out).write_parquet(os.path.join(EV, "rerank_parts", f"{base}.rank{rank}.parquet"))
    json.dump({"rank": rank, "gpu": gpu, "n": len(rows), "path": path, "load_s": round(load_s, 1), "rerank_s": round(time.time() - t1, 1)},
              open(os.path.join(EV, "rerank_parts", f"{base}.rank{rank}.json"), "w"))
    os._exit(0)

def stage_rerank():
    import subprocess
    gpus = [int(g) for g in os.environ.get("RERANK_GPUS", "4,5,6,7").split(",")]
    topn = int(os.environ.get("RERANK_TOPN", "30"))
    base = os.environ.get("RERANK_BASE", "hybrid_rrf")
    import signal
    ps = [subprocess.Popen([sys.executable, __file__, "rerank_worker", str(r), str(len(gpus)), str(g), str(topn), base],
                           stdout=open(os.path.join(EV, f"rerank.rank{r}.log"), "w"), stderr=subprocess.STDOUT,
                           start_new_session=True) for r, g in enumerate(gpus)]
    rc = [p.wait() for p in ps]
    for p in ps:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    print("rerank exit codes", rc)
    parts = [pl.read_parquet(f) for f in sorted(glob.glob(os.path.join(EV, "rerank_parts", f"{base}.rank*.parquet")))]
    pl.concat(parts).write_parquet(os.path.join(EV, f"runs_rerank_{base}.parquet"))
    st = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(EV, "rerank_parts", f"{base}.rank*.json")))]
    json.dump({"base": base, "topn": topn, "workers": st}, open(os.path.join(EV, f"rerank_report_{base}.json"), "w"), indent=1)

# ------------------------------------------------------------------ metrics
def art_of(cid):
    """chunk id -> (doc_id, article) or (doc_id, None)"""
    doc, rest = cid.split("::", 1)
    m = re.match(r"^dieu-(\d+[a-zđ]?)", rest)
    return doc, (m.group(1) if m else None)

def stage_metrics():
    out = []
    for label, path in [("v1", os.path.join(EV, "heldout.parquet")), ("v2", os.path.join(EV, "heldout_gold_v2.parquet")),
                        ("aug", os.path.join(EV, "heldout_gold_aug.parquet"))]:
        if os.path.exists(path):
            out.append(metrics_for(label, pl.read_parquet(path).select(["qa_id", "gold_articles", "gold_docs"])))
    allm = pl.concat(out)
    allm.write_csv(os.path.join(EV, "retrieval_metrics.csv"))
    pl.Config.set_tbl_rows(100); pl.Config.set_tbl_width_chars(220)
    print(allm)

def metrics_for(gold_label, held):
    runs = pl.read_parquet(os.path.join(EV, "runs.parquet"))
    extra = ([os.path.join(EV, "runs_rerank.parquet")] if os.path.exists(os.path.join(EV, "runs_rerank.parquet")) else []) + \
            sorted(glob.glob(os.path.join(EV, "runs_rerank_*.parquet")))
    seen = set(runs["method"].unique().to_list())
    for f in extra:     # runs_rerank.parquet = first (hybrid) rerank run; runs_rerank_<base>.parquet = later runs
        x = pl.read_parquet(f).filter(~pl.col("method").is_in(list(seen)))
        seen |= set(x["method"].unique().to_list())
        runs = pl.concat([runs, x])
    held = held.filter(pl.col("gold_articles").list.len() > 0)
    gold = {r["qa_id"]: r for r in held.to_dicts()}
    K = [1, 5, 10, 20]
    rows = []; per_q = []
    for m in runs["method"].unique(maintain_order=True).to_list():
        sub = runs.filter((pl.col("method") == m) & pl.col("qa_id").is_in(list(gold)))
        acc = defaultdict(list)
        for r in sub.iter_rows(named=True):
            g = gold[r["qa_id"]]
            ga = set(g["gold_articles"]); gd = set(g["gold_docs"])
            arts, docs = [], []
            for cid in r["chunk_ids"]:
                d, a = art_of(cid)
                key = f"{d}::{a}" if a else f"{d}::{cid}"
                if key not in arts:
                    arts.append(key)
                if d not in docs:
                    docs.append(d)
            for lvl, ranked, G in [("article", arts, ga), ("document", docs, gd)]:
                first = next((i for i, x in enumerate(ranked[:100]) if x in G), None)
                acc[(lvl, "mrr@100")].append(0.0 if first is None else 1.0 / (first + 1))
                for k in K:
                    top = ranked[:k]
                    acc[(lvl, f"recall@{k}")].append(1.0 if any(x in G for x in top) else 0.0)
                    acc[(lvl, f"frac_recall@{k}")].append(len(G & set(top)) / len(G))
                per_q.append({"qa_id": r["qa_id"], "method": m, "level": lvl, "first_hit_rank": None if first is None else first + 1})
        for (lvl, met), v in acc.items():
            rows.append({"method": m, "level": lvl, "metric": met, "value": round(float(np.mean(v)), 4), "n_queries": len(v)})
    df = pl.DataFrame(rows)
    wide = df.pivot(values="value", index=["method", "level", "n_queries"], on="metric").sort(["level", "method"])
    cols = ["method", "level", "n_queries"] + [f"recall@{k}" for k in K] + ["mrr@100"] + [f"frac_recall@{k}" for k in K]
    pl.DataFrame(per_q).write_parquet(os.path.join(EV, f"per_query_ranks_{gold_label}.parquet"))
    return wide.select(cols).with_columns(pl.lit(gold_label).alias("gold")).select(["gold"] + cols)

if __name__ == "__main__":
    st = sys.argv[1]
    if st == "gold": stage_gold()
    elif st == "run": stage_run()
    elif st == "rerank": stage_rerank()
    elif st == "rerank_worker": rerank_worker(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]),
                                              sys.argv[6] if len(sys.argv) > 6 else "hybrid_rrf")
    elif st == "metrics": stage_metrics()
    elif st == "gold_variants": stage_gold_variants()
