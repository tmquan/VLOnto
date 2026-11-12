"""Find a document by its number and list its first articles with polars."""
import polars as pl

docs = pl.read_parquet("kg/documents.parquet")
code = docs.filter(pl.col("doc_number") == "45/2019/QH14")
for row in code.select("doc_id", "title_vi", "issue_date", "validity").iter_rows():
    print(*row, sep=" | ")

articles = (
    pl.scan_parquet("kg/articles.parquet")
    .filter(pl.col("doc_id") == code["doc_id"][0])
    .sort("position")
    .select("article_no", "heading")
    .head(4)
    .collect()
)
for no, heading in articles.iter_rows():
    print(f"Điều {no}: {heading}")
