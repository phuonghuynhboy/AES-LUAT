"""Orchestrator của pipeline RAG pháp lý.

Các trách nhiệm retrieval, gọi Gemini, tạo claim, xác minh và định dạng câu trả
lời nằm trong các module chuyên biệt cùng package. Module này giữ entry point
``answer_question`` và re-export các tên cũ để không làm gãy code đang sử dụng.

Chạy CLI từ thư mục gốc repository::

    python -m backend.app.generation.rag_graph "Câu hỏi pháp lý"
"""

from __future__ import annotations

import logging
from threading import Lock

from langgraph.graph import END, StateGraph

from .answer_builder import build_answer_node, format_citation
from .claim_generation import (
    build_context,
    generate_node,
    make_generation_prompt,
    parse_generation_json,
    truncate_text,
)
from .claim_verification import (
    chunk_map,
    decision_node,
    structural_validate_node,
    verify_claim,
    verify_node,
)
from .gemini_client import (
    call_gemini_once,
    candidate_models,
    generate_with_retry,
    get_api_key,
    get_client,
    is_model_error,
    is_non_retryable_error,
    is_overloaded_error,
    looks_incomplete_answer,
    make_generate_config,
    response_to_text,
)
from .prompts import SYSTEM_PROMPT
from .rag_config import GRAPH_CONFIG
from .rag_state import RAGState
from .retrieval_node import get_retriever, retrieve_node

logger = logging.getLogger(__name__)

# Alias tương thích với các tên helper của file nguyên khối trước đây.
_get_retriever = get_retriever
_get_api_key = get_api_key
_get_client = get_client
_truncate_text = truncate_text
_build_context = build_context
_make_prompt = make_generation_prompt
_response_to_text = response_to_text
_is_model_error = is_model_error
_is_overloaded_error = is_overloaded_error
_is_non_retryable_error = is_non_retryable_error
_candidate_models = candidate_models
_make_generate_config = make_generate_config
_call_gemini_once = call_gemini_once
_looks_incomplete_answer = looks_incomplete_answer
_call_llm_with_retry = generate_with_retry
_parse_generation_json = parse_generation_json
_chunk_map = chunk_map
_verify_one_claim = verify_claim
_format_citation = format_citation


def _quiet_noisy_loggers() -> None:
    from .rag_cli import quiet_noisy_loggers

    quiet_noisy_loggers()


_quiet_noisy_loggers()


def build_graph():
    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("structural_validate", structural_validate_node)
    graph.add_node("verify", verify_node)
    graph.add_node("decision", decision_node)
    graph.add_node("build_answer", build_answer_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "structural_validate")
    graph.add_edge("structural_validate", "verify")
    graph.add_edge("verify", "decision")
    graph.add_edge("decision", "build_answer")
    graph.add_edge("build_answer", END)
    return graph.compile()


_compiled_graph = None
_graph_lock = Lock()


def serialize_source(result: dict) -> dict:
    """Serialize one retrieved chunk without changing its legal text."""
    return {
        "provision_id": result.get("provision_id"),
        "provision_key": result.get("provision_key"),
        "breadcrumb": result.get("breadcrumb"),
        "doc_id": result.get("doc_id"),
        # This is the original retrieved corpus chunk, never LLM/claim text.
        "text": result.get("text"),
        "valid_from": result.get("valid_from"),
        "valid_to": result.get("valid_to"),
        "temporal_warning": result.get("temporal_warning"),
        "rrf_score": result.get("rrf_score"),
        "retriever_sources": result.get("sources") or [],
    }


def build_response_sources(
    verified_claims: list[dict],
    retrieved: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Return cited sources and all retrieval candidates as separate lists.

    Citation membership is based only on ``evidence_chunk_ids`` from verified
    supported/partially-supported claims. Duplicate physical IDs are handled
    deterministically by retaining the first retrieved chunk.
    """
    source_by_id: dict[str, dict] = {}
    retrieved_sources: list[dict] = []

    for result in retrieved:
        provision_id = str(result.get("provision_id") or "").strip()
        if not provision_id:
            continue
        if provision_id in source_by_id:
            logger.warning(
                "Duplicate retrieved source provision_id=%s; keeping first occurrence.",
                provision_id,
            )
            continue
        serialized = serialize_source(result)
        source_by_id[provision_id] = serialized
        retrieved_sources.append(serialized)

    cited_ids: list[str] = []
    seen_ids: set[str] = set()
    for claim in verified_claims:
        if claim.get("status") not in {"supported", "partially_supported"}:
            continue
        for evidence_id in claim.get("evidence_chunk_ids") or []:
            evidence_id = str(evidence_id).strip()
            if not evidence_id or evidence_id in seen_ids:
                continue
            seen_ids.add(evidence_id)
            cited_ids.append(evidence_id)

    sources: list[dict] = []
    for evidence_id in cited_ids:
        source = source_by_id.get(evidence_id)
        if source is None:
            logger.warning(
                "Verified citation metadata missing for provision_id=%s.",
                evidence_id,
            )
            continue
        sources.append(source)

    return sources, retrieved_sources


def answer_question(question: str) -> dict:
    """Entry point chính cho FastAPI/backend."""
    global _compiled_graph

    question = (question or "").strip()
    if not question:
        return {
            "status": "refusal",
            "answer": "Vui lòng nhập câu hỏi.",
            "claims": [],
            "sources": [],
            "retrieved_sources": [],
            "warnings": ["Câu hỏi rỗng."],
        }

    if _compiled_graph is None:
        with _graph_lock:
            if _compiled_graph is None:
                _compiled_graph = build_graph()
    final_state = _compiled_graph.invoke(
        {
            "question": question,
            "retrieved": [],
            "claims": [],
            "verified_claims": [],
            "decision": "",
            "answer": "",
            "warnings": [],
        }
    )

    verified_claims = final_state.get("verified_claims", [])
    sources, retrieved_sources = build_response_sources(
        verified_claims,
        final_state.get("retrieved", []),
    )

    return {
        "status": final_state.get("decision", "refusal"),
        "answer": final_state.get("answer", ""),
        "claims": verified_claims,
        "sources": sources,
        "retrieved_sources": retrieved_sources,
        "warnings": final_state.get("warnings", []),
    }


def debug_question(question: str) -> None:
    from .rag_cli import debug_question as run_debug

    run_debug(question)


def main() -> None:
    from .rag_cli import main as run_cli

    run_cli()


if __name__ == "__main__":
    main()
