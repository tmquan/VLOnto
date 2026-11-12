-- Legal Q&As whose answer cites Article 35 of the Labour Code 45/2019/QH14
-- (newest first; the text of the Q&A is at the source URL in qas.url).
SELECT q.qa_id,
       q.published_date,
       q.category,
       coalesce(e.clause, '-') AS clause,
       coalesce(e.point, '-') AS point
FROM 'kg/edges_qa_article.parquet' AS e
JOIN 'kg/qas.parquet' AS q USING (qa_id)
WHERE e.dst_article_id = (
    SELECT a.article_id
    FROM 'kg/articles.parquet' AS a
    JOIN 'kg/documents.parquet' AS d USING (doc_id)
    WHERE d.doc_number = '45/2019/QH14'
      AND a.article_no = '35' AND a.segment = 'main')
ORDER BY q.published_date DESC, q.qa_id, clause, point;
