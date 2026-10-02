from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from backend.app.api.routes import chat as chat_route
from backend.app.api.schemas.response import ChatResponse
from backend.app.main import app


def _response() -> dict:
    return {
        "status": "full_answer",
        "answer": "Structured answer",
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "Supported claim",
                "answerable": True,
                "evidence_chunk_ids": ["SOURCE_A"],
                "status": "supported",
                "score": 0.98,
            }
        ],
        "sources": [
            {
                "provision_id": "SOURCE_A",
                "provision_key": "LOGICAL_A",
                "breadcrumb": "Văn bản > Điều 1",
                "doc_id": "DOC-1",
                "text": "Retrieved source text",
                "valid_from": "2025-01-15",
                "valid_to": None,
                "retriever_sources": ["bm25", "dense"],
            }
        ],
        "retrieved_sources": [],
        "warnings": [],
    }


def test_post_chat_calls_existing_rag_entry_point(monkeypatch):
    captured: dict[str, str] = {}

    def fake_answer(question: str, as_of: str | None = None) -> dict:
        captured["question"] = question
        captured["as_of"] = as_of or ""
        return _response()

    monkeypatch.setattr(chat_route, "answer_question", fake_answer)
    response = TestClient(app).post("/api/chat", json={"question": "  Query  "})

    assert response.status_code == 200
    assert captured["question"] == "Query"
    assert captured["as_of"] == ""
    payload = response.json()
    assert payload["sources"][0]["text"] == "Retrieved source text"
    assert payload["sources"][0]["valid_to"] is None


@pytest.mark.parametrize("question", ["", "   "])
def test_post_chat_rejects_blank_question(question: str):
    response = TestClient(app).post("/api/chat", json={"question": question})
    assert response.status_code == 422

def test_post_chat_passes_explicit_as_of(monkeypatch):
    captured: dict[str, str | None] = {}

    def fake_answer(question: str, as_of: str | None = None) -> dict:
        captured.update(question=question, as_of=as_of)
        return _response()

    monkeypatch.setattr(chat_route, "answer_question", fake_answer)
    response = TestClient(app).post(
        "/api/chat",
        json={"question": "Quy định nào áp dụng?", "as_of": "2025-02-06"},
    )

    assert response.status_code == 200
    assert captured == {
        "question": "Quy định nào áp dụng?",
        "as_of": "2025-02-06",
    }

def test_response_schema_rejects_unknown_status():
    invalid = _response()
    invalid["status"] = "invented_status"
    with pytest.raises(ValidationError):
        ChatResponse.model_validate(invalid)


def test_rag_exception_returns_http_500_without_mock(monkeypatch):
    def fail(_question: str, as_of: str | None = None) -> dict:
        del as_of
        raise RuntimeError("RAG failed")

    monkeypatch.setattr(chat_route, "answer_question", fail)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/chat",
        json={"question": "Query"},
    )
    assert response.status_code == 500


def test_cors_allows_only_configured_development_origin():
    client = TestClient(app)
    allowed = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    denied = client.options(
        "/api/chat",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers
