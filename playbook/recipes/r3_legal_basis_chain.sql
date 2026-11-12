-- Legal-basis chain of the enterprise accounting circular 99/2025/TT-BTC:
-- follow vlo:legalBasis edges up to three steps, keep the shortest depth.
WITH RECURSIVE chain(doc_id, depth, path) AS (
    SELECT doc_id, 0, [doc_id]
    FROM 'kg/documents.parquet'
    WHERE doc_number = '99/2025/TT-BTC'
  UNION ALL
    SELECT e.dst_doc_id, c.depth + 1, list_append(c.path, e.dst_doc_id)
    FROM chain AS c
    JOIN 'kg/edges_legal_basis.parquet' AS e ON e.src_doc_id = c.doc_id
    WHERE c.depth < 3 AND NOT list_contains(c.path, e.dst_doc_id)
)
SELECT min(c.depth) AS depth,
       coalesce(d.doc_number, '-') AS number,
       d.doc_type_vi AS type,
       d.title_vi AS title
FROM chain AS c
JOIN 'kg/documents.parquet' AS d USING (doc_id)
WHERE c.depth > 0
GROUP BY d.doc_number, d.doc_type_vi, d.title_vi
ORDER BY depth, number, title;
