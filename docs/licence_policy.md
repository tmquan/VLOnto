# VLOnto source licences and inclusion policy

Version 0.1.0, decided 2026-11-11 from the cards (`README.md`) of the six source datasets, downloaded at the pinned revisions below.
Card copies: `build/cards/<dataset>.README.md` (relative to the VLOnto root).
This is a reading of the cards by the build agent, not legal advice. Items marked **(user decision)** are judgement calls the project owner should confirm before publishing.

## 1. Sources

| Dataset (Hugging Face, owner `tmquan`) | Revision | Card licence | What the card grants or asks | Card sha256 (first 12) |
|---|---|---|---|---|
| `thuvienphapluat-vn-vbpl` | `705ade585384108ded5fc30f40a06fe110bdff22` | `cc-by-4.0` | CC BY 4.0 covers the **metadata** (identity columns parsed from the public slug). "Original document bodies are © thuvienphapluat.vn." Informational, not legal advice. | `0cec7fb1d412` |
| `thuvienphapluat-vn-hdpl` | `e814ecbfa1a1c0c32727c2f2ad2498d52f04b8bd` | `other` | "content © thuvienphapluat.vn, redistributed for research." No open grant. | `bc3ad6da92df` |
| `thuvienphapluat-vn-tnpl` | `f94d1e24852f233e85330c6d5093f43adbddde29` | `other` (`vietnamese-public-legal-terminology`) | Community-authored content without a formal open licence. Expectations: (1) attribute `thuvienphapluat.vn/tnpl/`; (2) keep the translation-provenance columns and do not present the English text as official statute; (3) treat `updated_by_*` as low-sensitivity PII; (4) Vietnamese law and source terms apply. | `9d00fdc58089` |
| `thuvienphapluat-vn-htpl` | `043c8f2988e248f1123ead53a54e3cbf83a02e44` | `other` | No grant stated; content from thuvienphapluat.vn. | `31a356568370` |
| `anle-toaan-gov-vn` | `d6124923ddcba618811644f433de7c748a291e22` | `cc-by-4.0` | Judicial documents are excluded from copyright (Art. 15, Law on Intellectual Property), so CC BY 4.0 covers the curation, structure, annotations and embeddings. Party names are anonymised by the courts (Resolution 03/2017/NQ-HĐTP); names of judges, prosecutors and clerks remain; do not re-identify parties. | `ba6e91f33d0a` |
| `cbba-toaan-gov-vn` | `8ace3afc9c974afd51e12dccbefd4b3ba54ce1ec` | `cc-by-4.0` | CC BY 4.0 with expectations: (1) attribute `congbobanan.toaan.gov.vn`; (2) do not present the extraction as official legal text; (3) respect the sensitivity of case data; (4) comply with Vietnamese law. | `4992c9a1c2be` |

## 2. Inclusion rules applied by the build

General rules, all sources:

1. **No person names.** Fields that hold names of people are never read into KG tables: `vbpl.signer`, `hdpl.author`, `tnpl.updated_by_vi/_en`, and the judgment bodies (`markdown`) of `anle`/`cbba`, which contain names of judges, prosecutors, clerks and (anonymised) parties. Court and issuing-body names are institution names and are kept.
2. **No body text from `other`-licensed sources.** For `hdpl`, `tnpl` and `htpl` the KG keeps identifiers, URLs, dates, categories/areas and derived edges only.
3. **Derived edges are VLOnto's own work.** Resolved citation, legal-basis, change and mention edges, with the method that produced them, are released with VLOnto.
4. **Full statutory text is not redistributed** (see 2.1). Each document and provision keeps its source URL so that users read the text at the source.

Exception to rule 2, on the website only (not in the KG tables or dumps): the Traces page shows the titles of the questions it traces (see 2.2).

### 2.1 `vbpl` — legal documents (CC BY 4.0 metadata)

| Included | Excluded |
|---|---|
| id, document type, number, number key, year, tier, issuer code and issuer kind, legal area, source URL | `vn_text`, `en_text` (document bodies, © thuvienphapluat.vn per card) |
| issue / effective / status dates, raw status string, validity derived by VLOnto (rules v7) | `signer` (person name) |
| Vietnamese title of the act (a factual name such as *Bộ luật Lao động*) | `pdf_url`, `docx_url`, `download_id`, `checksum` (not needed) |
| article numbers and short article headings (cut at 200 characters), chapter / section / appendix headings, used as provision labels | full article text |
| change relations with the one-sentence evidence quote (cut at 300 characters) that supports each relation | |
| legal-basis (`parent_acts`) and citation edges with the short raw reference string (e.g. *Nghị định số 95/2017/NĐ-CP*) | |

**(user decision)** The task brief proposed to keep article text for CC BY sources. The `vbpl` card restricts CC BY 4.0 to metadata and states that document bodies are © thuvienphapluat.vn, so the published KG tables do **not** contain article text. Vietnamese statutory text itself is outside copyright protection (Art. 15 of the Law on Intellectual Property, the same provision the `anle` card cites for judicial documents); the restriction concerns this particular transcription. Titles, headings and one-sentence evidence quotes are kept as short factual labels needed to identify provisions and to verify extracted relations. The article text is written to a separate local table (`$V/build/kg_local/article_text.parquet`, never published) and `vlonto build --with-article-text` adds it to the release tables if the owner decides that publication is acceptable.

### 2.2 `hdpl` — legal Q&As (`other`)

| Included | Excluded |
|---|---|
| Q&A id, source URL, published date, category slug, legal area | `question`, `answer`, `answer_html`, `summary` (text, © thuvienphapluat.vn) |
| derived citation edges: Q&A → document, Q&A → article (+ clause/point), with the resolution method and the short reference string (e.g. *Điều 50 Luật Việc làm*) | `keywords` (derived from the text) |
| | `author` (person name), `content_flags` (contain text snippets) |

**Traces page (website only).** The Traces page (`site/traces.html`, data `site/data/traces/`, built by `scripts/traces/` and `scripts/site/trace_site.py`) shows 540 traces in 27 legal areas. For the 538 questions it traces it shows the `summary` field (the question's title as published on thuvienphapluat.vn) with the source URL and a machine-assisted English gloss of at most 15 words, marked as machine-assisted on the page; and VLOnto's derived scores (word 5-gram containment between the answer and the cited provision). It shows no `question`, `answer` or `answer_html` text, no `keywords`, `author` or `content_flags`. The build reads answer texts in memory to compute the scores and writes only the scores; the citations as written in the answers are dropped, and the other answers of an area are shown by their id (*Câu hỏi #id · Question #id*). Titles that hold a person name are not selected (regular expressions and a model check; the one title the model flagged is kept in the build cache only as a SHA-256 hash). The titles remain subject to the source terms of thuvienphapluat.vn.

### 2.3 `tnpl` — legal terms (`other`, community-authored)

| Included | Excluded |
|---|---|
| term id, source URL, Vietnamese term name, English term name with its provenance (`term_name_source`: `mt` machine translation or `site`; `translation_model_id`) | `definition_vi`, `definition_en` (community-authored text without an open licence) |
| area (Vietnamese label, English label marked as provenance `mt` where machine-translated), status (*Còn hiệu lực*/*Hết hiệu lực*), related-term links | `updated_by_vi`, `updated_by_en` (PII per card) |
| | rows with `fetch_status = not_found` (empty placeholders) |

Term names are kept because they are short labels (one legal term each) that identify the concept and carry no creative expression; the card's translation-provenance expectation is honoured by keeping `term_name_source` and `translation_model_id` with every English label, and the English labels are documented as machine translations, not official terms.

### 2.4 `htpl` — legal news (`other`)

| Included | Excluded |
|---|---|
| article id, source URL, category, published date | `title`, `summary`, `body` |
| derived document-mention edges (document numbers found in title/body by regex, resolved to in-scope documents) | |

### 2.5 `anle` and `cbba` — court documents (CC BY 4.0)

| Included | Excluded |
|---|---|
| decision id (`doc_name`), official decision number and code, category, instance level, court level, issued date, precedent flag and precedent number, web URL | `markdown` (judgment text: contains names of judges, prosecutors, clerks and anonymised parties) |
| court institution name parsed from the judgment header (e.g. *Tòa án nhân dân tỉnh …*), only when it matches the institution pattern | any person name; `pdf_url` (not needed) |
| applied-provision edges (decision → document / article / clause / point) and case-to-case edges derived from the dataset's citation annotations, with method and the source `sentence_id` pointer | citation `span` text windows |

Judgment text could be redistributed under the cards, but VLOnto does not need it and leaving it out keeps personal data out of the KG.

## 3. Licence of VLOnto outputs

* Ontology (`vlonto.ttl`, `vlonto-shapes.ttl`, documentation): **CC BY 4.0**, creator tmquan.
* Website Traces page data (`site/data/traces/`): VLOnto's traces, scores and drawings under **CC BY 4.0**; the titles of the 538 traced questions it holds remain subject to the source terms of thuvienphapluat.vn (see 2.2).
* Knowledge-graph tables and RDF dumps: VLOnto's own contributions (resolution, structure, derived edges, validity) are released under **CC BY 4.0**; records derived from the `other`-licensed sources (`hdpl`, `tnpl`, `htpl`) contain only identifiers, links, dates, categories, short labels and derived edges, and remain subject to the source terms of thuvienphapluat.vn.
* Every source dataset is described in the graph as a `vlo:SourceDataset` with revision, licence IRI and attribution text, and every node carries `vlo:sourceDataset`.

## 4. Attribution text (use on the website, in the GitHub repository and in the playbook)

> VLOnto is derived from six datasets published on Hugging Face by TMQuan: `thuvienphapluat-vn-vbpl` (metadata CC BY 4.0; source thuvienphapluat.vn), `thuvienphapluat-vn-hdpl`, `thuvienphapluat-vn-tnpl` and `thuvienphapluat-vn-htpl` (source thuvienphapluat.vn and thuvienphapluat.vn/tnpl/; only identifiers, links, dates, categories, term names and derived links are used), `anle-toaan-gov-vn` (CC BY 4.0; source anle.toaan.gov.vn, Supreme People's Court of Viet Nam) and `cbba-toaan-gov-vn` (CC BY 4.0; source congbobanan.toaan.gov.vn, Supreme People's Court of Viet Nam). English term labels from `tnpl` are machine translations. Extracted relations are produced automatically and may be wrong. VLOnto is not an official legal text and is not legal advice.

Vietnamese:

> VLOnto được xây dựng từ sáu bộ dữ liệu do TMQuan công bố trên Hugging Face: `thuvienphapluat-vn-vbpl` (siêu dữ liệu theo CC BY 4.0; nguồn thuvienphapluat.vn), `thuvienphapluat-vn-hdpl`, `thuvienphapluat-vn-tnpl`, `thuvienphapluat-vn-htpl` (nguồn thuvienphapluat.vn; chỉ dùng mã định danh, liên kết, ngày, lĩnh vực, tên thuật ngữ và các liên kết suy ra), `anle-toaan-gov-vn` (CC BY 4.0; nguồn anle.toaan.gov.vn, Tòa án nhân dân tối cao) và `cbba-toaan-gov-vn` (CC BY 4.0; nguồn congbobanan.toaan.gov.vn, Tòa án nhân dân tối cao). Tên tiếng Anh của thuật ngữ là bản dịch máy. Các quan hệ được trích xuất tự động và có thể sai. VLOnto không phải văn bản pháp luật chính thức và không phải tư vấn pháp lý.
