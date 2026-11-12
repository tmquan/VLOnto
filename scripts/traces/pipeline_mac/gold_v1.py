#!/usr/bin/env python3
"""Reproduce the node's $R/eval/gold_all.parquet (the 'v1' Q&A -> article labels used by the VLOnto 0.1.0 KG).

Two facts recovered by matching the node's gold_report.json exactly (all 12 resolver counts, 22,523 Q&As):
  1. v1 ran explicit_mention() with the line-break bug described in data_report.md section 7.2: the look-ahead window
     after 'Điều N' stopped at the first line break, so a hyperlinked law name on its own line was not read
     (the repo's eval_retrieval.py has the fix: the window is whitespace-joined).
  2. v1 ran before fix_docnums.py, i.e. against the document numbers of clean.py (616 slug-garbage numbers unfixed).
Run with R pointing to a root whose data/clean/docs_clean.parquet has the 616 fixes reverted (revert_fixes.py), and
EV_OUT = the eval folder to write. Everything else is eval_retrieval.stage_gold unchanged."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_retrieval as ER


def explicit_mention_v1(answer, article):
    for m in re.finditer(r"Điều\s+%s(?![\w/])" % re.escape(article), answer):
        win = answer[m.end(): m.end() + 240].split("\n")[0]          # v1: reading stops at the line break
        win = re.split(r"(?<=[a-zđàáảãạ\)])\.\s", win)[0]
        mm = re.match(r"^\s*(?:,\s*)?(?:của\s+)?" + ER.LAWTYPES + r"\s+(?:số\s+)?(" + ER.NUMPAT + ")", win)
        if mm:
            return ("num", mm.group(1), mm.group(2), None)
        mm = re.match(r"^\s*(?:,\s*)?(?:của\s+)?" + ER.LAWTYPES + r"\s+([^\d\n,.;:()“”\"]{2,80}?)\s+(?:năm\s+)?(\d{4})(?!\d|/)", win)
        if mm:
            return ("name_year", mm.group(1), mm.group(2).strip(), mm.group(3))
        mm = re.match(r"^\s*(?:,\s*)?(?:của\s+)?" + ER.LAWTYPES + r"\s+([^\d\n,.;:()“”\"]{2,80}?)\s*(?:quy định|như sau|về|thì|có|được|nêu|,|\.|;|:|\(|$)", win)
        if mm and mm.group(1) in ER.NAME_TYPES:
            return ("name", mm.group(1), mm.group(2).strip(), None)
    return None


if __name__ == "__main__":
    ER.explicit_mention = explicit_mention_v1
    ER.EV = os.environ["EV_OUT"]
    os.makedirs(ER.EV, exist_ok=True)
    ER.stage_gold()
