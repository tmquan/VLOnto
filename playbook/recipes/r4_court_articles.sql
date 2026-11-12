-- Articles applied by the largest number of court decisions
-- (a decision that cites several clauses of one article counts once).
SELECT d.doc_number,
       a.article_no,
       a.heading,
       count(DISTINCT e.decision_id) AS decisions
FROM 'kg/edges_decision_provision.parquet' AS e
JOIN 'kg/articles.parquet'  AS a ON a.article_id = e.dst_article_id
JOIN 'kg/documents.parquet' AS d ON d.doc_id = e.dst_doc_id
GROUP BY d.doc_number, a.article_no, a.heading
ORDER BY decisions DESC, d.doc_number, a.article_no
LIMIT 10;
