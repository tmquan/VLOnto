"""Documents, issuing bodies, legal areas, articles and document structure, change events."""
import os
import re
import time
from collections import Counter, defaultdict

import polars as pl

from . import config as C
from . import vnlegal_text as VT

TYPE_ABBR = {"TT", "TTLT", "ND", "QD", "NQ", "NQLT", "PL", "L", "HP", "BL", "CT", "TTLB", "LB", "QDLB", "QDLT", "LT",
             "SL", "LCT", "VBHN", "QDTTG", "NDCP", "TB", "HD", "KH", "CV", "QDCT", "QDBT", "BC"}
KIND_TO_ISSUER = {"Thủ tướng": "TTG", "Chính phủ": "CP", "Quốc hội": "QH", "UB Thường vụ QH": "UBTVQH",
                  "Hội đồng Bộ trưởng": "HDBT", "Chủ tịch nước": "CTN", "HĐND tỉnh/TP": "HDND"}


def issuer_codes(number):
    """'20/2017/TT-BYT' -> ['BYT']; '117/2007/TTLT-BTC-BLĐTBXH' -> ['BTC','BLDTBXH']; '45/2019/QH14' -> ['QH']."""
    if not number:
        return []
    parts = number.split("/")
    sym = parts[-1] if len(parts) >= 2 else (number.split("-", 1)[1] if "-" in number else "")
    out = []
    for t in re.split(r"[-–]", sym):
        a = C.strip_diacritics(t).upper()
        a = re.sub(r"[^A-Z0-9]", "", a)
        a = re.sub(r"\d+$", "", a)
        if not a or a in TYPE_ABBR or not re.match(r"^[A-Z]{1,12}$", a):
            continue
        if a not in out:
            out.append(a)
    return out


def chapter_token(heading, word):
    m = re.match(r"^\s*%s\s+([IVXLCDM]+|\d+[a-zA-Z]?)\b" % word, heading or "", re.I)
    return m.group(1).lower() if m else None


def join_parts(texts):
    """Join the text of an article's chunk parts, dropping the repeated '(phần k/n)' heading line, the
    continuation marker '[…]' and the overlap with the previous part."""
    out = ""
    for k, t in enumerate(texts):
        t = t or ""
        if k > 0:
            lines = t.split("\n", 1)
            if re.match(r"^Điều\s+\S+.*\(phần\s+\d+/\d+\)\s*$", lines[0]) and len(lines) > 1:
                t = lines[1]
            t = re.sub(r"^\s*\[…\]\s*", "", t)
            best = 0
            for L in range(min(len(out), len(t), 600), 20, -1):
                if out.endswith(t[:L]):
                    best = L
                    break
            t = t[best:]
            out = out + ("\n" if best == 0 else "") + t
        else:
            out = t
    return out


def clean_title(t, doc_type, issue):
    """Constitution titles in the source end with the first heading ('lời nói đầu') and the 1959/2013 ones carry no year."""
    if t and doc_type == "Hiến pháp":
        t = re.sub(r"\s+lời nói đầu\s*$", "", t, flags=re.I).strip()
        if issue and not re.search(r"(?:19|20)\d{2}", t):
            t = f"{t} năm {issue[:4]}"
    return t


def build_documents(rep):
    t0 = time.time()
    d = pl.read_parquet(C.PROCESSED["docs_clean"], columns=[
        "id", "doc_type", "year", "tier", "issuer", "issuer_kind", "legal_area", "url", "doc_number", "doc_number_key",
        "issue_date", "effective_date_meta", "status_raw", "status_code", "status_date", "title_vi", "title_core", "excluded_reason"])
    rep["docs_clean_rows"] = d.height
    rep["docs_excluded_rows"] = int(d["excluded_reason"].is_not_null().sum())
    d = d.filter(pl.col("excluded_reason").is_null())
    v = pl.read_parquet(C.PROCESSED["validity"], columns=["id", "validity", "in_force", "effective_date", "effective_date_src",
                                                          "expiry_date", "status_text_conflict", "evidence_source", "as_of"])
    rep["validity_rows"] = v.height
    rep["validity_as_of"] = sorted(set(v["as_of"].drop_nulls().to_list()))
    d = d.join(v, on="id", how="left")
    st = pl.read_parquet(C.PROCESSED["doc_struct"], columns=["id", "n_articles", "has_articles", "n_chapters"])
    d = d.join(st, on="id", how="left")
    rows = []
    issuer_method = Counter()
    label_to_code = {re.sub(r"[^a-z0-9]", "", C.strip_diacritics(v[0]).lower()): k for k, v in C.ISSUERS.items()}
    date_checks = Counter()
    for r in d.iter_rows(named=True):
        issue, issue_src = r["issue_date"], None
        ny = re.search(r"/((?:19|20)\d{2})/", r["doc_number"] or "")
        idchk = "ok" if issue else "missing"
        if issue and ny and abs(int(issue[:4]) - int(ny.group(1))) > 1:
            # e.g. 76/2023/TT-BTC carrying 2015-06-25 (the date of the law it implements)
            issue_src, issue, idchk = issue, None, "year_mismatch_with_number"
        date_checks[idchk] += 1
        year = int(issue[:4]) if issue else (int(ny.group(1)) if ny else r["year"])
        raw = issuer_codes(r["doc_number"])
        codes = list(dict.fromkeys(C.ISSUER_ALIASES.get(c, c) for c in raw if C.ISSUER_ALIASES.get(c, c) in C.ISSUERS))
        unmatched = [c for c in raw if C.ISSUER_ALIASES.get(c, c) not in C.ISSUERS]
        how = "issuer-code" if codes else None
        if r["doc_type"] in ("Hiến pháp", "Luật", "Bộ luật"):
            # constitutions, codes and laws are adopted by the National Assembly whatever the promulgation symbol
            if codes != ["QH"]:
                how = "doc-type-rule"
            codes = ["QH"]
        elif r["doc_type"] == "Pháp lệnh" and "CTN" in codes:
            # 'L/CTN' is the President's promulgation order; ordinances are adopted by the Council of State
            # (1981-1992) or the Standing Committee of the National Assembly
            codes = [c for c in codes if c != "CTN"] or (["HDNN"] if year and 1981 <= int(year) < 1992 else ["UBTVQH"])
            how = "doc-type-rule"
        if not codes and r["issuer"]:
            a = re.sub(r"[^A-Z0-9]", "", C.strip_diacritics(r["issuer"]).upper())
            a = C.ISSUER_ALIASES.get(a, a)
            b = label_to_code.get(re.sub(r"[^a-z0-9]", "", C.strip_diacritics(r["issuer"]).lower()))
            if a in C.ISSUERS or b:
                codes, how = [a if a in C.ISSUERS else b], "source-metadata"
        if not codes and r["issuer_kind"] in KIND_TO_ISSUER:
            codes, how = [KIND_TO_ISSUER[r["issuer_kind"]]], "source-metadata"
        if not codes:
            how = "code-unknown" if unmatched else "none"
        issuer_method[how] += 1
        cls, concept, notation = C.DOC_TYPES[r["doc_type"]]
        rank = C.legal_force_rank(r["doc_type"], r["doc_number"])
        area = C.slugify(r["legal_area"]) if r["legal_area"] else None
        rows.append({
            "doc_id": r["id"], "iri": C.iri_doc(r["id"]), "doc_type_vi": r["doc_type"], "doc_class": cls,
            "doc_type_code": notation, "doc_number": r["doc_number"], "doc_number_key": r["doc_number_key"],
            "title_vi": clean_title(r["title_vi"], r["doc_type"], issue), "title_core": r["title_core"], "issue_date": issue, "issue_date_check": idchk,
            "issue_date_source": issue_src, "year": year,
            "effective_date": r["effective_date"], "effective_date_src": r["effective_date_src"], "expiry_date": r["expiry_date"],
            "status_raw": r["status_raw"], "status_code": r["status_code"], "status_date": r["status_date"],
            "validity": r["validity"] or "unknown", "in_force": r["in_force"], "status_text_conflict": bool(r["status_text_conflict"]),
            "validity_evidence": r["evidence_source"], "legal_force_rank": rank, "area_id": area,
            "issuer_ids": codes, "issuer_method": how, "issuer_codes_unmatched": unmatched, "tier": r["tier"], "url": r["url"],
            "n_chapters": r["n_chapters"], "has_articles": bool(r["has_articles"]),
            "source_dataset": "thuvienphapluat-vn-vbpl"})
    docs = pl.DataFrame(rows, infer_schema_length=None)
    rep["documents"] = docs.height
    rep["documents_by_type"] = dict(Counter(docs["doc_type_vi"].to_list()))
    rep["documents_by_rank"] = {str(k): v for k, v in sorted(Counter(docs["legal_force_rank"].to_list()).items())}
    rep["documents_by_validity"] = dict(Counter(docs["validity"].to_list()))
    rep["issuer_method"] = dict(issuer_method)
    rep["documents_issue_date_check"] = dict(date_checks)
    rep["documents_without_number"] = int(docs["doc_number"].is_null().sum())
    rep["wall_documents_s"] = round(time.time() - t0, 1)
    return docs


def build_issuers(docs, rep):
    cnt = Counter(c for codes in docs["issuer_ids"].to_list() for c in (codes or []))
    rows = []
    for code, n in cnt.most_common():
        vi, en, kind = C.ISSUERS[code]
        aliases = sorted(a for a, c in C.ISSUER_ALIASES.items() if c == code)
        rows.append({"issuer_id": code, "iri": C.iri_issuer(code), "label_vi": vi, "label_en": en, "kind": kind,
                     "label_source": "vlonto-table", "code_aliases": aliases, "n_documents": n})
    iss = pl.DataFrame(rows)
    rep["issuers"] = iss.height
    rep["issuers_named"] = int((iss["label_source"] == "vlonto-table").sum())
    rep["documents_covered_by_named_issuers"] = int(sum(1 for codes in docs["issuer_ids"].to_list() if codes and any(c in C.ISSUERS for c in codes)))
    unm = Counter(c for codes in docs["issuer_codes_unmatched"].to_list() for c in (codes or []))
    rep["issuer_codes_unmatched_top"] = unm.most_common(25)
    rep["documents_with_unmatched_codes_only"] = int(docs.filter(pl.col("issuer_method") == "code-unknown").height)
    return iss


def build_articles(docs, rep, with_text):
    """Articles (main body + appendix), structure nodes (appendix, part, chapter, section) and local article text."""
    t0 = time.time()
    ch = pl.read_parquet(C.PROCESSED["chunks"], columns=["chunk_id", "doc_id", "article_no", "article_title", "chapter", "section",
                                                         "part_name", "attachment", "part", "n_parts", "chars"] + (["text"] if with_text else []))
    ch = ch.with_row_index("row")
    ch = ch.with_columns(pl.col("chunk_id").str.replace(r"::part-\d+$", "").alias("unit"))
    art = ch.filter(pl.col("unit").str.contains(r"::(?:att\d+-)?dieu-[^:]+$"))
    agg = art.group_by("unit", maintain_order=True).agg(
        pl.col("doc_id").first(), pl.col("article_no").first(), pl.col("article_title").first(), pl.col("chapter").first(),
        pl.col("section").first(), pl.col("part_name").first(), pl.col("attachment").first(), pl.col("row").min().alias("row"),
        pl.len().alias("n_chunks"), pl.col("chars").sum().alias("chars"),
        *([pl.col("text").sort_by("part").alias("texts")] if with_text else []))
    agg = agg.sort("row")
    structs = {}          # struct_id -> dict
    struct_order = defaultdict(int)
    art_rows, text_rows = [], []
    pos = defaultdict(int)
    seen_heading_key = {}
    for r in agg.iter_rows(named=True):
        doc = r["doc_id"]
        unit = r["unit"].split("::", 1)[1]
        m = re.match(r"^att(\d+)-dieu-(.+)$", unit)
        seg = f"att{m.group(1)}" if m else "main"
        parent, parent_kind = doc, "Document"
        path = ""
        if seg != "main":
            sid = f"{doc}::{seg}"
            if sid not in structs:
                struct_order[(doc, "Appendix")] += 1
                structs[sid] = {"struct_id": sid, "doc_id": doc, "kind": "Appendix", "number": seg[3:],
                                "heading": C.cut(r["attachment"], 200), "parent_id": doc, "parent_kind": "Document",
                                "position": struct_order[(doc, "Appendix")]}
            parent, parent_kind, path = sid, "Appendix", seg
        for kind, field, word, prefix in (("Part", "part_name", "Phần", "phan"), ("Chapter", "chapter", "Chương", "chuong"),
                                          ("Section", "section", "Mục", "muc")):
            h = r[field]
            if not h:
                continue
            key = (doc, path, kind, h)
            if key in seen_heading_key:
                sid = seen_heading_key[key]
            else:
                tok = chapter_token(h, word) if kind != "Part" else None
                struct_order[(doc, path, kind)] += 1
                if not tok:
                    tok = f"o{struct_order[(doc, path, kind)]}"
                local = f"{prefix}-{tok}"
                p2 = f"{path}/{local}" if path else local
                sid = f"{doc}::{p2}"
                k = 2
                while sid in structs:
                    sid = f"{doc}::{p2}-{k}"
                    k += 1
                seen_heading_key[key] = sid
                struct_order[(doc, kind)] += 1
                structs[sid] = {"struct_id": sid, "doc_id": doc, "kind": kind, "number": tok,
                                "heading": C.cut(h, 200), "parent_id": parent, "parent_kind": parent_kind,
                                "position": struct_order[(doc, kind)]}
            parent, parent_kind = sid, kind
            path = sid.split("::", 1)[1]
        pos[doc] += 1
        aid = r["unit"]
        art_rows.append({"article_id": aid, "iri": C.iri_article(aid), "doc_id": doc,
                         "article_no": m.group(2) if m else r["article_no"],   # appendix chunks carry 'att1:2'; keep the number
                         "segment": seg, "heading": C.cut(r["article_title"], 200), "parent_id": parent,
                         "parent_kind": parent_kind, "position": pos[doc], "n_chunks": r["n_chunks"], "chars": r["chars"],
                         "chapter_heading": C.cut(r["chapter"], 200), "section_heading": C.cut(r["section"], 200)})
        if with_text:
            text_rows.append({"article_id": aid, "text": join_parts(r["texts"])})
    arts = pl.DataFrame(art_rows, infer_schema_length=None)
    st = pl.DataFrame(list(structs.values()), infer_schema_length=None).with_columns(
        pl.col("struct_id").map_elements(C.iri_struct, return_dtype=pl.Utf8).alias("iri"))
    rep["articles_total"] = arts.height
    rep["articles_main"] = int((arts["segment"] == "main").sum())
    rep["articles_appendix"] = int((arts["segment"] != "main").sum())
    rep["docs_with_main_articles"] = int(arts.filter(pl.col("segment") == "main")["doc_id"].n_unique())
    rep["structure_nodes"] = dict(Counter(st["kind"].to_list()))
    rep["structure_fallback_tokens"] = int(st.filter(pl.col("number").str.starts_with("o")).height)
    rep["article_heading_missing"] = int(arts["heading"].is_null().sum())
    rep["wall_articles_s"] = round(time.time() - t0, 1)
    txt = pl.DataFrame(text_rows) if with_text else None
    return arts, st, txt


def build_areas(docs, rep):
    """Area concepts used by documents; hdpl and tnpl areas are added later by build_other."""
    rows = {}
    for slug, n in Counter(docs["area_id"].drop_nulls().to_list()).items():
        vi, en = C.AREA_LABELS.get(slug, (None, None))
        rows[slug] = {"area_id": slug, "label_vi": vi, "label_en": en, "n_documents": n}
    rep["areas_from_documents"] = len(rows)
    rep["areas_without_label"] = [s for s, r in rows.items() if not r["label_vi"]]
    return rows


def build_changes(docs, rep):
    rel = pl.read_parquet(C.PROCESSED["relations"])
    rep["relations_rows"] = rel.height
    rep["relations_by_kind"] = dict(Counter(rel["relation"].to_list()))
    rep["relations_unresolved_rows"] = int((~rel["resolved"].fill_null(False)).sum()) if "resolved" in rel.columns else None
    have = set(docs["doc_id"].to_list())
    vd = {r["doc_id"]: r for r in docs.select("doc_id", "effective_date", "issue_date").iter_rows(named=True)}
    rows, ids = [], Counter()
    missing = 0
    for r in rel.iter_rows(named=True):
        a, b = r["new_id"], r["old_id"]
        if a not in have or b not in have:
            missing += 1
        base = f"{a}-{r['relation'].replace('_', '-')}-{b}"
        ids[base] += 1
        cid = base if ids[base] == 1 else f"{base}-{ids[base]}"
        eff = r["new_effective_date"] or (vd.get(a) or {}).get("effective_date") or (vd.get(a) or {}).get("issue_date")
        rows.append({"change_id": cid, "iri": C.iri_change(cid), "acting_doc_id": a, "affected_doc_id": b,
                     "kind": r["relation"], "evidence": C.cut(r["evidence"], 300), "effective_date": eff,
                     "mentioned_date": r["old_date_mentioned"], "acting_number": r["new_doc_number"],
                     "affected_number": r["old_doc_number"], "affected_number_as_cited": r["old_number"],
                     "method": "validity-rules-v7", "rule_version": "v7"})
    ch = pl.DataFrame(rows, infer_schema_length=None)
    rep["changes"] = ch.height
    rep["changes_with_missing_document"] = missing
    rep["changes_duplicate_id_suffixes"] = int(sum(v - 1 for v in ids.values() if v > 1))
    rep["changes_evidence_truncated"] = int(rel.filter(pl.col("evidence").str.len_chars() > 300).height)
    return ch
