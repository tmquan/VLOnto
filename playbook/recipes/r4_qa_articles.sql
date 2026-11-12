-- Articles cited by the largest number of published Q&A answers
-- (a Q&A whose answer cites several clauses of one article counts once).
SELECT d.doc_number,
       a.article_no,
       a.heading,
       count(DISTINCT e.qa_id) AS qas
FROM 'kg/edges_qa_article.parquet' AS e
JOIN 'kg/articles.parquet'  AS a ON a.article_id = e.dst_article_id
JOIN 'kg/documents.parquet' AS d ON d.doc_id = a.doc_id
GROUP BY a.article_id, d.doc_number, a.article_no, a.heading
ORDER BY qas DESC, d.doc_number, a.article_no
LIMIT 10;
