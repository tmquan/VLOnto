-- What replaced (or repealed) the Labour Code 10/2012/QH13?
SELECT n.doc_number AS new_number,
       n.title_vi   AS new_title,
       c.kind,
       c.effective_date
FROM 'kg/changes.parquet'   AS c
JOIN 'kg/documents.parquet' AS o ON o.doc_id = c.affected_doc_id
JOIN 'kg/documents.parquet' AS n ON n.doc_id = c.acting_doc_id
WHERE o.doc_number = '10/2012/QH13'
  AND c.kind IN ('replaced', 'repealed')
ORDER BY c.effective_date, new_number;
