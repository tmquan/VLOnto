"""kg_report.md and checks.json from the JSON reports of the build, export, validation, ontology check and site steps.

Spot-check verdicts are read from docs/spot_check_review.json (written by a person after reading spot_checks.md); the
court edge types and court limitations (keys edge_types_courts, limitations_courts) are used only when court data is
included (release v1 has none).
"""
import json
import os

from . import config as C


def _rd(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def g(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def n(x):
    return f"{x:,}" if isinstance(x, int) else ("-" if x is None else str(x))


def pct(a, b):
    return f"{100.0 * a / b:.1f}%" if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b else "-"


NODE_TABLES = [("documents", "vlo:LegalDocument (10 subclasses)"), ("articles", "vlo:Article"), ("structure", "vlo:Part / Chapter / Section / Appendix"),
               ("provisions_ref", "vlo:Clause / vlo:Point"), ("issuers", "vlo:IssuingBody"), ("areas", "vlo:LegalArea (skos:Concept)"),
               ("changes", "vlo:LegalChange"), ("courts", "vlo:Court"), ("decisions", "vlo:Judgment / CourtRuling / CourtDecision"),
               ("precedents", "vlo:Precedent"), ("qas", "vlo:LegalQuestion + vlo:LegalAnswer"), ("terms", "vlo:LegalTerm"),
               ("news", "vlo:LegalNewsArticle"), ("news_categories", "vlo:NewsCategory"), ("sources", "vlo:SourceDataset")]
EDGE_TABLES = [("edges_change", "vlo:replaces / amends / repeals / partiallyRepeals / partiallyTerminates"),
               ("edges_legal_basis", "vlo:legalBasis"), ("edges_citation", "vlo:cites / vlo:citesParentLaw"),
               ("edges_decision_provision", "vlo:appliesProvision / vlo:appliesDocument"), ("edges_decision_case", "vlo:citesCase / vlo:appliesPrecedent"),
               ("edges_precedent_source", "vlo:selectedFrom"), ("edges_qa_article", "vlo:answerCitesProvision"),
               ("edges_qa_document", "vlo:answerCitesDocument"), ("edges_term_related", "vlo:relatedTerm"), ("edges_news_document", "vlo:mentionsDocument")]


def court_table(t):
    return t in C.COURT_TABLES


def node_tables():
    return [(t, c) for t, c in NODE_TABLES if C.INCLUDE_COURTS or not court_table(t)]


def edge_tables():
    return [(t, p) for t, p in EDGE_TABLES if C.INCLUDE_COURTS or not court_table(t)]


def review_edge_types(S):
    et = dict(S.get("edge_types", {}))
    if C.INCLUDE_COURTS:
        et.update(S.get("edge_types_courts", {}))
    return et


def review_limitations(S):
    return list(S.get("limitations", [])) + (list(S.get("limitations_courts", [])) if C.INCLUDE_COURTS else [])


def make_checks(B, V, E, O, S, M, R):
    ch = []

    def add(name, ok, evidence):
        ch.append({"name": name, "result": "pass" if ok is True else ("fail" if ok is False else "not run"), "evidence": evidence})

    comp = g(O, "completeness", "problems")
    add("Ontology completeness (en+vi labels, en definition, module for every VLOnto term)", (comp == []) if comp is not None else None,
        f"{len(comp) if comp is not None else '-'} problems; terms by kind {g(O, 'completeness', 'by_kind')}")
    add("Ontology has no dangling references", (g(O, "dangling") == []) if "dangling" in O else None, f"dangling={g(O, 'dangling')}")
    rel = g(O, "release")
    add(f"Ontology release metadata (owl:versionInfo {C.VERSION}, owl:versionIRI {C.ONTOLOGY_VERSION_IRI}, dcterms:modified = build date {C.BUILD_DATE})",
        g(rel, "pass") if rel else None,
        f"versionInfo {g(rel, 'versionInfo')}, versionIRI {g(rel, 'versionIRI')}, priorVersion {g(rel, 'priorVersion')}, modified {g(rel, 'modified')}; "
        f"dcterms:source {g(rel, 'n_sources')} datasets (match: {g(rel, 'sources_match')}); judiciary terms with a v2 scope note {g(rel, 'scope_notes')}/{g(rel, 'court_terms')}"
        if rel else "ontology_check.json has no release section")
    add("ELI terms used by VLOnto exist in the ELI ontology", (g(O, "eli", "missing_in_eli") == []) if g(O, "eli", "available") else None,
        f"{g(O, 'eli', 'eli_terms_defined')} ELI terms defined; missing {g(O, 'eli', 'missing_in_eli')}")
    add("OWL-RL on fixtures (expected inferences present, planted disjointness and functional clash detected)", g(O, "owlrl", "pass"),
        f"{g(O, 'owlrl', 'positive', 'expected_inferences')} expected inferences, missing {g(O, 'owlrl', 'positive', 'missing_inferences')}; "
        f"negative: {g(O, 'owlrl', 'negative', 'n_inconsistencies')} inconsistencies")
    add("SHACL on fixtures (positive conforms, all planted errors reported)", g(O, "shacl", "pass"),
        f"positive results {g(O, 'shacl', 'positive', 'n_results')}; planted found {g(O, 'shacl', 'negative', 'planted_errors_found')}, "
        f"missed {g(O, 'shacl', 'negative', 'planted_errors_missed')}")
    nb = g(O, "pylode", "n_broken_internal_links")
    add("pyLODE documentation renders with no broken internal links", (nb == 0) if nb is not None else None,
        f"{g(O, 'pylode', 'bytes')} bytes, {g(O, 'pylode', 'internal_links')} internal links, broken {nb}")
    ri = g(V, "referential_integrity")
    add("Referential integrity of every parquet edge and foreign key", g(ri, "pass"),
        f"{len(g(ri, 'checks', default={}))} checks, orphans {g(ri, 'total_orphans')}")
    rec = g(V, "reconciliation", default=[])
    mism = [r for r in rec if not r.get("match")]
    add("Reconciliation with the processed-corpus data report", (len(mism) == 0) if rec else None,
        f"{len(rec) - len(mism)}/{len(rec)} items match" + (f"; differences: {[(r['item'], r['expected'], r['kg']) for r in mism]}" if mism else ""))
    loaded, total = g(V, "oxigraph", "triples_loaded"), g(E, "triples_total")
    add("Full RDF dump parses strictly and loads into Oxigraph", (isinstance(loaded, int) and loaded > 0) if loaded is not None else None,
        f"{n(total)} N-Triples lines written, {n(loaded)} distinct triples loaded")
    rc = {k: v for k, v in g(V, "rdf_counts", default={}).items() if not k.startswith("_")}
    bad = [k for k, v in rc.items() if not v.get("match")]
    add("Per-class instance counts identical in parquet and RDF", (not bad) if rc else None,
        f"{len(rc) - len(bad)}/{len(rc)} classes match" + (f"; mismatches {bad}" if bad else ""))
    di = g(V, "dangling_iris")
    add("Every VLOnto instance IRI used as an object is typed in the dump", g(di, "pass"),
        f"{n(g(di, 'vlid_objects'))} object IRIs, {n(g(di, 'objects_without_type'))} untyped")
    sh = g(V, "shacl")
    add("SHACL on a stratified sample of the KG (up to 150 nodes per class or kind)", g(sh, "pass"),
        f"{n(g(sh, 'sample_nodes'))} nodes / {n(g(sh, 'sample_triples'))} triples; violations {g(sh, 'n_violations')}"
        + (f" {g(sh, 'violation_kinds')}" if g(sh, "n_violations") else "") + (f"; error {g(sh, 'error')}" if g(sh, "error") else ""))
    ow = g(V, "owlrl_sample")
    add("OWL-RL closure of the KG sample is consistent", g(ow, "pass"),
        f"{n(g(ow, 'input_triples'))} -> {n(g(ow, 'closure_triples'))} triples; inconsistencies {g(ow, 'n_inconsistencies')}, "
        f"sameAs between distinct nodes {g(ow, 'n_sameAs')}")
    rs = g(V, "release_scope")
    if not C.INCLUDE_COURTS:
        add(f"Release {C.RELEASE} scope: no court data (no court table, no court/decision/precedent node, no court-source statement); sources = the {len(C.SOURCES)} thuvienphapluat datasets",
            g(rs, "pass") if rs else None,
            (f"court tables present {g(rs, 'court_tables_present')}; typed court nodes in RDF {g(rs, 'court_typed_nodes_in_rdf')}; "
             f"dump lines mentioning court IRIs or court sources {g(rs, 'court_data_lines_in_dump')}; source datasets {g(rs, 'source_datasets')}")
            if rs else "validation.json has no release_scope section")
    sc_name = "Spot checks: 10 random edges per edge type read and judged (criterion: at least 8 correct per 10 for every edge type)"
    if S:
        et = review_edge_types(S)
        tot = sum(v.get("checked", 0) for v in et.values())
        cor = sum(v.get("correct", 0) for v in et.values())
        wrong = sum(v.get("wrong", 0) for v in et.values())
        low = [k for k, v in et.items() if v.get("checked") and v.get("correct", 0) < 0.8 * v["checked"]]
        add(sc_name, (not low) and tot > 0,
            f"{cor}/{tot} judged correct, {wrong} judged wrong, {tot - cor - wrong} not verifiable from the record; "
            f"edge types below the criterion: {low}")
    else:
        add(sc_name, None, "review file missing")
    if M:
        files = M.get("files", [])
        big = [f["file"] for f in files if not f.get("within_20MB")]
        js = [f for f in files if f["file"].startswith("js/")]
        add("Site bundles within 20 MB, each with a file:// .js twin", (not big) if files else None,
            f"{len(files)} files, {len(js)} js twins, over 20 MB: {big}")
    N = _rd(os.path.join(R, "nfc_check.json"))
    if N:
        kinds = {}
        for k in N.get("files", {}):
            grp = k.split("/")[0]
            kinds[grp] = kinds.get(grp, 0) + 1
        add("0 non-NFC strings in every published output (Unicode NFC)", N.get("pass"),
            f"{N.get('total_non_nfc')} non-NFC strings in {N.get('n_files')} files {kinds}"
            + (f"; files with non-NFC strings: {N.get('files_with_non_nfc')}" if N.get("files_with_non_nfc") else "")
            + "; kg_report.md and checks.json are written in NFC by the report step")
    else:
        add("0 non-NFC strings in every published output (Unicode NFC)", None, "nfc_check.json missing")
    L = _rd(os.path.join(R, "link_check.json"))
    name = "No link to a VLOnto Hugging Face dataset or Space in any published output (release = GitHub repository + website)"
    if L:
        t = L.get("totals", {})
        add(name, L.get("pass_links", L.get("pass")),
            f"{n(L.get('n_files'))} files scanned; forbidden hits: links to a Hugging Face VLOnto dataset {t.get('hf_vlonto_dataset')}, "
            f"links to a Space {t.get('hf_space')}, Space path segments {t.get('spaces_path')}, "
            f"wording that calls a VLOnto document a card {t.get('dataset_card_wording')}"
            + (f" in {L.get('files_with_forbidden_links', L.get('files_with_forbidden'))}"
               if L.get("files_with_forbidden_links", L.get("files_with_forbidden")) else "")
            + f"; kept: {n(t.get('source_dataset_links'))} links to the tmquan source datasets on Hugging Face ({len(C.SOURCES)} sources of this build"
            + (f", {len(C.DEFERRED_SOURCES)} planned for v2" if C.DEFERRED_SOURCES else "") + f"), {n(t.get('github_repo_links'))} to the GitHub "
            f"repository, {n(t.get('paper_links'))} to the paper (arXiv:2611.11426)")
    else:
        add(name, None, "link_check.json missing")
    name = "No absolute build-machine path or host name in any published output (paths relative to the VLOnto root)"
    if L and "pass_paths" in L:
        t = L.get("totals", {})
        bad = L.get("files_with_forbidden_paths")
        add(name, L.get("pass_paths"),
            f"{n(L.get('n_files'))} files scanned; build-node home paths {t.get('node_home_path')}, build-node host names "
            f"{t.get('node_host_name', 'not checked (VLONTO_PRIVATE_HOSTS unset)')}, macOS home paths {t.get('mac_home_path')}" + (f" in {bad}" if bad else ""))
    else:
        add(name, None, "link_check.json missing or without path patterns")
    return ch


def build_report(out_md=None):
    rp = C.REPORTS
    B, V, E = _rd(f"{rp}/build_report.json"), _rd(f"{rp}/validation.json"), _rd(f"{rp}/export_report.json")
    Co, O = _rd(f"{rp}/core_report.json"), _rd(f"{rp}/ontology_check.json")
    S = _rd(os.path.join(C.REPO, "docs", "spot_check_review.json"))
    M = _rd(os.path.join(C.SITE, "manifest.json"))
    checks = make_checks(B, V, E, O, S, M, rp)
    files = g(B, "files", default={})
    L = []
    w = L.append
    w("# VLOnto knowledge graph: build and validation report")
    w("")
    w(f"Version {C.VERSION} (release {C.RELEASE}) · build date {C.BUILD_DATE} · validity as of {C.VALIDITY_AS_OF} · ontology "
      f"<https://tmquan.github.io/VLOnto/ontology> ({g(O, 'parse', 'version')}). Not an official legal source and not legal advice.")
    w("")
    if not C.INCLUDE_COURTS:
        w(f"Release {C.RELEASE} is built from the {len(C.SOURCES)} thuvienphapluat.vn datasets ("
          + ", ".join(f"`{k}`" for k in C.SOURCES) + "). The court datasets (" + ", ".join(f"`{k}`" for k in C.DEFERRED_SOURCES)
          + ") are planned for v2: the ontology keeps its judiciary classes and properties (marked with a v2 scope note), "
          "but this build has no court, decision or precedent data (switch `VLONTO_INCLUDE_COURTS`, default 0).")
        w("")
    w("## 1. Summary")
    w("")
    w(f"- {n(g(B, 'documents'))} legal documents, {n(g(B, 'articles_total'))} articles ({n(g(B, 'articles_main'))} main-body, "
      f"{n(g(B, 'articles_appendix'))} in appendices), {n(sum(g(B, 'structure_nodes', default={}).values()))} parts/chapters/sections/appendices, "
      f"{n(sum(g(B, 'provisions_ref', default={}).values()))} clause/point nodes.")
    w(f"- {n(g(B, 'changes'))} legal-change events, {n(g(files, 'edges_legal_basis', 'rows'))} legal-basis links, "
      f"{n(g(files, 'edges_citation', 'rows'))} citation links between documents/articles.")
    if C.INCLUDE_COURTS:
        w(f"- {n(g(B, 'decisions'))} court decisions, {n(g(files, 'courts', 'rows'))} canonical courts, {n(g(B, 'precedents'))} precedents, "
          f"{n(g(files, 'edges_decision_provision', 'rows'))} applied-provision links, {n(g(files, 'edges_decision_case', 'rows'))} case links.")
    else:
        w("- No court decisions, courts or precedents: court data is planned for v2.")
    w(f"- {n(g(files, 'qas', 'rows'))} legal Q&As (metadata only) with {n(g(files, 'edges_qa_article', 'rows'))} article links and "
      f"{n(g(files, 'edges_qa_document', 'rows'))} document links; {n(g(files, 'terms', 'rows'))} legal terms; {n(g(files, 'news', 'rows'))} news items.")
    w(f"- RDF: {n(g(E, 'triples_total'))} N-Triples lines ({n(g(V, 'oxigraph', 'triples_loaded'))} distinct triples in Oxigraph), "
      f"{n(g(E, 'nt_gz_bytes'))} bytes gzip; browser subset `vlonto-core.ttl` {n(g(Co, 'triples'))} triples, {n(g(Co, 'bytes'))} bytes.")
    npass = sum(1 for c in checks if c["result"] == "pass")
    w(f"- Checks: {npass} of {len(checks)} passed" + "".join(f"; **{c['result']}**: {c['name']}" for c in checks if c["result"] != "pass") + ".")
    w("")
    w("## 2. Sources and what is republished")
    w("")
    w("| dataset | revision | licence | republished in the KG | kept out |")
    w("|---|---|---|---|---|")
    keep = {"thuvienphapluat-vn-vbpl": ("documents metadata, titles, article numbers and headings (≤200 chars), structure, validity, links, evidence quotes ≤300 chars", "article and document bodies (local-only table)"),
            "thuvienphapluat-vn-hdpl": ("ids, URLs, dates, categories, derived links", "questions, answers, titles, authors, keywords"),
            "thuvienphapluat-vn-tnpl": ("term names (vi, en with provenance), area, status, related links", "definitions, editor names"),
            "thuvienphapluat-vn-htpl": ("ids, URLs, dates, categories, document mentions", "titles, summaries, bodies"),
            "anle-toaan-gov-vn": ("decision metadata, court names, links, sentence-id pointers", "judgment text, person names"),
            "cbba-toaan-gov-vn": ("decision metadata, canonical court names, links, sentence-id pointers", "judgment text, person names")}
    for ds, info in C.SOURCES.items():
        k = keep.get(ds, ("", ""))
        w(f"| tmquan/{ds} | `{info.get('revision', '')[:12]}` | {info.get('licence', '')} | {k[0]} | {k[1]} |")
    w("")
    if C.DEFERRED_SOURCES:
        w("Planned for v2 (not read by this build): " + ", ".join(f"tmquan/{ds} (`{info['revision'][:12]}`, {info['licence']})"
                                                               for ds, info in C.DEFERRED_SOURCES.items()) + ".")
        w("")
    w("Details and attribution: `docs/licence_policy.md`.")
    w("")
    w("## 3. Built objects")
    w("")
    w("| node table | rows | RDF class |")
    w("|---|---:|---|")
    for t, cls in node_tables():
        w(f"| {t} | {n(g(files, t, 'rows'))} | {cls} |")
    w("")
    w("| edge table | rows | RDF property |")
    w("|---|---:|---|")
    for t, p in edge_tables():
        w(f"| {t} | {n(g(files, t, 'rows'))} | {p} |")
    w("")
    w("RDF parts (triples per table):")
    w("")
    w("| part | triples |")
    w("|---|---:|")
    for k, v in g(E, "parts", default={}).items():
        w(f"| {k} | {n(v)} |")
    w("")
    w("## 4. Resolution rates")
    w("")
    cit = g(B, "citations", default={})
    w("### 4.1 vbpl citations (document → document/article)")
    w("")
    w("| kind | records | resolved to document | rate | resolved to article |")
    w("|---|---:|---:|---:|---:|")
    for k, raw in g(cit, "raw_records_by_kind", default={}).items():
        rd_ = g(cit, "resolved_to_document_by_kind", k, default=0)
        w(f"| {k} | {n(raw)} | {n(rd_)} | {pct(rd_, raw)} | {n(g(cit, 'resolved_to_article_by_kind', k, default=0))} |")
    w("")
    ur = g(cit, "unresolved_reasons", default={})
    w("Unresolved reasons: " + ", ".join(f"{k} {n(v)}" for k, v in sorted(ur.items(), key=lambda x: -x[1])[:12]) + ".")
    w(f" Self-citations ({n(g(B, 'citation_records_by_kind', 'self'))}) and anaphora ({n(g(B, 'citation_records_by_kind', 'anaphora'))}) are within-document and not turned into links.")
    w("")
    lb = g(B, "legal_basis", default={})
    w("### 4.2 Legal basis")
    w("")
    w(f"Source `parent_acts`: {n(g(lb, 'parent_acts', 'raw'))} references, {n(g(lb, 'parent_acts', 'resolved'))} resolved. "
      f"Preamble citations: {n(g(lb, 'preamble', 'preamble_citation_edges'))} candidate edges, {n(g(lb, 'preamble', 'kept'))} kept, "
      f"{n(g(lb, 'preamble', 'dropped_issued_later'))} dropped because the basis was issued after the citing document, "
      f"{n(g(lb, 'preamble', 'dropped_lower_rank'))} dropped because the basis has lower legal force. "
      f"Constitution (no number, so no citation record): {n(g(lb, 'constitution', 'preamble_mentions'))} preambles say 'Căn cứ Hiến pháp', "
      f"linked as {({k: v for k, v in (g(lb, 'constitution', default={}) or {}).items() if k != 'preamble_mentions'})}. "
      f"Result: {n(g(lb, 'edges'))} edges ({g(lb, 'edges_by_method')}), {n(g(lb, 'edges_found_by_both_methods'))} found by more than one method.")
    w("")
    w("### 4.3 Legal changes and validity")
    w("")
    w(f"Document issue dates: {g(B, 'documents_issue_date_check')} (a date more than one year away from the year in the document number is "
      f"set to null and kept in `issue_date_source`).")
    w("")
    w(f"{n(g(B, 'relations_rows'))} relations of the validity pipeline (rules v7) → {n(g(B, 'changes'))} change events; unresolved "
      f"{n(g(B, 'relations_unresolved_rows'))}; evidence quotes cut to 300 characters for {n(g(B, 'changes_evidence_truncated'))} events. "
      f"Validity of documents: {g(B, 'documents_by_validity')}.")
    w("")
    w("### 4.4 Court decisions")
    w("")
    if not C.INCLUDE_COURTS:
        w(f"Not part of release {C.RELEASE}: the court datasets (" + ", ".join(f"`{k}`" for k in C.DEFERRED_SOURCES)
          + ") are planned for v2. The build code for them is kept (`vlonto/build_courts.py`, run with `VLONTO_INCLUDE_COURTS=1`).")
        w("")
    tot = g(B, "court_pass1", "totals", default={})
    if C.INCLUDE_COURTS:
        w(f"Law citations in decisions: {n(g(tot, 'law_raw'))} records, {n(g(tot, 'law_resolved_doc'))} resolved to a document "
          f"({pct(g(tot, 'law_resolved_doc'), g(tot, 'law_raw'))}), {n(g(tot, 'law_resolved_article'))} to an article; "
          f"{n(g(tot, 'law_precedent'))} cite a precedent. Main unresolved reasons: "
          + ", ".join(f"{k.split(':', 1)[1]} {n(v)}" for k, v in sorted(((k, v) for k, v in tot.items() if k.startswith("law_unresolved:")), key=lambda x: -x[1])[:6]) + ".")
        cc = g(B, "case_citations", default={})
        w(f"Case citations: {n(g(cc, 'records'))} records → {n(g(cc, 'edges_decision_to_decision'))} decision→decision edges "
          f"(by date {n(g(cc, 'resolved:case-number-date'))}, by court {n(g(cc, 'resolved:case-number-court'))}) and "
          f"{n(g(cc, 'edges_decision_to_precedent'))} decision→precedent edges; {n(g(cc, 'no_candidate_in_corpus'))} cite a decision that is not in the corpus, "
          f"{n(g(cc, 'ambiguous_same_date'))} + {n(g(cc, 'ambiguous_same_court'))} were ambiguous and dropped, {n(g(cc, 'no_date_or_court_match'))} had no matching date or court.")
        cn = g(B, "courts_canonical", default={})
        w(f"Courts: {n(g(cn, 'courts'))} canonical courts by kind {g(cn, 'by_kind')}; {n(g(cn, 'decisions_linked'))} of {n(g(B, 'decisions'))} decisions "
          f"linked to a court ({pct(g(cn, 'decisions_linked'), g(B, 'decisions'))}); {n(g(cn, 'decisions_province_from_name'))} took the province "
          f"from the same name elsewhere; decisions without court: {g(cn, 'decisions_by_court_note')}.")
        w(f"Decision dates: {g(B, 'decisions_issued_date_check')} (dates outside 1945..build date, more than one year from the year in the "
          f"decision number, or earlier than the year of a cited law or decision are set to null). {n(g(tot, 'decision_number:legislative_dropped'))} source "
          f"records carried the number of a cited law (for example the court-fee resolution 326/2016/UBTVQH14) as their own number; number, "
          f"symbol and date of those records were dropped.")
        w(f"Case links removed by consistency rules: date-only match where a court is unknown {n(g(cc, 'dropped:date_match_court_unknown'))}, "
          f"date-only match to a court in another (or an unknown) province {n(g(cc, 'dropped:date_match_other_province'))}, "
          f"date-only match outside the citing High Court's region {n(g(cc, 'dropped:date_match_outside_high_court_region'))}, "
          f"first-instance judgment from another province {n(g(cc, 'dropped:first_instance_other_province'))}, "
          f"first-instance judgment at an impossible court level {n(g(cc, 'dropped:first_instance_wrong_level'))}, "
          f"first-instance judgment of the appellate court itself {n(g(cc, 'dropped:first_instance_same_court'))}.")
        w("")
    qa = g(B, "qa", default={})
    w("### 4.5 Q&A, terminology, news")
    w("")
    w(f"Q&A: {n(g(qa, 'document_citations', 'document_citation_records'))} document citation records, {n(g(qa, 'document_citations', 'resolved'))} resolved "
      f"({pct(g(qa, 'document_citations', 'resolved'), g(qa, 'document_citations', 'document_citation_records'))}); article links from the evaluation gold "
      f"resolver {n(g(qa, 'qa_article_edges'))} for {n(g(qa, 'qas_with_article_edge'))} Q&As, by method {g(qa, 'qa_article_edges_by_method')}.")
    tm = g(B, "terms", default={})
    w(f"Terms: {n(g(tm, 'terms'))} terms, {n(g(tm, 'related_edges_directed'))} related links ({n(g(tm, 'related_ids_not_in_terms'))} related ids not in the term table); "
      f"English names by source {g(tm, 'label_en_source')}.")
    nw = g(B, "news", default={})
    w(f"News: {n(g(nw, 'mentions'))} document-number mentions, {n(g(nw, 'resolved'))} resolved; {n(g(nw, 'published_date_parsed'))} of {n(g(nw, 'articles'))} items carry a date in the source.")
    w("")
    w("## 5. Checks")
    w("")
    w("| check | result | evidence |")
    w("|---|---|---|")
    for c in checks:
        w(f"| {c['name']} | {c['result']} | {str(c['evidence']).replace('|', '/')} |")
    w("")
    rec = g(V, "reconciliation", default=[])
    if rec:
        w("Reconciliation with the data report of the processed corpus:")
        w("")
        w("| item | data report | KG | match | note |")
        w("|---|---:|---:|---|---|")
        for r in rec:
            w(f"| {r['item']} | {n(r['expected'])} | {n(r['kg'])} | {'yes' if r['match'] else 'no'} | {r.get('note', '')} |")
        w("")
    w("## 6. Spot checks")
    w("")
    if S:
        w(S.get("method", ""))
        w("")
        if C.INCLUDE_COURTS and S.get("method_courts"):
            w(S["method_courts"])
            w("")
        if not C.INCLUDE_COURTS and S.get("release_note"):
            w(S["release_note"])
            w("")
        w("| edge type | checked | correct | wrong | not verifiable | notes |")
        w("|---|---:|---:|---:|---:|---|")
        for k, v in review_edge_types(S).items():
            unv = v.get("checked", 0) - v.get("correct", 0) - v.get("wrong", 0)
            w(f"| {k} | {v.get('checked')} | {v.get('correct')} | {v.get('wrong', 0)} | {unv} | {v.get('notes', '')} |")
    else:
        w("Review file missing.")
    w("")
    w("## 7. Limitations")
    w("")
    for x in review_limitations(S) if S else []:
        w(f"- {x}")
    w("")
    w("## 8. Reproduce")
    w("")
    w("```bash")
    w("export R=<processed vn-legal corpus root> V=<VLOnto root> NPROC=8")
    w("cd $V/repo/vlonto && python -m vlonto.cli all     # build, nfc, export, core, validate, site, check-ontology, nfc-check, link-check, report")
    w("python -m vlonto.cli check-ontology                # ontology checks, pyLODE HTML, JSON-LD context")
    w("python -m vlonto.cli report                        # this report")
    w("# court data (planned for v2): VLONTO_INCLUDE_COURTS=1 python -m vlonto.cli all   (or: python -m vlonto.cli all --with-courts)")
    w("```")
    md = "\n".join(L) + "\n"
    out_md = out_md or os.path.join(rp, "kg_report.md")
    from .nfc import nfc, nfc_obj
    md, checks = nfc(md), nfc_obj(checks)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(rp, "checks.json"), "w", encoding="utf-8") as f:
        json.dump(checks, f, ensure_ascii=False, indent=1)
    return {"path": out_md, "bytes": len(md.encode("utf-8")), "checks": {c["name"]: c["result"] for c in checks}}
