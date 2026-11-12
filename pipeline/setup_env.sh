#!/usr/bin/env bash
# Build the data-track Python env with uv (no root, no conda needed).
set -euo pipefail
R=${R:-/path/to/vnlegal}
export UV_CACHE_DIR=$R/uv-cache UV_PYTHON_INSTALL_DIR=$R/python
UV=$R/bin/uv
if [ ! -x $R/envs/data/bin/python ]; then $UV venv --python 3.12 $R/envs/data; fi
# light data stack first (download, profiling, cleaning, chunking, BM25, API)
$UV pip install --python $R/envs/data/bin/python \
  "huggingface_hub[hf_xet]" hf_transfer pyarrow polars pandas numpy regex orjson tqdm \
  bm25s PyStemmer scipy faiss-cpu fastapi "uvicorn[standard]" requests rapidfuzz
$R/envs/data/bin/python -c "import huggingface_hub, pyarrow, polars, bm25s, faiss; print('hub', huggingface_hub.__version__, 'pyarrow', pyarrow.__version__, 'polars', polars.__version__, 'bm25s', bm25s.__version__, 'faiss', faiss.__version__)"
