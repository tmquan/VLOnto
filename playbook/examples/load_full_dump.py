"""Bulk-load the full N-Triples dump into an on-disk pyoxigraph store."""
import gzip

from pyoxigraph import RdfFormat, Store

store = Store("vlonto-store")  # RocksDB directory, created if missing
with gzip.open("rdf/vlonto-kg.nt.gz", "rb") as dump:
    store.bulk_load(dump, format=RdfFormat.N_TRIPLES)
store.optimize()
print(f"{len(store):,} triples in vlonto-store/")
