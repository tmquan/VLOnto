#!/usr/bin/env python3
"""Run chunk.py unchanged except for two Mac adaptations:
  * chunk_anle(): the anle dataset is not part of this rebuild (not needed for the Q&A -> article labels), so its chunk
    table is skipped and the report says so;
  * multiprocessing.Pool.map is replaced by concurrent.futures.ProcessPoolExecutor.map (same function, same order of
    results; a worker killed under memory pressure raises BrokenProcessPool instead of hanging the run)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from concurrent.futures import ProcessPoolExecutor
import chunk as CH


class _ExecPool:
    def __init__(self, n, initializer=None, initargs=()):
        self.ex = ProcessPoolExecutor(n, initializer=initializer, initargs=initargs)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.ex.shutdown()

    def map(self, f, it, chunksize=1):
        return list(self.ex.map(f, it, chunksize=chunksize))


def _no_anle():
    return {"anle_skipped": "anle-toaan-gov-vn not downloaded for the Mac rebuild; anle_chunks.parquet not written"}


if __name__ == "__main__":
    assert os.path.abspath(CH.__file__).startswith(os.path.dirname(os.path.abspath(__file__))), CH.__file__
    CH.chunk_anle = _no_anle
    CH.Pool = _ExecPool
    CH.main()
