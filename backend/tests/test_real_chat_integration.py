from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.retrieval.corpus_loader import load_chunks
from backend.app.retrieval.retrieval_config import CONFIG

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RAG_INTEGRATION") != "1",
    reason="Set RUN_RAG_INTEGRATION=1 to call the real Gemini-backed RAG pipeline.",
)

FULL_QUERY = (
    "Theo Luật số 57/2024/QH15, công ty mẹ và công ty con trong tập đoàn kinh tế "
    "nhà nước có được tham dự gói thầu của nhau không?"
)
PARTIAL_QUERY = (
    f"{FULL_QUERY} Đồng thời, mức xử phạt hành chính nếu các công ty này vi phạm "
    "quy định về đấu thầu là bao nhiêu?"
)
REFUSAL_QUERY = (
    "Mức xử phạt hành chính đối với hành vi chậm đóng bảo hiểm xã hội bắt buộc "
    "của người sử dụng lao động được quy định như thế nào theo pháp luật hiện hành?"
)


def _assert_citation_invariant(payload: dict) -> None:
    source_ids = {source["provision_id"] for source in payload["sources"]}
    for claim in payload["claims"]:
        if claim.get("status") in {"supported", "partially_supported"}:
            assert set(claim.get("evidence_chunk_ids") or []) <= source_ids


def _assert_source_text_matches_corpus(payload: dict) -> None:
    corpus = {
        chunk["provision_id"]: chunk["text"]
        for chunk in load_chunks(CONFIG["chunks_path"])
    }
    for source in payload["sources"]:
        assert source["text"] == corpus[source["provision_id"]]


@pytest.mark.parametrize(
    ("query", "expected_status"),
    [
        (FULL_QUERY, "full_answer"),
        (PARTIAL_QUERY, "partial_answer"),
        (REFUSAL_QUERY, "refusal"),
    ],
)
def test_real_chat_end_to_end(query: str, expected_status: str):
    response = TestClient(app).post("/api/chat", json={"question": query})
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == expected_status
    _assert_citation_invariant(payload)
    _assert_source_text_matches_corpus(payload)

    if expected_status == "full_answer":
        assert any(
            source["provision_id"] == "57-2024-QH15#amd4k3pc.qt6.k4a"
            for source in payload["sources"]
        )
    elif expected_status == "partial_answer":
        assert payload["sources"]
        assert any(claim.get("status") == "unsupported" for claim in payload["claims"])
    else:
        assert payload["sources"] == []
