"""LangGraph node kết nối pipeline generation với HybridRetriever."""

from __future__ import annotations

from threading import Lock

from ..retrieval.retriever import CONFIG as RETRIEVER_CONFIG
from ..retrieval.retriever import HybridRetriever
from .rag_config import GRAPH_CONFIG
from .rag_state import RAGState

_retriever_instance: HybridRetriever | None = None
_retriever_lock = Lock()


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
    results = get_retriever().retrieve(
        question,
        top_n=int(GRAPH_CONFIG["retrieve_top_n"]),
    )
    return {"retrieved": results}
