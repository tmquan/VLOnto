"""Knowledge-graph tools for the Vietnamese legal assistant agent.

Three read-only functions over the VLOnto parquet tables (DuckDB, in process):

  check_validity(doc_number)                  validity, replacing acts and
                                              amendments with their evidence
  expand_citations(doc_number, article_no)    what an article cites, what cites
                                              it, how many Q&A answers cite it
  related_provisions(doc_number, article_no)  articles cited together with
                                              it in Q&A answers

Each function returns a plain dict; to_text() turns it into the short text an
agent tool returns to the model. Co-citation is a usage signal, not a statement
that two provisions are legally related. VLOnto v1 has no court decisions (they
join in v2), so the usage signals come from the published Q&As.
"""
import textwrap

import duckdb

TABLES = ("documents", "articles", "changes", "edges_citation",
          "edges_qa_article")
SUPERSEDING = ("replaced", "repealed")

# co-citation: articles cited in the same Q&A answers as article ?, scored by
# shared * ln(N / df) so that articles cited almost everywhere rank low
RELATED_SQL = """
WITH s AS (SELECT DISTINCT {unit} FROM {table} WHERE dst_article_id = ?),
co AS (SELECT e.dst_article_id AS aid, count(DISTINCT e.{unit}) AS shared
       FROM {table} e JOIN s USING ({unit})
       WHERE e.dst_article_id <> ?
       GROUP BY 1 HAVING count(DISTINCT e.{unit}) >= ?),
df AS (SELECT dst_article_id AS aid, count(DISTINCT {unit}) AS df
       FROM {table} WHERE dst_article_id IN (SELECT aid FROM co) GROUP BY 1),
n AS (SELECT count(DISTINCT {unit}) AS n FROM {table}
      WHERE dst_article_id IS NOT NULL)
SELECT d.doc_number, a.article_no, a.heading, co.shared, df.df,
       round(co.shared * ln(n.n / df.df), 1) AS score
FROM co JOIN df USING (aid) CROSS JOIN n
JOIN articles a ON a.article_id = co.aid
JOIN documents d ON d.doc_id = a.doc_id
ORDER BY score DESC, d.doc_number, a.article_no
LIMIT ?
"""


CITES_SQL = """
SELECT d.doc_number, t.article_no, sum(e.n_mentions) AS mentions
FROM edges_citation e
JOIN documents d ON d.doc_id = e.dst_doc_id
LEFT JOIN articles t ON t.article_id = e.dst_article_id
WHERE e.src_article_id = ?
GROUP BY ALL
ORDER BY mentions DESC, d.doc_number, t.article_no
LIMIT ?
"""

CITED_BY_SQL = """
SELECT DISTINCT d.doc_number, s.article_no, d.issue_date
FROM edges_citation e
JOIN documents d ON d.doc_id = e.src_doc_id
LEFT JOIN articles s ON s.article_id = e.src_article_id
WHERE e.dst_article_id = ?
ORDER BY d.issue_date DESC NULLS LAST, d.doc_number, s.article_no
"""


class VLOntoTools:
    def __init__(self, kg_dir="kg"):
        self.con = duckdb.connect()
        for t in TABLES:
            path = f"{kg_dir}/{t}.parquet"
            self.con.execute(
                f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{path}')")

    def _rows(self, sql, params=()):
        cur = self.con.execute(sql, list(params))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _count(self, table, unit, aid):
        sql = (f"SELECT count(DISTINCT {unit}) AS n FROM {table} "
               "WHERE dst_article_id = ?")
        return self._rows(sql, [aid])[0]["n"]

    def _article(self, doc_number, article_no):
        rows = self._rows(
            "SELECT a.article_id, a.heading FROM articles a "
            "JOIN documents d USING (doc_id) "
            "WHERE d.doc_number = ? AND a.article_no = ? "
            "AND a.segment = 'main' ORDER BY a.article_id",
            [doc_number, str(article_no)])
        if not rows:
            raise KeyError(f"{doc_number} Điều {article_no}: not in the graph")
        return rows[0]

    def check_validity(self, doc_number):
        docs = self._rows(
            "SELECT doc_id, title_vi, validity, in_force, expiry_date "
            "FROM documents WHERE doc_number = ? ORDER BY doc_id", [doc_number])
        if not docs:
            return {"doc_number": doc_number, "found": False}
        d = docs[0]
        events = self._rows(
            "SELECT c.kind, c.effective_date, a.doc_number AS by_number, "
            "c.evidence FROM changes c "
            "JOIN documents a ON a.doc_id = c.acting_doc_id "
            "WHERE c.affected_doc_id = ? "
            "ORDER BY c.effective_date NULLS LAST, by_number, c.kind",
            [d["doc_id"]])
        return {
            "doc_number": doc_number, "found": True, "title": d["title_vi"],
            "validity": d["validity"], "in_force": d["in_force"],
            "expiry_date": d["expiry_date"],
            "superseded_by": [e for e in events if e["kind"] in SUPERSEDING],
            "amended_by": [e for e in events if e["kind"] not in SUPERSEDING],
            "same_number_documents": len(docs),
        }

    def expand_citations(self, doc_number, article_no, limit=3):
        art = self._article(doc_number, article_no)
        aid = art["article_id"]
        cited_by = self._rows(CITED_BY_SQL, [aid])
        return {
            "article": f"{doc_number} Điều {article_no}",
            "heading": art["heading"],
            "cites": self._rows(CITES_SQL, [aid, limit]),
            "cited_by_count": len(cited_by),
            "cited_by": cited_by[:limit],
            "qas": self._count("edges_qa_article", "qa_id", aid),
        }

    def related_provisions(self, doc_number, article_no, limit=3,
                           min_shared=2):
        """Articles cited in the same Q&A answers, ranked by
        shared * ln(N / df): the number of shared Q&As weighted by how rare
        the other article is, so that articles cited in almost every answer
        do not dominate."""
        aid = self._article(doc_number, article_no)["article_id"]
        sql = RELATED_SQL.format(table="edges_qa_article", unit="qa_id")
        return {"article": f"{doc_number} Điều {article_no}",
                "in_qas": self._rows(sql, [aid, aid, min_shared, limit])}


def _wrap(text, indent="    ", width=78):
    return textwrap.fill(str(text), width=width, initial_indent=indent,
                         subsequent_indent=indent)


def _art(no):
    return f" Điều {no}" if no else ""


def to_text(result):
    """Render a tool result as the short text a tool returns to the model."""
    lines = []
    if "validity" in result:
        lines.append(f"{result['doc_number']} ({result['title']}): "
                     f"validity {result['validity']}, "
                     f"in force: {result['in_force']}")
        for e in result["superseded_by"]:
            lines.append(f"  {e['kind']} by {e['by_number']} "
                         f"from {e['effective_date']}")
            lines.append(_wrap(f"evidence: {e['evidence']}"))
        for e in result["amended_by"][-3:]:
            lines.append(f"  {e['kind']} by {e['by_number']} "
                         f"from {e['effective_date']}")
        hidden = len(result["amended_by"]) - 3
        if hidden > 0:
            lines.append(f"  ({hidden} earlier amendments not shown)")
    elif "cites" in result:
        lines.append(f"{result['article']}: {result['heading']}")
        for c in result["cites"]:
            lines.append(f"  cites {c['doc_number']}{_art(c['article_no'])}")
        lines.append(f"  cited by {result['cited_by_count']} documents or "
                     f"articles, newest first:")
        for c in result["cited_by"]:
            lines.append(f"    {c['doc_number']}{_art(c['article_no'])} "
                         f"(issued {c['issue_date']})")
        lines.append(f"  cited in {result['qas']:,} Q&A answers")
    else:
        lines.append(f"{result['article']}: provisions cited together with it")
        lines.append("  in Q&As (shared / all citing it / score):")
        for r in result["in_qas"]:
            head = textwrap.shorten(r["heading"] or "-", width=52,
                                    placeholder=" …")
            lines.append(f"    {r['doc_number']}{_art(r['article_no'])}: "
                         f"{head}")
            lines.append(f"      {r['shared']:,} / {r['df']:,} / "
                         f"{r['score']}")
    return "\n".join(lines)
