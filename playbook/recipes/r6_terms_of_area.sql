-- Legal terms of the area 'Labour and wages', with the provenance of
-- the English label (mt = machine translation, site = from the source).
SELECT t.label_vi,
       coalesce(t.label_en, '-') AS label_en,
       coalesce(t.label_en_source, '-') AS en_source
FROM 'kg/terms.parquet' AS t
JOIN 'kg/areas.parquet' AS a USING (area_id)
WHERE a.label_en = 'Labour and wages'
ORDER BY t.label_vi, t.term_id;
