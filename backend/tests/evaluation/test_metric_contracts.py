from __future__ import annotations

import pytest

from backend.evaluation.metrics import evaluate_response


pytestmark = pytest.mark.evaluation


CORPUS = {
    "DOC_A#d1": {"provision_id": "DOC_A#d1", "text": "Nội dung điều luật A."},
}


def _case(category: str = "single_hop") -> dict:
    return {
        "id": "CASE_001",
        "category": category,
        "question": "Câu hỏi kiểm thử",
        "expected_statuses": ["refusal" if category == "out_of_scope" else "partial_answer"],
        "gold_answer": "Nội dung đúng",
        "gold_citation_groups": [] if category == "out_of_scope" else [["DOC_A#d1"]],
        "answer_rubric": {
            "required_facts": []
            if category == "out_of_scope"
            else [{"fact_id": "fact", "any_of": ["nội dung đúng"], "patterns": []}],
            "forbidden_facts": [],
            "minimum_fact_coverage": 1.0,
        },
    }


def test_partial_answer_cites_supported_claim_only():
    response = {
        "status": "partial_answer",
        "answer": "Nội dung đúng; phần còn lại chưa đủ căn cứ.",
        "claims": [
            {
                "claim_id": "supported",
                "status": "supported",
                "evidence_chunk_ids": ["DOC_A#d1"],
            },
            {
                "claim_id": "unsupported",
                "status": "unsupported",
                "evidence_chunk_ids": [],
            },
        ],
        "sources": [CORPUS["DOC_A#d1"]],
        "retrieved_sources": [],
        "warnings": [],
    }

    result = evaluate_response(_case(), response, CORPUS)

    assert result["citation_exact"] is True
    assert result["claim_citation_contract_correct"] is True
    assert result["status_semantics_correct"] is True


def test_unsupported_claim_must_not_have_citation():
    response = {
        "status": "partial_answer",
        "answer": "Nội dung đúng; phần còn lại chưa đủ căn cứ.",
        "claims": [
            {
                "claim_id": "supported",
                "status": "supported",
                "evidence_chunk_ids": ["DOC_A#d1"],
            },
            {
                "claim_id": "unsupported",
                "status": "unsupported",
                "evidence_chunk_ids": ["DOC_A#d1"],
            },
        ],
        "sources": [CORPUS["DOC_A#d1"]],
        "retrieved_sources": [],
        "warnings": [],
    }

    result = evaluate_response(_case(), response, CORPUS)

    assert result["unsupported_claims_with_evidence"] == ["unsupported"]
    assert result["claim_citation_contract_correct"] is False
    assert result["hallucination_present"] is True


def test_refusal_has_zero_citations_even_when_retrieval_found_sources():
    response = {
        "status": "refusal",
        "answer": "Chưa có đủ căn cứ pháp lý để trả lời.",
        "claims": [],
        "sources": [],
        "retrieved_sources": [CORPUS["DOC_A#d1"]],
        "warnings": [],
    }

    result = evaluate_response(_case("out_of_scope"), response, CORPUS)

    assert result["predicted_citation_ids"] == []
    assert result["out_of_scope_correct"] is True
    assert result["hallucination_present"] is False


def test_citation_mapping_rejects_provision_key_in_place_of_provision_id():
    response = {
        "status": "partial_answer",
        "answer": "Nội dung đúng; phần còn lại chưa đủ căn cứ.",
        "claims": [
            {
                "claim_id": "supported",
                "status": "supported",
                "evidence_chunk_ids": ["PROVISION_KEY_A"],
            },
            {
                "claim_id": "unsupported",
                "status": "unsupported",
                "evidence_chunk_ids": [],
            },
        ],
        "sources": [CORPUS["DOC_A#d1"]],
        "retrieved_sources": [],
        "warnings": [],
    }

    result = evaluate_response(_case(), response, CORPUS)

    assert result["citation_invariant_violations"] == ["PROVISION_KEY_A"]
    assert result["citation_exact"] is False
    assert result["hallucination_present"] is True
