from __future__ import annotations

import logging

from backend.app.generation import rag_graph


class FakeGraph:
    def __init__(self, state: dict):
        self.state = state

    def invoke(self, _input: dict) -> dict:
        return self.state


def _retrieved(provision_id: str, text: str) -> dict:
    return {
        "provision_id": provision_id,
        "provision_key": f"KEY#{provision_id}",
        "breadcrumb": "Văn bản kiểm thử > Điều 1",
        "doc_id": "DOC-1",
        "text": text,
        "valid_from": "2025-01-15",
        "valid_to": None,
        "temporal_warning": None,
        "rrf_score": 0.03,
        "sources": ["bm25", "dense"],
    }


def test_answer_question_preserves_retrieved_text_and_citation_invariant(monkeypatch):
    used_text = "The exact value carried by the retrieved chunk."
    state = {
        "decision": "full_answer",
        "answer": "Answer",
        "verified_claims": [
            {
                "claim_id": "claim_1",
                "text": "Claim",
                "status": "supported",
                "evidence_chunk_ids": ["SOURCE_A"],
            }
        ],
        "retrieved": [
            _retrieved("SOURCE_A", used_text),
            _retrieved("UNUSED_SOURCE", "Unused retrieval candidate"),
        ],
        "warnings": [],
    }
    monkeypatch.setattr(rag_graph, "_compiled_graph", FakeGraph(state))

    response = rag_graph.answer_question("A question")

    assert [source["provision_id"] for source in response["sources"]] == ["SOURCE_A"]
    assert response["sources"][0]["text"] == used_text
    assert len(response["retrieved_sources"]) == 2
    evidence_ids = set(response["claims"][0]["evidence_chunk_ids"])
    source_ids = {source["provision_id"] for source in response["sources"]}
    assert evidence_ids <= source_ids


def test_refusal_keeps_candidates_out_of_verified_sources(monkeypatch):
    state = {
        "decision": "refusal",
        "answer": "Insufficient evidence",
        "verified_claims": [
            {
                "claim_id": "claim_1",
                "text": "Unsupported",
                "status": "unsupported",
                "evidence_chunk_ids": ["SOURCE_A"],
            }
        ],
        "retrieved": [_retrieved("SOURCE_A", "Candidate")],
        "warnings": ["INSUFFICIENT_LEGAL_EVIDENCE"],
    }
    monkeypatch.setattr(rag_graph, "_compiled_graph", FakeGraph(state))

    response = rag_graph.answer_question("A question")

    assert response["sources"] == []
    assert len(response["retrieved_sources"]) == 1


def test_duplicate_retrieved_ids_keep_first_and_log_warning(caplog):
    first = _retrieved("SOURCE_A", "first")
    second = _retrieved("SOURCE_A", "second")
    claims = [{"status": "supported", "evidence_chunk_ids": ["SOURCE_A"]}]

    with caplog.at_level(logging.WARNING):
        sources, retrieved_sources = rag_graph.build_response_sources(
            claims,
            [first, second],
        )

    assert len(sources) == 1
    assert len(retrieved_sources) == 1
    assert sources[0]["text"] == "first"
    assert "Duplicate retrieved source provision_id=SOURCE_A" in caplog.text


def test_multiple_evidence_ids_return_multiple_sources_in_claim_order():
    claims = [
        {
            "status": "supported",
            "evidence_chunk_ids": ["SOURCE_B", "SOURCE_A"],
        }
    ]
    sources, _ = rag_graph.build_response_sources(
        claims,
        [_retrieved("SOURCE_A", "A"), _retrieved("SOURCE_B", "B")],
    )

    assert [source["provision_id"] for source in sources] == ["SOURCE_B", "SOURCE_A"]
