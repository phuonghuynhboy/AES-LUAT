"""Kiểu dữ liệu state được truyền giữa các node LangGraph."""

from typing import TypedDict


class RAGState(TypedDict):
    question: str
    as_of: str | None
    retrieved: list[dict]
    claims: list[dict]
    verified_claims: list[dict]
    decision: str
    answer: str
    warnings: list[str]
