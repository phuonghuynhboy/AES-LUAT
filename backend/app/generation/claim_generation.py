"""Chuẩn bị context/prompt, parse JSON và tạo các legal claim."""

from __future__ import annotations

import json
import logging
import re

from .gemini_client import generate_with_retry
from .rag_config import GRAPH_CONFIG
from .rag_state import RAGState

logger = logging.getLogger(__name__)


def truncate_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    candidate = normalized[:max_chars].rstrip()
    # Ưu tiên cắt ở ranh giới câu/ý, tránh cắt giữa một mệnh đề pháp lý.
    minimum_boundary = int(max_chars * 0.6)
    boundaries = [
        candidate.rfind(mark, minimum_boundary)
        for mark in (". ", "; ", ": ", "? ", "! ")
    ]
    boundary = max(boundaries, default=-1)
    if boundary >= minimum_boundary:
        candidate = candidate[: boundary + 1].rstrip()
    else:
        whitespace = candidate.rfind(" ", minimum_boundary)
        if whitespace >= minimum_boundary:
            candidate = candidate[:whitespace].rstrip()
    return candidate + "..."


def build_context(retrieved: list[dict]) -> str:
    """Đóng gói các chunk thành context ngắn cho Gemini."""
    if not retrieved:
        return "(Không tìm thấy điều khoản liên quan.)"

    blocks: list[str] = []
    total_chars = 0
    max_context_chars = int(GRAPH_CONFIG["max_context_chars"])
    max_chunk_chars = int(GRAPH_CONFIG["max_chunk_chars"])

    for index, chunk in enumerate(retrieved, start=1):
        provision_id = str(chunk.get("provision_id", "")).strip()
        breadcrumb = str(chunk.get("breadcrumb", "")).strip()
        text = truncate_text(str(chunk.get("text", "")), max_chunk_chars)
        block = (
            f"[NGUỒN {index}]\n"
            f"provision_id: {provision_id}\n"
            f"breadcrumb: {breadcrumb}\n"
            f"nội dung: {text}"
        )

        if total_chars + len(block) > max_context_chars:
            remaining = max_context_chars - total_chars
            if remaining > 600:
                blocks.append(block[:remaining].rstrip() + "...")
            break
        blocks.append(block)
        total_chars += len(block)

    return "\n\n---\n\n".join(blocks)


def make_generation_prompt(question: str, context: str) -> str:
    return f"""NGỮ CẢNH:
{context}

CÂU HỎI:
{question}

Hãy trích xuất các kết luận pháp lý cần thiết để trả lời câu hỏi và trả về đúng JSON schema đã yêu cầu.
"""


def parse_generation_json(raw: str, retrieved: list[dict]) -> list[dict]:
    raw = (raw or "").strip()
    if not raw:
        return []

    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Generation không trả JSON hợp lệ.")
        return []

    claims = data.get("claims", []) if isinstance(data, dict) else []
    if not isinstance(claims, list):
        return []

    allowed_ids = {
        str(chunk.get("provision_id", "")).strip()
        for chunk in retrieved
        if str(chunk.get("provision_id", "")).strip()
    }
    output: list[dict] = []
    seen_claim_ids: set[str] = set()

    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            continue

        claim_id = str(claim.get("claim_id") or f"claim_{index}").strip()
        question_part = str(claim.get("question_part") or "").strip()
        claim_text = str(claim.get("text") or "").strip()
        answerable = bool(claim.get("answerable", False))
        evidence_ids = claim.get("evidence_chunk_ids") or []
        if not question_part:
            question_part = claim_text or f"Ý {index} của câu hỏi"
        if not isinstance(evidence_ids, list):
            evidence_ids = []

        cleaned_ids: list[str] = []
        for provision_id in evidence_ids:
            provision_id = str(provision_id).strip()
            if provision_id in allowed_ids and provision_id not in cleaned_ids:
                cleaned_ids.append(provision_id)
        if answerable and not cleaned_ids:
            answerable = False
        if claim_id in seen_claim_ids:
            claim_id = f"{claim_id}_{index}"
        seen_claim_ids.add(claim_id)

        output.append(
            {
                "claim_id": claim_id,
                "question_part": question_part,
                "text": claim_text,
                "answerable": answerable,
                "evidence_chunk_ids": cleaned_ids,
            }
        )
    return output


def generate_node(state: RAGState) -> dict:
    retrieved = state.get("retrieved", [])
    if not retrieved:
        return {"claims": []}

    context = build_context(retrieved)
    prompt = make_generation_prompt((state.get("question") or "").strip(), context)
    return {"claims": parse_generation_json(generate_with_retry(prompt), retrieved)}
