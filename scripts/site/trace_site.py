#!/usr/bin/env python3
"""trace_site.py - the data of traces.html: build/traces/*.json (question traces) -> site/data/traces/*.js (stdlib only).

    python scripts/site/trace_site.py --traces $V/build/traces --site site [--report out.json]
    (build_site.py runs the same step; with no build/traces/index.json it writes the "no trace data" index)

Input: index.json and one <area id>.json per legal area, as written by scripts/traces/ (schema in its README). Output:
site/data/traces/index.js and one <area id>.js per area, made with tools/json2js.py (window.VLONTO["traces_index"] and
window.VLONTO["traces_<area id>"]; the page loads an area's file when one of its questions is first chosen). Each area
file holds, per trace, what the page shows plus the build-time 2D drawing (scripts/site/trace_layout.py; the page's
fallback without WebGL). site/data/traces/graph.js (window.VLONTO["traces_graph"], loaded first) places all traces in
the 3D legal network (scripts/site/trace_global.py, which reads site/data/legal_network.js): every law is its network
document; the provisions hang under their laws, the questions, answers, terms and other answers lie on planes under
the lowest document layer; every node once with id, class, position and, for the law side, terms and areas, its labels
and source link; the edges by kind; per trace its node, foreground and edge lists and its call-out nodes.
site/data/traces/questions.js (window.VLONTO["traces_questions"], loaded with the graph) is the page's one list of all
traced questions, area by area: per question its rank, title, English gloss, the law's names and number, verified and
match - fields the area files already hold, so the list and its search need no area file.
    python scripts/site/trace_site.py --questions-from-site --site site
rebuilds questions.js (and its entry in index.js) from the area files in site/data/traces, for a build without
build/traces.

Published (licence policy, docs/licence_policy.md): question titles as published on thuvienphapluat.vn and their
machine-assisted English glosses for the traced questions, law and provision labels, term names, dates, record ids,
links to the sources, structure paths, match scores and methods. Dropped from the trace JSON on the way: citations as
written in the answers (paths[].refs, unresolved_citations[].ref / law_name: fragments of answer text), the titles of
the other answers (no English gloss; shown as "Câu hỏi #id · Question #id"), and the free text that the vbpl status
field carries after the status itself (reduced to the status and its date, with an English rendering). No answer text,
article / clause / point text, glossary definitions or person names are in the input or the output.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import trace_layout as TL  # noqa: E402
import trace_global as TGL  # noqa: E402

CLASSES = TL.CLASSES
NO_DATA_REASON = "no build/traces/index.json in this build"


def json2js_module():
    spec = importlib.util.spec_from_file_location("json2js", HERE.parent.parent / "tools" / "json2js.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def nfc(o):
    if isinstance(o, str):
        return unicodedata.normalize("NFC", o)
    if isinstance(o, list):
        return [nfc(x) for x in o]
    if isinstance(o, dict):
        return {nfc(k): nfc(v) for k, v in o.items()}
    return o


STATUS = [
    (re.compile(r"^Còn hiệu lực đến:?\s*(\d{2}/\d{2}/\d{4})"), "Còn hiệu lực đến {d}", "in force until {d}"),
    (re.compile(r"^Hết hiệu lực:?\s*(\d{2}/\d{2}/\d{4})"), "Hết hiệu lực: {d}", "no longer in force: {d}"),
    (re.compile(r"^Còn hiệu lực"), "Còn hiệu lực", "in force"),
    (re.compile(r"^Hết hiệu lực"), "Hết hiệu lực", "no longer in force"),
    (re.compile(r"^Chưa có hiệu lực"), "Chưa có hiệu lực", "not yet in force"),
    (re.compile(r"^Không còn phù hợp"), "Không còn phù hợp", "no longer applicable"),
]


def canon_status(raw):
    """the status of the vbpl record, without the text the source field sometimes carries after it"""
    s = unicodedata.normalize("NFC", (raw or "").strip())
    for rx, vi, en in STATUS:
        m = rx.match(s)
        if m:
            d = m.group(1) if m.groups() else ""
            return vi.format(d=d), en.format(d=d)
    return "không rõ", "unknown"


def compact_trace(tr: dict, area_id: str, font) -> tuple[dict, dict]:
    nodes = tr["nodes"]
    idx = {n["id"]: k for k, n in enumerate(nodes)}
    out_nodes = []
    for n in nodes:
        c = n["cls"]
        pv = n.get("provenance") or {}
        status = pv.get("status")
        if c in ("work", "record"):
            vi, en = canon_status(None if status == "no status in source" else status)
            status = f"{vi} · {en}"
        vi_l, en_l = n["label_vi"], n["label_en"]
        if c == "other_question":                     # titles of other answers are not published (no English gloss)
            num = n["id"].split(":", 1)[1]
            vi_l, en_l = f"Câu hỏi #{num}", f"Question #{num}"
        e = {"i": n["id"], "c": CLASSES.index(c), "vi": vi_l, "en": en_l,
             "p": [pv.get("dataset") or "", str(pv.get("record") or ""), pv.get("method") or "", status or ""]}
        if n.get("url"):
            e["u"] = n["url"]
        if n.get("on_trace"):
            e["t"] = 1
        if n.get("verified"):
            e["v"] = 1
        out_nodes.append(e)
    paths = []
    for p in tr["paths"]:
        e = {"n": [idx[i] for i in p["nodes"]], "v": bool(p["verified"]), "m": p.get("match"), "u": p.get("unit"),
             "me": p.get("method") or ""}
        if p.get("primary"):
            e["pr"] = True
        paths.append(e)
    law = tr["law"]
    s_vi, s_en = canon_status(law.get("status"))
    unresolved = []
    for u in tr.get("unresolved_citations") or []:
        e = {"k": u.get("kind") or "", "r": u.get("reason") or ""}
        for src, dst in (("law_type", "t"), ("number", "num"), ("article", "art")):
            if u.get(src):
                e[dst] = str(u[src])
        unresolved.append(e)
    geo, meta = TL.TraceGeometry(tr, area_id, font).export()
    ca = tr.get("callouts") or {}
    out = {
        "rank": tr["rank"], "verified": bool(tr["verified"]), "match": tr.get("match"),
        "article": {"vi": tr["article"]["label_vi"], "en": tr["article"]["label_en"], "k": idx[tr["article"]["node"]],
                    "n": tr["article"]["n_answers"], "na": tr["article"]["n_answers_all"]},
        "qa": {"id": tr["qa"]["id"], "url": tr["qa"]["url"], "date": tr["qa"]["published_date"],
               "vi": tr["qa"]["title_vi"], "en": tr["qa"]["title_en"]},
        "law": {"doc_id": law["doc_id"], "number": law["number"], "vi": law["label_vi"], "en": law["label_en"],
                "type_vi": law["type_vi"], "type_en": law["type_en"], "year": law.get("year"), "url": law.get("url") or "",
                "status_vi": s_vi, "status_en": s_en, "en_src": law.get("name_en_source") or ""},
        "nodes": out_nodes, "paths": paths,
        "terms": [{"n": idx[t["node"]], "d": idx.get(t.get("defined_by")) if t.get("defined_by") else None,
                   "m": t.get("definition_match")} for t in tr.get("terms") or []],
        "callouts": {"p": idx.get(ca.get("provision")), "t": idx.get(ca.get("term")) if ca.get("term") else None},
        "unresolved": unresolved, "counts": tr.get("counts") or {}, "g": geo,
    }
    return nfc(out), meta


FORBIDDEN_KEYS = {"answer", "answer_text", "text", "content", "definition", "definitions", "body", "refs", "ref",
                  "law_name", "heading", "headings", "name_vi_full"}


def licence_scan(obj, where="") -> list:
    """keys that would carry source text must not reach the site; other-answer labels must be bare ids"""
    bad = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                bad.append(f"{where}.{k}")
            bad += licence_scan(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad += licence_scan(v, f"{where}[{i}]")
    return bad


def check_area(src: dict, area_id: str) -> list:
    """schema and consistency checks of one input area file"""
    p = []
    if src.get("area", {}).get("id") != area_id:
        p.append("area id differs from the file name")
    for t in src.get("traces", []):
        ids = {n["id"] for n in t["nodes"]}
        if len(ids) != len(t["nodes"]):
            p.append(f"#{t['rank']}: duplicate node ids")
        for ln in t["links"]:
            if ln["s"] not in ids or ln["t"] not in ids:
                p.append(f"#{t['rank']}: dangling link {ln['s']} -> {ln['t']}")
        prim = [x for x in t["paths"] if x.get("primary")]
        if len(prim) != 1:
            p.append(f"#{t['rank']}: {len(prim)} primary paths")
        for x in t["paths"]:
            if any(i not in ids for i in x["nodes"]):
                p.append(f"#{t['rank']}: path through a missing node")
        for n in t["nodes"]:
            if n["cls"] not in CLASSES:
                p.append(f"#{t['rank']}: unknown class {n['cls']}")
    return p


def arms_stats(acc: dict, arms: list, tr: dict):
    """card shape: a V or W has traced strokes on both sides of the vertex, a single arm on one side only"""
    sides = {sd for _, sd in arms}
    dark = {sd for st, sd in arms if st == 1}
    acc["v_w" if len(sides) > 1 else "single"] += 1
    acc["dark_v_w" if len(dark) > 1 else "dark_single"] += 1
    defined = {ln["t"] for ln in tr["links"] if ln["kind"] == "defines"}
    acc["with_term_arm"] += any(t["node"] in defined for t in tr.get("terms") or [])
    acc["strokes"][str(len(arms))] = acc["strokes"].get(str(len(arms)), 0) + 1


QUESTION_FIELDS = ["rank", "vi", "en", "law_vi", "law_en", "law_number", "verified", "match"]


def questions_payload(area_ids: list, traces_by_area: dict) -> dict:
    """the side list of traces.html (data/traces/questions.js): every traced question, area by area in the index's order,
    as [rank, title, English gloss, law name vi, law name en, law number, verified 0/1, match] (QUESTION_FIELDS)"""
    out = []
    for aid in area_ids:
        rows = []
        for t in sorted(traces_by_area[aid], key=lambda t: t["rank"]):
            qa, law = t.get("qa") or {}, t.get("law") or {}
            rows.append([t["rank"], qa.get("vi") or "", qa.get("en") or "", law.get("vi") or "", law.get("en") or "",
                         law.get("number") or "", 1 if t.get("verified") else 0, t.get("match")])
        out.append({"id": aid, "q": rows})
    return nfc({"v": 1, "fields": QUESTION_FIELDS, "areas": out})


def write_js(j2j, value, name: str, out: Path, tmp: Path, src_name: str) -> int:
    src = tmp / src_name
    src.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _, size = j2j.convert(src, out, name, "VLONTO", False, False, 20.0)
    # in-process check (json2js --verify needs node): the file decodes to the same value
    m = re.search(r'= JSON\.parse\((".*")\);\n$', out.read_text(encoding="utf-8"), re.S)
    if not m or json.loads(json.loads(m.group(1))) != value:
        raise SystemExit(f"{out}: does not decode to its JSON")
    return size


def build(traces: Path | None, site: Path) -> dict:
    """writes site/data/traces/; returns a report"""
    out = site / "data" / "traces"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.js"):
        f.unlink()
    j2j = json2js_module()
    rep = {"available": False, "files": []}
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        if traces is None or not (traces / "index.json").exists():
            index = {"v": 1, "available": False, "reason": NO_DATA_REASON}
            write_js(j2j, index, "traces_index", out / "index.js", tmp, "index.json")
            rep["reason"] = NO_DATA_REASON
            return rep
        src_index = json.loads((traces / "index.json").read_text(encoding="utf-8"))
        font = TL.Font()
        areas, problems = [], []
        layout = {"traces": 0, "callouts_dropped": 0, "ink_hits": 0, "crossings": 0, "leaders_over_trace": 0,
                  "card_callouts": 0, "card_callouts_at_edge": 0, "variants": {},
                  "arms": {"single": 0, "v_w": 0, "dark_single": 0, "dark_v_w": 0, "with_term_arm": 0, "strokes": {}}}
        srcs, compact = {}, {}
        for a in src_index["areas"]:
            raw = (traces / a["file"]).read_bytes()
            src = json.loads(raw.decode("utf-8"))
            srcs[a["id"]] = src
            problems += [f"{a['id']}: {x}" for x in check_area(src, a["id"])]
            traces_out = []
            for tr in src["traces"]:
                c, meta = compact_trace(tr, a["id"], font)
                traces_out.append(c)
                layout["traces"] += 1
                layout["callouts_dropped"] += meta["dropped"]
                layout["crossings"] += meta["crossings"]
                layout["leaders_over_trace"] += meta["over"]
                cv = c["g"]["views"]["card"]
                for co in cv["c"]:
                    b = co["b"]
                    layout["card_callouts"] += 1
                    layout["card_callouts_at_edge"] += b[0] <= TL.CARD["m"] + 0.6 or b[0] + b[2] >= cv["w"] - TL.CARD["m"] - 0.6
                layout["variants"][str(meta["variant"])] = layout["variants"].get(str(meta["variant"]), 0) + 1
                layout["ink_hits"] += meta["ink"] + sum(1 for v in ("wide", "tall") for co in c["g"]["views"][v]["c"]
                                                        if co.pop("ink", False))
                arms_stats(layout["arms"], meta["arms"], tr)
            compact[a["id"]] = traces_out
            payload = {"v": 1, "area": nfc(src["area"]), "traces": traces_out}
            bad = licence_scan(payload)
            if bad:
                raise SystemExit(f"{a['id']}: keys that may carry source text: {bad[:5]}")
            size = write_js(j2j, payload, f"traces_{a['id']}", out / f"{a['id']}.js", tmp, a["file"])
            areas.append({k: a[k] for k in ("id", "label_vi", "label_en", "n_qas", "n_qas_with_links", "n_traces")} |
                         {"file": f"{a['id']}.js", "bytes": size, "verified": sum(1 for t in traces_out if t["verified"]),
                          "source_sha256": hashlib.sha256(raw).hexdigest()})
            rep["files"].append({"file": f"data/traces/{a['id']}.js", "bytes": size})
        if problems:
            raise SystemExit("trace data problems: " + "; ".join(problems[:10]))
        # all traces inside the 3D legal network (scripts/site/trace_global.py): every node once, every law its document
        graph, gstats = TGL.build_graph([a["id"] for a in src_index["areas"]], srcs, read_network(site))
        graph = nfc(graph)
        bad = licence_scan(graph)
        if bad:
            raise SystemExit(f"graph: keys that may carry source text: {bad[:5]}")
        gsize = write_js(j2j, graph, "traces_graph", out / "graph.js", tmp, "graph.json")
        rep["files"].append({"file": "data/traces/graph.js", "bytes": gsize})
        rep["graph"] = gstats | {"bytes": gsize}
        questions = questions_payload([a["id"] for a in src_index["areas"]], compact)
        bad = licence_scan(questions)
        if bad:
            raise SystemExit(f"questions: keys that may carry source text: {bad[:5]}")
        qsize = write_js(j2j, questions, "traces_questions", out / "questions.js", tmp, "questions.json")
        rep["files"].append({"file": "data/traces/questions.js", "bytes": qsize})
        index = {"v": 1, "available": True, "version": src_index.get("version"), "generated": src_index.get("generated"),
                 "source_revisions": src_index.get("source_revisions"), "method": src_index.get("method"),
                 "classes": src_index.get("classes"), "totals": src_index.get("totals"), "areas": areas,
                 "index_sha256": hashlib.sha256((traces / "index.json").read_bytes()).hexdigest(),
                 "graph": {"file": "graph.js", "bytes": gsize, "nodes": gstats["nodes"], "links": gstats["links"]},
                 "questions": {"file": "questions.js", "bytes": qsize, "count": sum(len(a["q"]) for a in questions["areas"])}}
        size = write_js(j2j, nfc(index), "traces_index", out / "index.js", tmp, "index.json")
        rep["files"].insert(0, {"file": "data/traces/index.js", "bytes": size})
        rep.update({"available": True, "areas": len(areas), "traces": layout["traces"], "layout": layout,
                    "largest_bytes": max(f["bytes"] for f in rep["files"]), "seconds": round(time.time() - t0, 1)})
    return rep


def read_network(site: Path) -> dict:
    """the legal network the traces live in: site/data/legal_network.js (the KG track's twin, which build_site.py copies
    before it builds the traces), as a json2js file or as the twin's object literal"""
    p = site / "data" / "legal_network.js"
    if not p.exists():
        raise SystemExit(f"{p} missing: the traces are placed in the legal network (build_site.py copies it first)")
    t = p.read_text(encoding="utf-8")
    m = re.search(r'= JSON\.parse\((".*")\);?\s*$', t, re.S)
    if m:
        return json.loads(json.loads(m.group(1)))
    m = re.search(r'window\.VLONTO\["legal_network"\]\s*=\s*', t)
    if not m:
        raise SystemExit(f"{p}: no window.VLONTO[\"legal_network\"]")
    return json.loads(t[m.end():].rstrip().rstrip(";"))


def read_js(path: Path):
    """the value of a json2js file (window.VLONTO[name] = JSON.parse("..."))"""
    m = re.search(r'= JSON\.parse\((".*")\);\n$', path.read_text(encoding="utf-8"), re.S)
    if not m:
        raise SystemExit(f"{path}: not a json2js file")
    return json.loads(json.loads(m.group(1)))


def questions_from_site(site: Path) -> dict:
    """questions.js and its index entry from the area files already in site/data/traces (the same payload build() writes)"""
    out = site / "data" / "traces"
    index = read_js(out / "index.js")
    if not index.get("available"):
        raise SystemExit("site/data/traces/index.js has no trace data")
    ids = [a["id"] for a in index["areas"]]
    questions = questions_payload(ids, {aid: read_js(out / f"{aid}.js")["traces"] for aid in ids})
    if licence_scan(questions):
        raise SystemExit("questions: keys that may carry source text")
    j2j = json2js_module()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        qsize = write_js(j2j, questions, "traces_questions", out / "questions.js", tmp, "questions.json")
        index["questions"] = {"file": "questions.js", "bytes": qsize, "count": sum(len(a["q"]) for a in questions["areas"])}
        size = write_js(j2j, nfc(index), "traces_index", out / "index.js", tmp, "index.json")
    return {"files": [{"file": "data/traces/questions.js", "bytes": qsize}, {"file": "data/traces/index.js", "bytes": size}],
            "questions": index["questions"]["count"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--traces", type=Path, default=None, help="folder with index.json and <area>.json (build/traces)")
    ap.add_argument("--site", type=Path, required=True)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--questions-from-site", action="store_true",
                    help="only rebuild data/traces/questions.js (and its index entry) from the area files in the site")
    a = ap.parse_args(argv)
    rep = questions_from_site(a.site) if a.questions_from_site else build(a.traces, a.site)
    text = json.dumps(rep, ensure_ascii=False, indent=1)
    print(text[:3000])
    if a.report:
        a.report.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
