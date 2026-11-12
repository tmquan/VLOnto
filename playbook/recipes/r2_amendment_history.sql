-- Amendment history of the Land Law 31/2024/QH15: every change event
-- whose affected document is the law, oldest first.
SELECT c.effective_date,
       a.doc_number AS acting_number,
       a.doc_type_vi AS acting_type,
       c.kind
FROM 'kg/changes.parquet'   AS c
JOIN 'kg/documents.parquet' AS d ON d.doc_id = c.affected_doc_id
JOIN 'kg/documents.parquet' AS a ON a.doc_id = c.acting_doc_id
WHERE d.doc_number = '31/2024/QH15'
ORDER BY c.effective_date NULLS LAST, acting_number, c.kind;
