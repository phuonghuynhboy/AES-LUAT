"""LangGraph node kết nối pipeline generation với HybridRetriever."""

from __future__ import annotations

from datetime import date
import re
from threading import Lock

from ..retrieval.retriever import CONFIG as RETRIEVER_CONFIG
from ..retrieval.retriever import HybridRetriever
from .rag_config import GRAPH_CONFIG
from .rag_state import RAGState

_retriever_instance: HybridRetriever | None = None
_retriever_lock = Lock()


def extract_as_of_date(question: str) -> str | None:
    """Đọc mốc ngày ISO hoặc dd/mm/yyyy được nêu trực tiếp trong câu hỏi."""
    iso_match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", question)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(1)).isoformat()
        except ValueError:
            pass

    dmy_match = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", question)
    if dmy_match:
        day, month, year = (int(value) for value in dmy_match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass
    return None


def get_retriever() -> HybridRetriever:
    """Khởi tạo retriever một lần để tái sử dụng index và vector store."""
    global _retriever_instance
    if _retriever_instance is None:
        with _retriever_lock:
            if _retriever_instance is None:
                _retriever_instance = HybridRetriever(RETRIEVER_CONFIG)
    return _retriever_instance


def retrieve_node(state: RAGState) -> dict:
    question = (state.get("question") or "").strip()
    if not question:
        return {"retrieved": []}
    as_of = state.get("as_of") or extract_as_of_date(question)
    results = get_retriever().retrieve(
        question,
        top_n=int(GRAPH_CONFIG["retrieve_top_n"]),
        as_of=as_of,
    )
    return {"retrieved": results}
