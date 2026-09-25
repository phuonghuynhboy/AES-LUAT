"""Biến các claim đã xác minh thành câu trả lời và cảnh báo cuối."""

from __future__ import annotations

from .claim_verification import chunk_map
from .rag_state import RAGState


def format_citation(provision_id: str, chunks: dict[str, dict]) -> str:
    chunk = chunks.get(provision_id) or {}
    breadcrumb = str(chunk.get("breadcrumb") or "").strip()
    return f"{breadcrumb} — {provision_id}" if breadcrumb else provision_id


def build_answer_node(state: RAGState) -> dict:
    decision = state.get("decision", "refusal")
    verified = state.get("verified_claims", [])
    available_chunks = chunk_map(state.get("retrieved", []))
    warnings = list(state.get("warnings", []))

    if decision == "refusal":
        warnings.append("INSUFFICIENT_LEGAL_EVIDENCE")
        return {
            "answer": (
                "Không tìm thấy đủ căn cứ pháp lý đáng tin cậy trong ngữ cảnh "
                "được cung cấp để trả lời câu hỏi này."
            ),
            "warnings": warnings,
        }

    usable = [
        claim
        for claim in verified
        if claim.get("status") in {"supported", "partially_supported"}
    ]
    unsupported = [
        claim for claim in verified if claim.get("status") == "unsupported"
    ]

    lines: list[str] = []
    for claim in usable:
        citations = [
            format_citation(provision_id, available_chunks)
            for provision_id in claim.get("evidence_chunk_ids", [])
            if provision_id in available_chunks
        ]
        suffix = f" ({'; '.join(citations)})" if citations else ""
        lines.append(f"- {claim.get('text', '').strip()}{suffix}")

    if decision == "partial_answer":
        warnings.append("PARTIAL_ANSWER_SOME_CLAIMS_NOT_FULLY_SUPPORTED")
        missing_parts = [
            str(claim.get("question_part") or claim.get("text") or "").strip()
            for claim in unsupported
            if str(claim.get("question_part") or claim.get("text") or "").strip()
        ]
        if missing_parts:
            lines.append(
                "- Chưa đủ căn cứ trong nguồn hiện có để trả lời: "
                + "; ".join(missing_parts)
                + "."
            )

    return {"answer": "\n".join(lines).strip(), "warnings": warnings}
