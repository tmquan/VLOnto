# VLOnto knowledge-graph data dictionary

Version 1.0.0 (release v1), built 2026-11-12, document validity as of 2026-11-08. Tables are parquet (zstd) files in `build/kg`; `build/kg_local` holds local-only tables that are not for publication (licence policy). Paths are relative to the VLOnto root.

Release v1 sources: `thuvienphapluat-vn-vbpl`, `thuvienphapluat-vn-hdpl`, `thuvienphapluat-vn-tnpl`, `thuvienphapluat-vn-htpl`. Court data (`anle-toaan-gov-vn`, `cbba-toaan-gov-vn`) is planned for v2: the ontology keeps the judiciary classes, but this build has no court, decision or precedent tables.

IRIs: documents `id/document/<doc_id>`, articles `id/document/<doc_id>/dieu-<n>`, clauses `.../khoan-<k>`, points `.../diem-<p>`, Q&As `id/qa/<id>` (answer `id/qa/<id>/answer`), terms `id/term/<id>`, news `id/news/<id>`, under https://tmquan.github.io/VLOnto/.

## `documents` (40,816 rows)

Legal documents (40,816 in-scope normative documents from vbpl, after cleaning).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `doc_id` | String | 40,816 | vbpl document id (primary key) |
| `iri` | String | 40,816 | VLOnto IRI |
| `doc_type_vi` | String | 40,816 | Vietnamese document type |
| `doc_class` | String | 40,816 | VLOnto class local name (Law, Decree, ...) |
| `doc_type_code` | String | 40,816 | type notation (L, NĐ, TT, ...) |
| `doc_number` | String | 40,215 | official number, e.g. 45/2019/QH14 (null for 601 documents) |
| `doc_number_key` | String | 40,215 | normalised lookup key |
| `title_vi` | String | 40,816 | Vietnamese title |
| `title_core` | String | 36,984 | title without the type word (used for name resolution) |
| `issue_date` | String | 40,502 | issue date (ISO); null when it is more than one year away from the year in the number |
| `issue_date_check` | String | 40,816 | ok, missing or year_mismatch_with_number |
| `issue_date_source` | String | 144 | source issue date when it was rejected |
| `year` | Int64 | 40,720 | issue year (from the number when the date was rejected) |
| `effective_date` | String | 22,076 | entry into force (metadata, then text) |
| `effective_date_src` | String | 22,076 | source of effective_date |
| `expiry_date` | String | 7,256 | no longer in force from |
| `status_raw` | String | 4,356 | source status string (Vietnamese) |
| `status_code` | String | 4,356 | normalised source status |
| `status_date` | String | 2,207 | date in the status string |
| `validity` | String | 40,816 | validity v7 (8 values) |
| `in_force` | Boolean | 12,156 | true/false/null |
| `status_text_conflict` | Boolean | 40,816 | source says in force but text says superseded |
| `validity_evidence` | String | 40,816 | status / text / status+text / none |
| `legal_force_rank` | Int64 | 40,816 | 0 (Constitution) .. 5 (circulars) |
| `area_id` | String | 40,816 | legal area slug |
| `issuer_ids` | List(String) | 40,816 | canonical issuer codes (joint documents have several) |
| `issuer_method` | String | 40,816 | issuer-code (symbol of the number), doc-type-rule (laws, codes, constitutions -> QH; ordinances), source-metadata, code-unknown, none |
| `issuer_codes_unmatched` | List(String) | 40,816 | symbol parts of the number that are not a known issuer (kept for transparency, no node) |
| `tier` | Int64 | 40,816 | vbpl tier (0 primary legislation, 1 central decisions) |
| `url` | String | 40,816 | source URL (thuvienphapluat.vn) |
| `n_chapters` | Int64 | 40,816 | chapters found by the parser |
| `has_articles` | Boolean | 40,816 | article structure parsed |
| `source_dataset` | String | 40,816 | source dataset |
| `n_articles_main` | UInt32 | 40,816 | main-body articles |
| `n_articles_appendix` | UInt32 | 40,816 | appendix articles |

## `articles` (436,309 rows)

Articles (Điều): one node per main-body or appendix article; parts of split articles joined. No text (licence).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `article_id` | String | 436,309 | <doc_id>::dieu-<n> or <doc_id>::att<s>-dieu-<n> (chunk unit id) |
| `iri` | String | 436,309 | VLOnto IRI |
| `doc_id` | String | 436,309 | document |
| `article_no` | String | 436,309 | article number as printed (5, 5a) |
| `segment` | String | 436,309 | main or att<s> (appendix s) |
| `heading` | String | 349,840 | article heading (<=200 chars) |
| `parent_id` | String | 436,309 | immediate parent (structure id or doc_id) |
| `parent_kind` | String | 436,309 | Document/Appendix/Part/Chapter/Section |
| `position` | Int64 | 436,309 | order of the article in its document |
| `n_chunks` | Int64 | 436,309 | retrieval chunks of the article |
| `chars` | Int64 | 436,309 | characters of text |
| `chapter_heading` | String | 315,885 | chapter heading |
| `section_heading` | String | 82,344 | section heading |

## `structure` (73,925 rows)

Appendices, parts, chapters and sections of documents.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `struct_id` | String | 73,925 | <doc_id>::<path> e.g. 333670::chuong-iii/muc-3 |
| `doc_id` | String | 73,925 | document |
| `kind` | String | 73,925 | Appendix/Part/Chapter/Section |
| `number` | String | 73,925 | number token (iii, 3) or o<k> when not parsable |
| `heading` | String | 73,234 | heading (<=200 chars) |
| `parent_id` | String | 73,925 | parent node |
| `parent_kind` | String | 73,925 | kind of parent |
| `position` | Int64 | 73,925 | order among nodes of this kind in the document |
| `iri` | String | 73,925 | VLOnto IRI |

## `provisions_ref` (48,031 rows)

Clauses (khoản) and points (điểm) created because an edge refers to them.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `prov_id` | String | 48,031 | <article_id>::khoan-<k>[::diem-<p>] or <article_id>::diem-<p> |
| `iri` | String | 48,031 | VLOnto IRI |
| `kind` | String | 48,031 | Clause or Point |
| `article_id` | String | 48,031 | article |
| `doc_id` | String | 48,031 | document |
| `clause` | String | 47,957 | clause number |
| `point` | String | 12,555 | point letter |
| `parent_id` | String | 48,031 | article or clause |
| `n_refs` | Int64 | 48,031 | edges that reference this provision |

## `issuers` (57 rows)

Issuing bodies identified by the symbol of the document number (curated table; unknown symbols get no node).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `issuer_id` | String | 57 | canonical ASCII code (BTC, TTG, QH, ...) |
| `iri` | String | 57 | VLOnto IRI |
| `label_vi` | String | 57 | Vietnamese name |
| `label_en` | String | 57 | English name |
| `kind` | String | 57 | ministry, government, national-assembly, ... |
| `label_source` | String | 57 | vlonto-table |
| `code_aliases` | List(String) | 57 | other symbols mapped to this body |
| `n_documents` | Int64 | 57 | documents issued |

## `areas` (51 rows)

Legal areas (SKOS concepts) from vbpl/hdpl (27) and tnpl.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `area_id` | String | 51 | slug |
| `iri` | String | 51 | VLOnto IRI |
| `label_vi` | String | 51 | Vietnamese label |
| `label_en` | String | 51 | English label |
| `label_en_source` | String | 51 | vlonto (written for VLOnto) or tnpl-mt |
| `schemes` | List(String) | 51 | LegalAreaScheme and/or TermAreaScheme |
| `n_documents` | Int64 | 51 | documents |
| `n_qas` | Int64 | 51 | Q&As |
| `n_terms` | Int64 | 51 | terms |

## `doc_types` (10 rows)

Document types (concepts of the ontology).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `doc_type_vi` | String | 10 |  |
| `label_en` | String | 10 |  |
| `class` | String | 10 |  |
| `concept` | String | 10 |  |
| `notation` | String | 10 |  |
| `n_documents` | Int64 | 10 |  |

## `legal_force_ranks` (6 rows)

Legal-force ranks (concepts of the ontology).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `rank` | Int64 | 6 |  |
| `concept` | String | 6 |  |
| `label_en` | String | 6 |  |
| `label_vi` | String | 6 |  |
| `n_documents` | Int64 | 6 |  |

## `changes` (15,035 rows)

Legal change events (validity relations v7), one per relation.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `change_id` | String | 15,035 | <acting>-<kind>-<affected> |
| `iri` | String | 15,035 | VLOnto IRI |
| `acting_doc_id` | String | 15,035 | acting (newer) document |
| `affected_doc_id` | String | 15,035 | affected document |
| `kind` | String | 15,035 | replaced/amended/repealed/partially_repealed/partially_expired |
| `evidence` | String | 15,035 | operative sentence (<=300 chars) |
| `effective_date` | String | 15,002 | effective date of the change |
| `mentioned_date` | String | 12,948 | date of the affected act in the sentence |
| `acting_number` | String | 14,913 | number of acting act |
| `affected_number` | String | 15,035 | number of affected act |
| `affected_number_as_cited` | String | 15,035 | number as written |
| `method` | String | 15,035 | validity-rules-v7 |
| `rule_version` | String | 15,035 | v7 |

## `edges_change` (15,035 rows)

Shortcut edges acting document -> affected document (one per change event).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `src_doc_id` | String | 15,035 | acting document |
| `dst_doc_id` | String | 15,035 | affected document |
| `kind` | String | 15,035 | change kind |
| `property` | String | 15,035 | vlo property |
| `change_id` | String | 15,035 | event |
| `method` | String | 15,035 | validity-rules-v7 |

## `edges_legal_basis` (99,038 rows)

Legal basis: citing document -> basis document.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `src_doc_id` | String | 99,038 | citing document |
| `dst_doc_id` | String | 99,038 | basis document |
| `method` | String | 99,038 | parent-acts, preamble-citation or constitution-preamble (first in this order when several apply) |
| `methods` | List(String) | 99,038 | all methods that found the edge |
| `resolve_method` | String | 99,038 | docnum-key or law-name-year |
| `raw` | String | 99,038 | reference as written |

## `edges_citation` (268,563 rows)

vbpl citations (external, external_mention, parent_law, parent_law_mention) resolved to documents/articles.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `src_doc_id` | String | 268,563 | citing document |
| `src_article_id` | String | 133,431 | citing article when known |
| `dst_doc_id` | String | 268,563 | cited document |
| `dst_article_id` | String | 97,153 | cited article when given and present |
| `clause` | String | 56,649 | cited clause |
| `point` | String | 17,466 | cited point |
| `kind` | String | 268,563 | vbpl citation kind |
| `n_mentions` | UInt32 | 268,563 | records merged into this edge |
| `article_cited` | String | 98,120 | article number written (even if absent) |
| `source_location` | String | 268,563 | where in the citing document |
| `raw` | String | 268,563 | citation as written (<=200 chars) |
| `method` | String | 268,563 | docnum-key or law-name-year |

## `qas` (109,543 rows)

Legal Q&As from hdpl: metadata only (no question or answer text).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `qa_id` | String | 109,543 | hdpl id |
| `iri` | String | 109,543 | question IRI |
| `answer_iri` | String | 109,543 | answer IRI |
| `url` | String | 109,543 | source URL |
| `published_date` | String | 109,543 | publication date |
| `year` | Int64 | 109,543 | publication year |
| `category` | String | 109,482 | category slug |
| `area_id` | String | 109,482 | legal area |
| `has_ad` | Boolean | 109,543 | advertising flag of the source |
| `n_citation_records` | Int64 | 109,543 | citation records |
| `n_document_citations` | Int64 | 109,543 | document-level records |
| `n_provision_citations` | Int64 | 109,543 | provision-level records |
| `n_gold_articles` | UInt32 | 109,543 | articles linked (gold resolver) |
| `n_documents_resolved` | UInt32 | 109,543 | documents linked by number |

## `edges_qa_article` (34,869 rows)

Q&A answer -> article (+clause, point) from the gold resolver (gold_all.parquet).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `qa_id` | String | 34,869 | Q&A |
| `dst_doc_id` | String | 34,869 | document |
| `dst_article_id` | String | 34,869 | article |
| `clause` | String | 16,424 | clause |
| `point` | String | 3,221 | point |
| `ref` | String | 34,869 | reference as written |
| `method` | String | 34,869 | answer-text-number / answer-text-name / citation-field-name / unique-document-of-type |
| `method_detail` | String | 34,869 | gold method string |

## `edges_qa_document` (119,683 rows)

Q&A answer -> document cited by number.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `qa_id` | String | 119,683 | Q&A |
| `dst_doc_id` | String | 119,683 | document |
| `number_cited` | String | 119,683 | number as written |
| `law_type` | String | 119,683 | law type |
| `method` | String | 119,683 | docnum-key |

## `terms` (16,701 rows)

Legal terms from tnpl (names only, no definitions).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `term_id` | Int64 | 16,701 | tnpl id |
| `iri` | String | 16,701 | VLOnto IRI |
| `label_vi` | String | 16,701 | Vietnamese term |
| `label_en` | String | 16,599 | English label |
| `label_en_source` | String | 16,599 | mt or site |
| `translation_model` | String | 15,426 | MT model |
| `area_id` | String | 16,700 | area slug |
| `tnpl_area_id` | Int64 | 16,700 | tnpl area id |
| `status_vi` | String | 16,701 | status |
| `in_force` | Boolean | 16,701 | status as boolean |
| `url` | String | 16,701 | source URL |

## `edges_term_related` (17,615 rows)

Related terms.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `src_term_id` | Int64 | 17,615 | term |
| `dst_term_id` | Int64 | 17,615 | related term |
| `method` | String | 17,615 | source-metadata |

## `news` (681 rows)

Legal news articles from htpl (no title or text).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `news_id` | String | 681 | htpl id |
| `iri` | String | 681 | VLOnto IRI |
| `url` | String | 681 | source URL |
| `category` | String | 681 | category slug |
| `published_date` | String | 87 | date |
| `year` | Int64 | 87 | year |
| `n_numbers_found` | Int64 | 681 | document numbers found |
| `n_documents_resolved` | Int64 | 681 | documents linked |

## `edges_news_document` (1,484 rows)

News article -> mentioned document.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `news_id` | String | 1,484 | news |
| `dst_doc_id` | String | 1,484 | document |
| `number_found` | String | 1,484 | number |
| `method` | String | 1,484 | docnum-regex |

## `news_categories` (7 rows)

News categories.

| Column | Type | Non-null | Description |
|---|---|---|---|
| `category` | String | 7 |  |
| `iri` | String | 7 |  |
| `label_vi` | String | 7 |  |
| `label_en` | String | 7 |  |
| `n_articles` | Int64 | 7 |  |

## `sources` (4 rows)

Source datasets of this build with revision, licence and policy (release v1: the four thuvienphapluat.vn datasets).

| Column | Type | Non-null | Description |
|---|---|---|---|
| `dataset` | String | 4 |  |
| `iri` | String | 4 |  |
| `revision` | String | 4 |  |
| `licence` | String | 4 |  |
| `publisher` | String | 4 |  |
| `content` | String | 4 |  |
| `repository` | String | 4 |  |
| `card_sha256` | String | 4 |  |

## `article_text` (436,309 rows, local only)



| Column | Type | Non-null | Description |
|---|---|---|---|
| `article_id` | String | 436,309 |  |
| `text` | String | 436,309 |  |

