"""Load the browser-sized Turtle subset into pyoxigraph and run SPARQL."""
from pyoxigraph import RdfFormat, Store

store = Store()  # in memory
store.load(path="rdf/vlonto-core.ttl", format=RdfFormat.TURTLE)
print(f"{len(store):,} triples")

QUERY = """
PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?number ?title WHERE {
  ?code a vlo:Code ; vlo:title ?title ; vlo:isInForce true .
  OPTIONAL { ?code vlo:documentNumber ?number }
}
ORDER BY ?number
"""
for row in store.query(QUERY):
    number = row["number"].value if row["number"] else "-"
    print(number, row["title"].value)
