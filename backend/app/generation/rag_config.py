"""Cấu hình runtime cho pipeline RAG."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOTENV_PATH = PROJECT_ROOT / ".env"

# Process environment has priority; .env is only a local-development fallback.
try:
    from dotenv import load_dotenv
except ImportError:
    pass
else:
    load_dotenv(DOTENV_PATH, override=False)


GRAPH_CONFIG: dict[str, Any] = {
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    "fallback_models": ["gemini-3.6-flash"],
    # Chỉ lưu TÊN biến môi trường, tuyệt đối không lưu giá trị API key tại đây.
    "gemini_api_key_env": "GEMINI_API_KEY",
    "temperature": 0.0,
    # Mặc định lấy đủ số nguồn mà retriever đã thiết kế để trả về. Các biến môi
    # trường giúp chạy sweep 2/4/6/8 mà không sửa mã giữa các benchmark.
    "retrieve_top_n": int(os.getenv("RAG_RETRIEVE_TOP_N", "8")),
    "max_context_chars": int(os.getenv("RAG_MAX_CONTEXT_CHARS", "20000")),
    "max_chunk_chars": int(os.getenv("RAG_MAX_CHUNK_CHARS", "2000")),
    "max_output_tokens": 2048,
    "max_retries": 3,
    "retry_backoff_base_sec": 2.0,
    "gemini_timeout_ms": 60_000,
    "not_found_phrase": (
        "Không tìm thấy quy định liên quan trong ngữ cảnh được cung cấp."
    ),
}
