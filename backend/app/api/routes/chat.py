"""Thin HTTP adapter around the existing legal RAG graph."""

from fastapi import APIRouter

from ...generation.rag_graph import answer_question
from ..schemas.request import ChatRequest
from ..schemas.response import ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Run the existing RAG entry point without duplicating pipeline logic."""
    return ChatResponse.model_validate(answer_question(request.question))
