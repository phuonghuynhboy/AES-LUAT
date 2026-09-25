"""Kiểm tra cấu trúc, xác minh citation và quyết định mức độ trả lời."""

from __future__ import annotations

import json
import logging
import re

from google.genai import types

from .gemini_client import (
    candidate_models,
    get_client,
    is_non_retryable_error,
    response_to_text,
)
from .prompts import VERIFIER_PROMPT
from .rag_state import RAGState

logger = logging.getLogger(__name__)


def chunk_map(retrieved: list[dict]) -> dict[str, dict]:
    return {
        str(chunk.get("provision_id", "")).strip(): chunk
        for chunk in retrieved
        if str(chunk.get("provision_id", "")).strip()
    }


def structural_validate_node(state: RAGState) -> dict:
    warnings: list[str] = []
    available_chunks = chunk_map(state.get("retrieved", []))
    for claim in state.get("claims", []):
        claim_id = claim.get("claim_id")
        evidence_ids = claim.get("evidence_chunk_ids") or []
        if claim.get("answerable") and not evidence_ids:
            warnings.append(
                f"{claim_id}: claim được đánh dấu answerable nhưng không có citation hợp lệ."
            )
            continue
        for provision_id in evidence_ids:
            if provision_id not in available_chunks:
                warnings.append(
                    f"{claim_id}: citation {provision_id} không thuộc retrieved context."
                )
    return {"warnings": warnings}


def verify_claim(claim: dict, evidence_chunks: list[dict]) -> dict:
    if not claim.get("answerable"):
        return {
            "claim_id": claim.get("claim_id"),
            "question_part": claim.get("question_part", ""),
            "text": claim.get("text", ""),
            "answerable": False,
            "evidence_chunk_ids": [],
            "status": "unsupported",
            "score": 0.0,
            "reason": (
                "Không có đủ bằng chứng trong retrieved context để trả lời phần này "
                "của câu hỏi."
            ),
        }

    if not evidence_chunks:
        return {
            "claim_id": claim.get("claim_id"),
            "question_part": claim.get("question_part", ""),
            "text": claim.get("text", ""),
            "evidence_chunk_ids": claim.get("evidence_chunk_ids", []),
            "status": "unsupported",
            "score": 0.0,
            "reason": "Claim không có evidence hợp lệ.",
        }

    evidence = "\n\n---\n\n".join(
        f"provision_id: {chunk.get('provision_id')}\n"
        f"breadcrumb: {chunk.get('breadcrumb')}\n"
        f"nội dung: {chunk.get('text')}"
        for chunk in evidence_chunks
    )
    prompt = f"""CLAIM:
{claim.get('text', '')}

EVIDENCE:
{evidence}
"""

    last_error: Exception | None = None
    for model_name in candidate_models():
        try:
            response = get_client().models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=VERIFIER_PROMPT,
                    temperature=0.0,
                    max_output_tokens=512,
                ),
            )
            raw = response_to_text(response)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
            raw = re.sub(r"\s*```$", "", raw)
            data = json.loads(raw)

            status = str(data.get("status", "")).strip()
            if status not in {"supported", "partially_supported", "unsupported"}:
                status = "unsupported"
            try:
                score = float(data.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0

            return {
                "claim_id": claim.get("claim_id"),
                "question_part": claim.get("question_part", ""),
                "text": claim.get("text", ""),
                "evidence_chunk_ids": claim.get("evidence_chunk_ids", []),
                "status": status,
                "score": max(0.0, min(1.0, score)),
                "reason": str(data.get("reason") or "").strip(),
            }
        except Exception as error:
            last_error = error
            if is_non_retryable_error(error):
                break

    logger.warning("Citation verifier thất bại: %s", last_error)
    return {
        "claim_id": claim.get("claim_id"),
        "question_part": claim.get("question_part", ""),
        "text": claim.get("text", ""),
        "evidence_chunk_ids": claim.get("evidence_chunk_ids", []),
        "status": "unsupported",
        "score": 0.0,
        "reason": "Không xác minh được citation do verifier lỗi.",
    }


def verify_node(state: RAGState) -> dict:
    available_chunks = chunk_map(state.get("retrieved", []))
    verified = []
    for claim in state.get("claims", []):
        evidence_chunks = [
            available_chunks[provision_id]
            for provision_id in claim.get("evidence_chunk_ids", [])
            if provision_id in available_chunks
        ]
        verified.append(verify_claim(claim, evidence_chunks))
    return {"verified_claims": verified}


def decision_node(state: RAGState) -> dict:
    verified = state.get("verified_claims", [])
    if not verified:
        return {"decision": "refusal"}

    statuses = [claim.get("status") for claim in verified]
    if all(status == "supported" for status in statuses):
        decision = "full_answer"
    elif any(
        status in {"supported", "partially_supported"} for status in statuses
    ):
        decision = "partial_answer"
    else:
        decision = "refusal"
    return {"decision": decision}
