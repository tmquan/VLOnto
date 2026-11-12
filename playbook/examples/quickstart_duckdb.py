"""Count documents per validity class with DuckDB (run next to the kg/ folder)."""
import duckdb

con = duckdb.connect()
rows = con.execute("""
    SELECT validity, count(*) AS documents
    FROM 'kg/documents.parquet'
    GROUP BY validity
    ORDER BY documents DESC, validity
""").fetchall()
for validity, n in rows:
    print(f"{validity:<27}{n:>7,}")
