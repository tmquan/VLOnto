"""BM25 (Lucene variant) over Vietnamese syllables, numpy/scipy implementation.

Tokens are hashed to 64-bit ids (blake2b) so tokenisation can run in many
processes without sharing a vocabulary; the index stores the sorted unique
hashes (vocabulary) and a term-major CSR matrix of BM25 weights, so a query
score is the sum of a few sparse rows.
"""
import os, sys, json, time, hashlib
import numpy as np
import scipy.sparse as sp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vnlegal_text as V

K1, B = 1.2, 0.75

def h64(tok):
    return int.from_bytes(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(), "little")

def hash_tokens(text, bigrams=False):
    return np.fromiter((h64(t) for t in V.vi_tokens(text, bigrams=bigrams)), dtype=np.uint64)

def build(token_hash_lists, k1=K1, b=B):
    """token_hash_lists: list of np.uint64 arrays (one per document)."""
    lens = np.array([len(a) for a in token_hash_lists], dtype=np.int64)
    n_docs = len(lens)
    allh = np.concatenate(token_hash_lists) if n_docs else np.zeros(0, np.uint64)
    doc = np.repeat(np.arange(n_docs, dtype=np.int64), lens)
    vocab, term = np.unique(allh, return_inverse=True)
    del allh
    key = term.astype(np.int64) * n_docs + doc
    del term, doc
    ukey, tf = np.unique(key, return_counts=True)
    del key
    t = (ukey // n_docs).astype(np.int64); d = (ukey % n_docs).astype(np.int32)
    del ukey
    df = np.bincount(t, minlength=len(vocab)).astype(np.float64)
    idf = np.log1p((n_docs - df + 0.5) / (df + 0.5))
    avgdl = lens.mean() if n_docs else 1.0
    denom = tf + k1 * (1 - b + b * lens[d] / avgdl)
    w = (idf[t] * tf * (k1 + 1) / denom).astype(np.float32)
    indptr = np.zeros(len(vocab) + 1, dtype=np.int64)
    np.cumsum(np.bincount(t, minlength=len(vocab)), out=indptr[1:])
    W = sp.csr_matrix((w, d, indptr), shape=(len(vocab), n_docs))
    return {"vocab": vocab, "W": W, "idf": idf.astype(np.float32), "avgdl": float(avgdl), "n_docs": n_docs,
            "nnz": int(W.nnz)}

def save(idx, path):
    os.makedirs(path, exist_ok=True)
    np.save(os.path.join(path, "vocab.npy"), idx["vocab"])
    sp.save_npz(os.path.join(path, "W.npz"), idx["W"], compressed=False)
    json.dump({k: idx[k] for k in ("avgdl", "n_docs", "nnz")}, open(os.path.join(path, "params.json"), "w"))

class BM25Index:
    def __init__(self, path, bigrams=False):
        self.vocab = np.load(os.path.join(path, "vocab.npy"))
        self.W = sp.load_npz(os.path.join(path, "W.npz")).tocsr()
        self.bigrams = bigrams
        self.n_docs = self.W.shape[1]

    def term_ids(self, query):
        hs = np.unique(hash_tokens(query, self.bigrams))
        pos = np.searchsorted(self.vocab, hs)
        pos = np.clip(pos, 0, len(self.vocab) - 1)
        return pos[self.vocab[pos] == hs]

    def scores(self, query, mask=None):
        ids = self.term_ids(query)
        if len(ids) == 0:
            return np.zeros(self.n_docs, dtype=np.float32)
        s = np.asarray(self.W[ids].sum(axis=0)).ravel()
        if mask is not None:
            s = np.where(mask, s, -1.0)
        return s

    def search(self, query, k=100, mask=None):
        s = self.scores(query, mask)
        k = min(k, len(s))
        top = np.argpartition(-s, k - 1)[:k]
        top = top[np.argsort(-s[top], kind="stable")]
        top = top[s[top] > 0]
        return top, s[top]
