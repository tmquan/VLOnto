#!/usr/bin/env python3
"""Step 4 - Structure parsing and chunking.

Why: hdpl answers and lawyers cite *articles* (Điều), so the retrieval unit is
one article with its khoản/điểm kept together, carrying its Chương/Mục context
and document identity so the agent can cite '<Điều N> <title> (<number>)'.

Rules
  * article heading = line 'Điều N[a]. <title>' accepted only if N continues
    the sequence (N = last+1, gap <= 2, or 'Na' after N); a heading that starts
    with a quote or follows '... như sau:' is quoted amendment text, not a new
    article. 'Điều 1.' after an attachment heading ('QUY CHẾ ...', '(Ban hành
    kèm theo ...)') opens a new segment (attached regulation).
  * article body > 3,600 chars is split at khoản boundaries into parts of
    <= 3,000 chars with a <= 400-char overlap.
  * documents without any accepted article are windowed (3,000 chars, 300 overlap).
  * chunk id: <doc_id>::dieu-<n>[::part-k]; attachments <doc_id>::att<s>-dieu-<n>;
    no-article docs <doc_id>::body::part-k.

Outputs ($R/data/chunks/): chunks.parquet, doc_struct.parquet,
anle_chunks.parquet, chunk_report.json, sample_chunks.jsonl
"""
import os, sys, re, json, time, random
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vnlegal_text as V

R = Path(os.environ.get("R", "/path/to/vnlegal"))
OUT = Path(os.environ.get("CHUNK_OUT", str(R / "data" / "chunks"))); OUT.mkdir(parents=True, exist_ok=True)
NPROC = int(os.environ.get("NPROC", "200"))
MAX_BODY, SPLIT_AT, OVERLAP, WIN, WIN_OVL = 3000, 3600, 400, 3000, 300

ART = re.compile(r"^(?:\*\*)?Điều\s+(\d{1,3})([a-zđ]?)\s*(?:[\.:\-–]+)\s*(.*)$")
CHAP = re.compile(r"^(?:Chương|CHƯƠNG)\s+([IVXLCDM]+|\d+)([a-zA-Z]?)\b\s*[\.:\-–]?\s*(.*)$")
SEC = re.compile(r"^(?:Mục|MỤC)\s+(\d+)\b\s*[\.:\-–]?\s*(.*)$")
PART = re.compile(r"^(?:Phần\s+thứ|PHẦN\s+THỨ)\s+(\S+)\s*[\.:\-–]?\s*(.*)$")
ATTACH = re.compile(r"^(?:QUY\s+CHẾ|QUY\s+ĐỊNH|BẢN\s+QUY\s+ĐỊNH|ĐIỀU\s+LỆ|QUY\s+TRÌNH|HƯỚNG\s+DẪN|NỘI\s+QUY|TIÊU\s+CHUẨN|CHƯƠNG\s+TRÌNH|CHẾ\s+ĐỘ|QUY\s+TẮC|ĐỊNH\s+MỨC|DANH\s+MỤC|KẾ\s+HOẠCH)\b")
BANHANH = re.compile(r"^[\(\[]?\s*(?:Ban\s+hành|Kèm\s+theo)\s+(?:kèm\s+theo\s+)?", re.I)
KHOAN = re.compile(r"^\d{1,3}[\.\)]\s")
INTRO = re.compile(r"(như\s+sau|sau\s+đây)\s*:\s*$")
QUOTE = "“\"'‘«"
EFFECT_TITLE = re.compile(r"(?i)hiệu\s+lực|thi\s+hành|điều\s+khoản\s+chuyển\s+tiếp|tổ\s+chức\s+thực\s+hiện")

def _caps(s):
    return V._is_caps(s)

SPLIT_HEAD = re.compile(r"(?m)^(Điều|ĐIỀU)[ \t]*\n[ \t]*(\d{1,3}[a-zđ]?[ \t]*[\.:\-–])")
SPLIT_CHAP = re.compile(r"(?m)^(Chương|CHƯƠNG|Mục|MỤC)[ \t]*\n[ \t]*([IVXLCDM]+|\d{1,3})\b")
BODY_START = re.compile(r"\s(?=(?:Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Pháp lệnh|Nghị quyết|Quyết định|Hiến pháp|Quy chế|Quy định|Điều lệ) này\b|Trong (?:Bộ luật|Luật|Nghị định|Thông tư|Pháp lệnh|Nghị quyết|Quyết định|Quy chế|Quy định) này\b)")

def normalise_headings(text):
    text = SPLIT_HEAD.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
    return SPLIT_CHAP.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)

def parse_articles(text):
    text = normalise_headings(text)
    lines = text.split("\n")
    arts, pre = [], []
    cur = None; seg = 1; last_no = 0; last_suf = ""
    chapter = section = part = None
    attach_at, attach_title = -999, None
    prev = ""; i = 0; n = len(lines)
    while i < n:
        line = lines[i].strip()
        quoted = line[:1] in QUOTE
        m = ART.match(line) if not quoted else None
        if m:
            no, suf, title = int(m.group(1)), m.group(2), m.group(3).strip()
            intro = bool(INTRO.search(prev))
            accept = restart = False
            if not intro:
                if cur is None and seg == 1 and no in (1, 2) and not suf:
                    accept = True
                elif cur is not None and no == last_no + 1 and not suf:
                    accept = True
                elif cur is not None and no == last_no and suf and suf > last_suf:
                    accept = True
                elif cur is not None and last_no + 1 < no <= last_no + 30 and not suf:
                    accept = True
                elif cur is not None and no == 1 and not suf and i - attach_at <= 40:
                    accept = restart = True
            if accept:
                if restart:
                    seg += 1; chapter = section = part = None
                if title and (len(title) > 200 or title.endswith((".", ";")) ):
                    mb = BODY_START.search(title[:200])
                    if mb and 2 <= len(title[:mb.start()].split()) <= 25:
                        body0, title = [title[mb.start():].strip()], title[:mb.start()].strip()
                    else:
                        body0, title = [title], None       # 'Điều 2. Quyết định này có hiệu lực ...' = body
                else:
                    body0 = []
                    if not title and i + 1 < n:
                        nxt = lines[i + 1].strip()
                        if nxt and not KHOAN.match(nxt) and not ART.match(nxt) and len(nxt) <= 200 and not nxt.endswith((".", ";", ":")):
                            title = nxt; i += 1
                        elif nxt and not KHOAN.match(nxt) and not ART.match(nxt):
                            mb = BODY_START.search(nxt[:200])
                            if mb and 2 <= len(nxt[:mb.start()].split()) <= 25:
                                title = nxt[:mb.start()].strip(); body0 = [nxt[mb.start():].strip()]; i += 1
                cur = {"seg": seg, "no": no, "suf": suf, "title": title or None, "chapter": chapter,
                       "section": section, "part": part, "attach_title": attach_title if seg > 1 else None,
                       "lines": body0}
                arts.append(cur)
                last_no, last_suf = no, suf
                prev = line; i += 1
                continue
        if not quoted:
            mc = CHAP.match(line)
            if mc and (len(line) < 200):
                t = mc.group(3).strip()
                if not t and i + 1 < n and _caps(lines[i + 1]) and not ART.match(lines[i + 1]):
                    t = lines[i + 1].strip(); i += 1
                chapter = f"Chương {mc.group(1)}{mc.group(2)}" + (f". {t}" if t else ""); section = None
                prev = line; i += 1; continue
            ms = SEC.match(line)
            if ms and len(line) < 200 and (not ms.group(2) or _caps(ms.group(2)) or len(ms.group(2)) < 120):
                t = ms.group(2).strip()
                if not t and i + 1 < n and _caps(lines[i + 1]) and not ART.match(lines[i + 1]):
                    t = lines[i + 1].strip(); i += 1
                section = f"Mục {ms.group(1)}" + (f". {t}" if t else "")
                prev = line; i += 1; continue
            mp = PART.match(line)
            if mp and len(line) < 200:
                t = mp.group(2).strip()
                if not t and i + 1 < n and _caps(lines[i + 1]):
                    t = lines[i + 1].strip(); i += 1
                part = f"Phần thứ {mp.group(1)}" + (f". {t}" if t else ""); chapter = section = None
                prev = line; i += 1; continue
            if ATTACH.match(line) and _caps(line[:40]):
                attach_at = i; attach_title = line[:200]
                prev = line; i += 1; continue          # structural heading, not article text
            if BANHANH.match(line):
                attach_at = i
                if line.startswith(("(", "[")):
                    prev = line; i += 1; continue      # '(Ban hành kèm theo ...)' caption
        if cur is not None:
            cur["lines"].append(line)
        else:
            pre.append(line)
        prev = line; i += 1
    return arts, pre

def split_body(lines):
    """Split article body lines into parts <= MAX_BODY chars at khoản boundaries."""
    body = "\n".join(lines)
    if len(body) <= SPLIT_AT:
        return [body]
    blocks, cur = [], []
    for l in lines:
        if KHOAN.match(l) and cur:
            blocks.append("\n".join(cur)); cur = []
        cur.append(l)
    if cur:
        blocks.append("\n".join(cur))
    pieces = []
    for b in blocks:                      # break oversize blocks by lines, then by length
        if len(b) <= MAX_BODY:
            pieces.append(b); continue
        acc = ""
        for l in b.split("\n"):
            while len(l) > MAX_BODY:
                cut = l.rfind(" ", 0, MAX_BODY)
                cut = cut if cut > MAX_BODY // 2 else MAX_BODY
                if acc:
                    pieces.append(acc); acc = ""
                pieces.append(l[:cut]); l = l[cut:].lstrip()
            if acc and len(acc) + 1 + len(l) > MAX_BODY:
                pieces.append(acc); acc = l
            else:
                acc = (acc + "\n" + l) if acc else l
        if acc:
            pieces.append(acc)
    parts, acc = [], ""
    for p in pieces:
        if acc and len(acc) + 1 + len(p) > MAX_BODY:
            parts.append(acc); acc = p
        else:
            acc = (acc + "\n" + p) if acc else p
    if acc:
        parts.append(acc)
    out = [parts[0]]
    for k in range(1, len(parts)):
        tail = parts[k - 1][-OVERLAP:]
        cut = tail.find("\n")
        tail = tail[cut + 1:] if 0 <= cut < len(tail) - 50 else tail[tail.find(" ") + 1:]
        out.append("[…] " + tail + "\n" + parts[k])
    return out

def windows(text, size=WIN, ovl=WIN_OVL):
    out, s = [], 0
    while s < len(text):
        e = min(len(text), s + size)
        if e < len(text):
            cut = text.rfind("\n", s + size // 2, e)
            if cut < 0:
                cut = text.rfind(" ", s + size // 2, e)
            e = cut if cut > 0 else e
        out.append(text[s:e].strip())
        if e >= len(text):
            break
        s = max(e - ovl, s + 1)
    return [w for w in out if w]

DOC_COLS = ["id", "doc_number", "doc_type", "title_vi", "issuer", "issue_date", "effective_date_meta",
            "status_code", "status_raw", "legal_area", "url", "tier"]

def chunk_doc(d):
    text = d["text"]
    arts, pre = parse_articles(text)
    meta = {k: d.get(k) for k in DOC_COLS}
    num = d.get("doc_number")
    title = d.get("title_vi") or d.get("doc_type")
    ctx_title = title + (f" (số {num})" if num and num not in title else "")
    chunks, seen = [], set()
    def add(cid, art_no, art_title, chapter, section, partname, attach, k, K, body_text, heading):
        while cid in seen:
            cid += "-dup"
        seen.add(cid)
        ctx = "\n".join(x for x in [ctx_title, attach, partname, chapter, section] if x)
        txt = (heading + (f" (phần {k}/{K})" if K > 1 else "") + "\n" + body_text) if heading else body_text
        chunks.append({**meta, "chunk_id": cid, "doc_id": d["id"], "article_no": art_no, "article_title": art_title,
                       "chapter": chapter, "section": section, "part_name": partname, "attachment": attach,
                       "part": k, "n_parts": K, "text": txt, "context": ctx, "chars": len(txt)})
    for a in arts:
        no = f"{a['no']}{a['suf']}"
        heading = f"Điều {no}." + (f" {a['title']}" if a["title"] else "")
        parts = split_body(a["lines"]) if a["lines"] else [""]
        K = len(parts)
        base = f"{d['id']}::" + (f"att{a['seg']-1}-" if a["seg"] > 1 else "") + f"dieu-{no}"
        for k, p in enumerate(parts, 1):
            cid = base + (f"::part-{k}" if K > 1 else "")
            add(cid, no if a["seg"] == 1 else f"att{a['seg']-1}:{no}", a["title"], a["chapter"], a["section"],
                a["part"], a["attach_title"], k, K, p, heading)
    if not arts:
        ws = windows(text)
        for k, w in enumerate(ws, 1):
            add(f"{d['id']}::body::part-{k}", None, None, None, None, None, None, k, len(ws), w, None)
    # effect articles -> effective date stated in text
    seg1 = [a for a in arts if a["seg"] == 1]
    eff_arts = [a for a in seg1 if a["title"] and EFFECT_TITLE.search(a["title"])] + seg1[-2:]
    eff_text, seen_no = [], set()
    for a in eff_arts:
        if a["no"] in seen_no:
            continue
        seen_no.add(a["no"])
        eff_text.append(f"Điều {a['no']}{a['suf']}. {a['title'] or ''}\n" + "\n".join(a["lines"]))
    eff_text = "\n".join(eff_text)[:12000]
    eff_date, eff_src = V.extract_effective(eff_text, d.get("issue_date")) if eff_text else (None, None)
    text = normalise_headings(text)
    struct = {"id": d["id"], "n_articles": len(seg1), "n_segments": max([a["seg"] for a in arts], default=0),
              "n_chunks": len(chunks), "has_articles": bool(arts), "n_chapters": len({a["chapter"] for a in seg1 if a["chapter"]}),
              "first_article_pos": (text.find("\nĐiều 1") if "\nĐiều 1" in text else -1),
              "eff_text_date": eff_date, "eff_text_src": eff_src, "effect_text": eff_text}
    return chunks, struct

def chunk_anle():
    man = json.load(open(R / "data" / "download_manifest.json"))
    import glob
    fs = sorted(glob.glob(os.path.join(man["datasets"]["tmquan/anle-toaan-gov-vn"]["local_dir"], "documents-*.parquet")))
    a = pl.read_parquet(fs, columns=["doc_name", "official_document_id", "court", "issued_date", "category",
                                      "instance_level", "is_precedent", "precedent_number", "web_url", "markdown", "citations_law"])
    rows = []
    for r in a.iter_rows(named=True):
        txt = V.basic_clean(r["markdown"] or "")
        if len(txt) < 200:
            continue
        ctx = " — ".join(x for x in [("Án lệ " + r["precedent_number"]) if r["is_precedent"] and r["precedent_number"] else None,
                                       f"Bản án/Quyết định số {r['official_document_id']}" if r["official_document_id"] else None,
                                       r["court"], r["issued_date"], r["category"]] if x)
        refs = sorted({c["ref"] for c in (r["citations_law"] or []) if c and c.get("ref")})[:50]
        ws = windows(txt)
        for k, w in enumerate(ws, 1):
            rows.append({"chunk_id": f"anle::{r['doc_name']}::part-{k}", "doc_name": r["doc_name"],
                         "official_document_id": r["official_document_id"], "court": r["court"],
                         "issued_date": r["issued_date"], "category": r["category"], "instance_level": r["instance_level"],
                         "is_precedent": r["is_precedent"], "precedent_number": r["precedent_number"], "url": r["web_url"],
                         "part": k, "n_parts": len(ws), "context": ctx, "text": w, "chars": len(w), "law_refs": refs})
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet(OUT / "anle_chunks.parquet")
    return {"anle_docs": a.height, "anle_chunks": df.height, "anle_precedent_chunks": int(df["is_precedent"].sum()),
            "anle_chars_median": float(df["chars"].median())}

def main():
    t0 = time.time()
    docs = pl.read_parquet(R / "data" / "clean" / "docs_clean.parquet")
    rows = docs.select(DOC_COLS + ["text"]).to_dicts()
    with Pool(NPROC) as p:
        res = p.map(chunk_doc, rows, chunksize=32)
    chunks = [c for cs, _ in res for c in cs]
    structs = [s for _, s in res]
    print("docs", len(rows), "chunks", len(chunks), f"{time.time()-t0:.0f}s", flush=True)
    cdf = pl.DataFrame(chunks, infer_schema_length=None)
    cdf.write_parquet(OUT / "chunks.parquet")
    sdf = pl.DataFrame(structs, infer_schema_length=None)
    sdf.write_parquet(OUT / "doc_struct.parquet")
    rep = {"docs": len(rows), "chunks": cdf.height}
    rep["chunks_by_kind"] = {
        "article_single": int(((cdf["n_parts"] == 1) & cdf["article_no"].is_not_null()).sum()),
        "article_parts": int(((cdf["n_parts"] > 1) & cdf["article_no"].is_not_null()).sum()),
        "attachment_article_chunks": int(cdf["chunk_id"].str.contains("::att").sum()),
        "no_article_windows": int(cdf["article_no"].is_null().sum())}
    rep["docs_with_articles"] = int(sdf["has_articles"].sum())
    rep["docs_without_articles_by_type"] = sdf.join(docs.select(["id", "doc_type"]), on="id").filter(~pl.col("has_articles")).group_by("doc_type").len().sort("len", descending=True).rows()
    rep["articles_total_seg1"] = int(sdf["n_articles"].sum())
    rep["split_articles"] = int(cdf.filter(pl.col("n_parts") > 1).select(["doc_id", "article_no"]).unique().height)
    rep["chars_quantiles"] = {str(q): float(cdf["chars"].quantile(q)) for q in [0, .05, .25, .5, .75, .95, .99, 1]}
    rep["chars_total"] = int(cdf["chars"].sum()); rep["context_chars_total"] = int(cdf["context"].str.len_chars().sum())
    rep["est_tokens_total_2.66cpt"] = int((rep["chars_total"] + rep["context_chars_total"]) / 2.66)
    rep["chunks_by_doc_type"] = cdf.group_by("doc_type").len().sort("len", descending=True).rows()
    rep["eff_text_date_cov"] = int(sdf["eff_text_date"].is_not_null().sum())
    rep["eff_text_src"] = sdf.group_by("eff_text_src").len().rows()
    # known articles check
    chk = {}
    for did, art in [("333670", "35"), ("333670", "220"), ("142187", "37"), ("523642", "252")]:
        x = cdf.filter((pl.col("doc_id") == did) & (pl.col("article_no") == art))
        chk[f"{did}:{art}"] = x.select(["chunk_id", "title_vi", "chapter", "article_title", "chars"]).to_dicts()
    rep["known_article_checks"] = chk
    rep["struct_known"] = sdf.filter(pl.col("id").is_in(["333670", "142187", "523642", "557190", "259700"])).drop("effect_text").to_dicts()
    # two example chunks for the guide + 10 sample chunks
    ex = cdf.filter(pl.col("chunk_id").is_in(["333670::dieu-35", "523642::dieu-252"]))
    rep["example_chunks"] = ex.to_dicts()
    random.seed(7)
    pool_ids = cdf.filter(pl.col("doc_type").is_in(["Luật", "Bộ luật", "Nghị định", "Thông tư"]) & pl.col("article_no").is_not_null())["chunk_id"].to_list()
    pick = ["333670::dieu-35", "523642::dieu-252"] + random.sample(pool_ids, 6)
    pick += random.sample(cdf.filter(pl.col("n_parts") > 1)["chunk_id"].to_list(), 1)
    pick += random.sample(cdf.filter(pl.col("article_no").is_null())["chunk_id"].to_list(), 1)
    with open(OUT / "sample_chunks.jsonl", "w") as f:
        for r in cdf.filter(pl.col("chunk_id").is_in(pick)).to_dicts():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rep.update(chunk_anle())
    rep["wall_s"] = round(time.time() - t0, 1)
    json.dump(rep, open(OUT / "chunk_report.json", "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("example_chunks", "known_article_checks", "struct_known")}, ensure_ascii=False, default=str)[:3000])

if __name__ == "__main__":
    main()
