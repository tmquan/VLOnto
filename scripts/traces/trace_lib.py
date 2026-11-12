"""Question traces for the VLOnto site: one area at a time, the 20 most-asked articles, one representative answer each,
traced like Fig. 1 / Fig. 6 of arXiv:2611.11426 (question, answer, cited sources, point -> clause -> article -> section ->
chapter -> work, the law's vbpl record, terms the question mentions with their defining clauses, the area, and other
answers in the same area that cite the same law).

Inputs are the rebuilt pipeline tables ($R/data/clean/docs_clean.parquet, $R/data/chunks/chunks.parquet,
$R/eval/gold_all.parquet), the KG-style tables made by kg_edges.py ($TR/kg/*.parquet) and the hdpl/tnpl/vbpl shards.
Licence policy: no answer text, no article/clause/point text, no person names. Question titles are shown for the traced
questions (user decision 2026-11-12); other answers carry their title only when short and free of person names."""
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import polars as pl

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("VLONTO_REPO_ROOT", os.path.dirname(os.path.dirname(HERE)))   # scripts/traces -> repository root
sys.path.insert(0, os.path.join(REPO, "vlonto"))
from vlonto import vnlegal_text as V          # noqa: E402  (same file as pipeline/vnlegal_text.py)
from vlonto import build_docs as BD           # noqa: E402
from vlonto import config as C                # noqa: E402
from vlonto.resolve import norm_article       # noqa: E402

N_MATCH = 5            # paper: word 5-gram containment (Section 4, Table 6, Section 10)
VERIFY_AT = 0.5        # paper: >= 0.5 -> validated / "word for word"
LETTERS = "a b c d đ e g h i k l m n o p q r s t u v x y".split()
QUOTE = "“\"'‘«"
KHOAN_RE = re.compile(r"^(\d{1,3})([a-zđ]?)[\.\)]\s+(.*)$")
DIEM_RE = re.compile(r"^([a-zđ])\)\s*(.*)$")
LEAD_ENUM = re.compile(r"^\s*(?:\d{1,3}[a-zđ]?[\.\)]|[a-zđ]\))\s*")
HEAD_RE = re.compile(r"^Điều\s+\S+?\.?\s*(?:\(phần\s+\d+/\d+\))?\s*")


# ------------------------------------------------------------------ text, tokens, n-grams
def toks(s):
    """Syllable tokens: NFC, new-style tone marks, lower case; document numbers stay one token (vnlegal_text.vi_tokens)."""
    return V.vi_tokens(s or "")


def ngram_set(t, n):
    return {tuple(t[i:i + n]) for i in range(len(t) - n + 1)} if len(t) >= n else set()


class AnswerGrams:
    """n-gram sets of one answer text, built lazily per n."""
    def __init__(self, text):
        self.t = toks(text)
        self.sets = {}

    def get(self, n):
        if n not in self.sets:
            self.sets[n] = ngram_set(self.t, n)
        return self.sets[n]


def containment(prov_text, ans, n=N_MATCH):
    """Share of the provision's word n-grams found in the answer (paper: word 5-gram containment).
    Provisions shorter than n words count as one gram of their full length."""
    t = toks(prov_text)
    if not t:
        return None
    k = min(n, len(t))
    g = ngram_set(t, k)
    if not g:
        return None
    a = ans.get(k)
    return len(g & a) / len(g)


# ------------------------------------------------------------------ article texts and clause/point parsing
def article_texts(chunks):
    """chunks (chunk_id, doc_id, article_no, part, text) of main-body articles -> {article_id: full text}.
    Parts of split articles are joined with vlonto.build_docs.join_parts (as the KG's local article text)."""
    c = chunks.with_columns(pl.col("chunk_id").str.replace(r"::part-\d+$", "").alias("unit"))
    c = c.filter(pl.col("unit").str.contains(r"::dieu-[^:]+$"))
    out = {}
    for unit, grp in c.sort(["unit", "part"]).group_by("unit", maintain_order=True):
        u = unit[0] if isinstance(unit, tuple) else unit
        out[u] = BD.join_parts(grp["text"].to_list())
    return out


def split_heading(text):
    """Article chunk text = 'Điều N. Title' line + body lines. -> (title_line, body_lines)."""
    lines = (text or "").split("\n")
    head = lines[0] if lines and lines[0].startswith("Điều") else ""
    body = lines[1:] if head else lines
    return head, [l.strip() for l in body if l.strip()]


def parse_units(text):
    """Clauses ('1. ...') and points ('a) ...') of one article, numbered in sequence (quoted amendment text and
    out-of-sequence numbers are body text). Returns (clauses, article_points); clause = {no, lines, points[]},
    point = {letter, lines}."""
    _, body = split_heading(text)
    clauses, art_points = [], []
    cur_c = cur_p = None
    for s in body:
        if s[:1] in QUOTE:
            m = None
        else:
            m = KHOAN_RE.match(s)
        if m:
            n, suf = int(m.group(1)), m.group(2)
            exp = clauses[-1]["n"] + 1 if clauses else 1
            if (not suf and n == exp) or (suf and clauses and n == clauses[-1]["n"] and suf > (clauses[-1]["suf"] or "")):
                cur_c = {"no": f"{n}{suf}", "n": n, "suf": suf, "lines": [s], "points": []}
                clauses.append(cur_c)
                cur_p = None
                continue
        mp = DIEM_RE.match(s) if s[:1] not in QUOTE else None
        if mp:
            letter = mp.group(1)
            cont = cur_c["points"] if cur_c is not None else art_points
            if cont:
                last = cont[-1]["letter"]
                exp = LETTERS[LETTERS.index(last) + 1] if last in LETTERS and LETTERS.index(last) + 1 < len(LETTERS) else None
            else:
                exp = "a"
            if letter == exp:
                cur_p = {"letter": letter, "lines": [s]}
                cont.append(cur_p)
                if cur_c is not None:
                    cur_c["lines"].append(s)
                continue
        if cur_p is not None:
            cur_p["lines"].append(s)
        if cur_c is not None:
            cur_c["lines"].append(s)
    return clauses, art_points


def norm_clause_no(c):
    if c is None:
        return None
    m = re.match(r"^0*(\d{1,3})([a-zđ]?)$", str(c).strip().lower())
    return f"{int(m.group(1))}{m.group(2)}" if m and int(m.group(1)) > 0 else None


def norm_point(p):
    if p is None:
        return None
    p = str(p).strip().lower().rstrip(")")
    return p if p in LETTERS else None


class Structure:
    """Per-article units with labels, KG-style ids and provision texts (texts stay in memory only)."""
    def __init__(self, art_text):
        self.art_text = art_text
        self.cache = {}
        self.norm_cache = {}

    def norm(self, aid):
        if aid not in self.norm_cache:
            self.norm_cache[aid] = norm_text(self.art_text.get(aid, ""))
        return self.norm_cache[aid]

    def units(self, aid):
        if aid not in self.cache:
            self.cache[aid] = parse_units(self.art_text.get(aid, ""))
        return self.cache[aid]

    def article_prov_text(self, aid):
        head, body = split_heading(self.art_text.get(aid, ""))
        title = HEAD_RE.sub("", head).strip()
        return "\n".join(([title] if title else []) + body)

    def resolve(self, aid, clause, point):
        """-> (unit kind, unit id, clause_no, point_letter, provision text, note). Most specific unit that exists."""
        clauses, apoints = self.units(aid)
        k, p = norm_clause_no(clause), norm_point(point)
        if k:
            cl = next((c for c in clauses if c["no"] == k), None)
            if cl is None:
                return "article", aid, None, None, self.article_prov_text(aid), "clause_not_found"
            if p:
                pt = next((x for x in cl["points"] if x["letter"] == p), None)
                if pt is None:
                    return "clause", f"{aid}::khoan-{k}", k, None, LEAD_ENUM.sub("", "\n".join(cl["lines"]), count=1), "point_not_found"
                return "point", f"{aid}::khoan-{k}::diem-{p}", k, p, LEAD_ENUM.sub("", "\n".join(pt["lines"]), count=1), None
            return "clause", f"{aid}::khoan-{k}", k, None, LEAD_ENUM.sub("", "\n".join(cl["lines"]), count=1), None
        if p:
            pt = next((x for x in apoints if x["letter"] == p), None)
            if pt is not None:
                return "point", f"{aid}::diem-{p}", None, p, LEAD_ENUM.sub("", "\n".join(pt["lines"]), count=1), None
            return "article", aid, None, None, self.article_prov_text(aid), "point_without_clause_not_found"
        return "article", aid, None, None, self.article_prov_text(aid), None


# ------------------------------------------------------------------ labels
def roman_or_num(tok):
    if tok is None:
        return None
    t = str(tok)
    return t.upper() if re.match(r"^[ivxlcdm]+$", t) else t


def art_no_of(aid):
    return aid.split("::", 1)[1].replace("dieu-", "", 1)


def unit_labels(kind, aid, k=None, p=None):
    n = art_no_of(aid)
    if kind == "article":
        return f"Điều {n}", f"Art. {n}"
    if kind == "clause":
        return f"Khoản {k} Điều {n}", f"Art. {n}({k})"
    if kind == "point":
        if k:
            return f"Điểm {p} khoản {k} Điều {n}", f"Art. {n}({k})({p})"
        return f"Điểm {p} Điều {n}", f"Art. {n}({p})"
    raise ValueError(kind)


def struct_labels(kind, number, heading):
    num = roman_or_num(number)
    if num and str(number).startswith("o") and re.match(r"^o\d+$", str(number)):
        num = None
    if kind == "Chapter":
        if not num:
            m = re.match(r"^\s*(?:Chương|CHƯƠNG)\s+(\S+)", heading or "")
            num = m.group(1).strip(".:") if m else "?"
        return f"Chương {num}", f"Chapter {num}"
    if kind == "Section":
        if not num:
            m = re.match(r"^\s*(?:Mục|MỤC)\s+(\S+)", heading or "")
            num = m.group(1).strip(".:") if m else "?"
        return f"Mục {num}", f"Section {num}"
    raise ValueError(kind)


# ------------------------------------------------------------------ person names in titles
HONORIFIC = re.compile(r"(?:^|[\s,(])(?:ông|bà|anh|chị|cô|chú|bác|em|cháu|Ông|Bà|Anh|Chị|Cô|Chú|Bác|Em|Cháu)\s+[A-ZĐÂĂÊÔƠƯ][a-zà-ỹđ]+(?:\s+[A-ZĐÂĂÊÔƠƯ][a-zà-ỹđ]+){0,3}")
SURNAME = re.compile(r"\b(?:Nguyễn|Trần|Lê|Phạm|Hoàng|Huỳnh|Phan|Vũ|Võ|Đặng|Bùi|Đỗ|Hồ|Ngô|Dương|Lý|Đinh|Trịnh|Đào|Mai|Lương|Tô|Hà|Cao|Lâm|Thái|Tạ|Châu)(?:\s+[A-ZĐÂĂÊÔƠƯ][a-zà-ỹđ]+){1,3}\b")
NOT_NAMES = {"Hà Nội", "Lê Lợi", "Hồ Chí Minh", "Cao Bằng", "Thái Bình", "Thái Nguyên", "Hà Giang", "Hà Nam", "Hà Tĩnh",
             "Lâm Đồng", "Châu Đốc", "Đào Tạo", "Lương Hưu", "Mai Táng", "Lý Lịch", "Hà Tiên", "Tô Lịch", "Phan Thiết", "Đồng Nai",
             "Bà Rịa", "Cô Tô", "Hà Đông", "Ông Ích Khiêm", "Châu Thành", "Hồ Gươm", "Hoàng Sa", "Trường Sa"}


def person_name_hits(title):
    hits = []
    for rx in (HONORIFIC, SURNAME):
        for m in rx.finditer(title or ""):
            s = m.group(0).strip(" ,(")
            if any(s.endswith(x) or s == x or x in s for x in NOT_NAMES):
                continue
            hits.append(s)
    return hits


# ------------------------------------------------------------------ citations of one answer (stage_gold, per citation)
def citation_outcomes(q, ER, d_by_id, by_key, by_name, arts_set, main_art_set, doc_resolver):
    """Replicates eval_retrieval.stage_gold for ONE Q&A but keeps every citation with its outcome.
    Provision citations: status 'resolved' (doc_id, article, method) when stage_gold would emit a gold item, plus
    'drawn' when the article is a main-body article (the KG edge filter); otherwise the reason it was dropped.
    Document citations: resolved like vlonto.build_other.build_qa (DocResolver.by_number with the law type hint)."""
    cits = q["citations"] or []
    pub = (q["published_date"] or "")[:10]
    ans = V.nfc(q["answer"] or "")
    docs_of_type = defaultdict(set)
    for c in cits:
        if c["kind"] == "document" and c["id"]:
            for r in by_key.get(V.docnum_key(c["id"]), []):
                docs_of_type[c["law_type"]].add(r["id"])
    out = []
    for c in cits:
        rec = {"kind": c["kind"], "ref": C.cut(c["ref"], 160), "law_type": c["law_type"], "law_name": (c["law_name"] or None),
               "number": c["id"], "year": c["year"], "article": c["article"], "clause": c["clause"], "point": c["point"]}
        if c["kind"] == "document":
            if not c["id"]:
                rec.update(status="unresolved", reason="no_number")
            else:
                th = c["law_type"] if c["law_type"] in C.DOC_TYPES else None
                d, how = doc_resolver.by_number(c["id"], th, pub or None)
                if d:
                    rec.update(status="resolved", doc_id=d, method=how)
                else:
                    rec.update(status="unresolved", reason=how)
            out.append(rec)
            continue
        art = (c["article"] or "").strip()
        if not art or not re.match(r"^\d{1,3}[a-zđ]?$", art):
            rec.update(status="unresolved", reason="provision_bad_article")
            out.append(rec)
            continue
        typ, name, year = c["law_type"], (c["law_name"] or "").strip(), c["year"]
        res, method = None, None
        ex = ER.explicit_mention(ans, art)
        if ex:
            if ex[0] == "num":
                rr = by_key.get(V.docnum_key(ex[2]), [])
                if rr:
                    res, method = rr[0], "answer_text:number"
            elif ex[1] in ER.NAME_TYPES:
                res, how = ER.resolve_name(by_name, ex[1], ex[2], ex[3], pub)
                method = f"answer_text:{how}" if res else None
        if res is None and name and typ in ER.NAME_TYPES:
            res, how = ER.resolve_name(by_name, typ, name, year, pub)
            method = f"citation_field:{how}" if res else None
        if res is None and not name and len(docs_of_type.get(typ, ())) == 1:
            res = d_by_id[next(iter(docs_of_type[typ]))]
            method = "unique_document_of_type"
        if res is None:
            rec.update(status="unresolved", reason="law_not_resolved")
        elif (res["id"], art) not in arts_set:
            rec.update(status="unresolved", reason="article_not_parsed", doc_id=res["id"], method=method)
        else:
            na = norm_article(art)
            drawn = (res["id"], na) in main_art_set
            rec.update(status="resolved" if drawn else "unresolved", reason=None if drawn else "appendix_or_unmatched_article",
                       doc_id=res["id"], article_no=na, method=method)
        out.append(rec)
    return out


# ------------------------------------------------------------------ English law names
SMALL = {"a", "an", "and", "of", "on", "the", "to", "for", "in", "with", "by", "at", "or", "from", "into", "under", "via"}


def title_case(s):
    ws = s.split()
    out = []
    for i, w in enumerate(ws):
        lw = w.lower()
        if i > 0 and lw in SMALL:
            out.append(lw)
        elif w.isupper() and len(w) > 1 and re.match(r"^[A-Z0-9\-]+$", w) and lw not in ("law", "code"):
            out.append(w)                       # acronyms (VAT, SMEs)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


EN_PREFIX = re.compile(r"^(?:Law|Code|Decree|Circular|Resolution|Ordinance|Constitution|Decision|Joint\s+Circular|Joint\s+Resolution|Order)"
                       r"\s+(?:No\.?\s+)?\d+[a-zA-Z]?\s+\d{4}\s+[A-Za-z0-9\-]+\s+(?:of\s+[A-Z][a-z]+\s+\d{1,2}\s+\d{4}\s+)?", re.I)


def english_name_from_record(title, doc_type):
    """English record slug title ('Law 31 2024 QH15 on Land', 'Law No 100 2015 QH13 criminal code') -> 'Law on Land',
    'Criminal Code'. Only for codes, laws, ordinances and constitutions."""
    if not title:
        return None
    rest = EN_PREFIX.sub("", title.strip()).strip()
    if not rest or rest == title.strip():
        return None
    rest = re.sub(r"^(?:the|The)\s+", "", rest)
    low = rest.lower()
    if doc_type == "Bộ luật" or low.endswith(" code") or low == "code":
        return title_case(rest)
    if doc_type == "Hiến pháp":
        return "Constitution"
    if doc_type == "Pháp lệnh":
        return ("Ordinance " + title_case(rest)) if not low.startswith("ordinance") else title_case(rest)
    if low.startswith("on "):
        return "Law on " + title_case(rest[3:])
    if low.startswith(("amend", "amending", "amendments", "law ")):
        return "Law " + rest[0].lower() + rest[1:] if not low.startswith("law ") else title_case(rest)
    return "Law on " + title_case(rest)


# ------------------------------------------------------------------ graph container
class TraceGraph:
    def __init__(self):
        self.nodes, self.order, self.links = {}, [], {}

    def node(self, nid, cls, label_vi, label_en, url=None, prov=None):
        if nid not in self.nodes:
            self.nodes[nid] = {"id": nid, "cls": cls, "label_vi": label_vi, "label_en": label_en, "url": url,
                               "on_trace": False, "verified": False, "provenance": prov or {}}
            self.order.append(nid)
        return nid

    def link(self, s, t, kind):
        k = (s, t, kind)
        if k not in self.links:
            self.links[k] = {"s": s, "t": t, "kind": kind, "on_trace": False, "verified": False}
        return k

    def mark_path(self, seq, verified, link_kinds):
        """seq: node ids along a path; link_kinds: {(a, b): key} lookup for consecutive pairs."""
        for nid in seq:
            self.nodes[nid]["on_trace"] = True
            if verified:
                self.nodes[nid]["verified"] = True
        for a, b in zip(seq, seq[1:]):
            k = link_kinds.get((a, b)) or link_kinds.get((b, a))
            if k is not None:
                self.links[k]["on_trace"] = True
                if verified:
                    self.links[k]["verified"] = True


# ------------------------------------------------------------------ terms
def term_base(name):
    return re.split(r"\s*\(", name or "")[0].strip()


def build_term_index(tnpl_rows):
    """{token tuple of the term name (before any parenthesis): [term rows]} for names of >= 2 syllables."""
    idx = defaultdict(list)
    for r in tnpl_rows:
        t = tuple(toks(term_base(r["term_name_vi"])))
        if len(t) >= 2:
            idx[t].append(r)
    return idx


def find_term_mentions(texts, idx, maxlen=12):
    """texts: [(source, text)] -> non-overlapping longest matches [(key, source, start)] in text order."""
    out = []
    for src, text in texts:
        t = toks(text)
        taken = [False] * len(t)
        hits = []
        for i in range(len(t)):
            for n in range(min(maxlen, len(t) - i), 1, -1):
                key = tuple(t[i:i + n])
                if key in idx:
                    hits.append((n, i, key))
                    break
        for n, i, key in sorted(hits, key=lambda h: (-h[0], h[1])):
            if any(taken[i:i + n]):
                continue
            for j in range(i, i + n):
                taken[j] = True
            out.append((key, src, i))
    seen, res = set(), []
    for key, src, i in sorted(out, key=lambda h: (h[1] != "title", h[2])):
        if key not in seen:
            seen.add(key)
            res.append((key, src, i))
    return res


DEF_TAIL = r"(?:\s*\([^)]{0,160}\))?\s*(?:là|được hiểu là)\s"


def norm_text(s):
    return V.tone_new_style(V.nfc(s or "")).lower()


def find_defining_unit(key, doc_ids, arts_by_doc, S, name_raw):
    """First clause/point whose text (enumerator stripped) starts with the term name followed by 'là' / 'được hiểu
    là' (paper: definitional pattern 'X là ...'), searching the given documents in order."""
    pat = re.compile("^" + re.escape(norm_text(name_raw)) + DEF_TAIL)
    needle = norm_text(name_raw)
    for doc in doc_ids:
        for aid in arts_by_doc.get(doc, []):
            if aid not in S.art_text or needle not in S.norm(aid):
                continue
            clauses, apoints = S.units(aid)
            for cl in clauses:
                body = LEAD_ENUM.sub("", cl["lines"][0], count=1)
                if pat.match(norm_text(body)):
                    return ("clause", f"{aid}::khoan-{cl['no']}", aid, cl["no"], None, LEAD_ENUM.sub("", "\n".join(cl["lines"]), count=1))
                for pt in cl["points"]:
                    body = LEAD_ENUM.sub("", pt["lines"][0], count=1)
                    if pat.match(norm_text(body)):
                        return ("point", f"{aid}::khoan-{cl['no']}::diem-{pt['letter']}", aid, cl["no"], pt["letter"],
                                LEAD_ENUM.sub("", "\n".join(pt["lines"]), count=1))
            for pt in apoints:
                body = LEAD_ENUM.sub("", pt["lines"][0], count=1)
                if pat.match(norm_text(body)):
                    return ("point", f"{aid}::diem-{pt['letter']}", aid, None, pt["letter"], LEAD_ENUM.sub("", "\n".join(pt["lines"]), count=1))
    return None
