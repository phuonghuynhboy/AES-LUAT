"""Cấu hình mặc định cho các retriever."""

from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))

CONFIG = {
    "chunks_path": os.path.join(PROJECT_ROOT, "data", "chunks", "*.json"),
    "chroma_persist_dir": os.path.join(PROJECT_ROOT, "data", "chroma_db"),
    "collection_name": "luat_chunks",
    "embedding_model": "bkai-foundation-models/vietnamese-bi-encoder",
    "bm25_top_k": 20,
    "dense_top_k": 20,
    # Không trộn kết quả dense nếu Chroma chỉ chứa một phần corpus. Nếu vẫn
    # fusion trong trạng thái này, RRF có thể đẩy chunk của văn bản đã index
    # lên trên kết quả BM25 đúng từ các văn bản còn lại.
    "min_dense_corpus_coverage": 0.95,
    "disable_incomplete_dense": True,
    "candidate_multiplier": 4,
    "rrf_k": 60,
    "final_top_n": 8,
    "strict_temporal": False,
}
