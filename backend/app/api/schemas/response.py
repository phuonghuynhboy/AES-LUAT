"""Response contract shared by the RAG API and citation frontend."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChatStatus = Literal["full_answer", "partial_answer", "refusal"]
ClaimStatus = Literal["supported", "partially_supported", "unsupported"]


class LegalClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_id: str
    question_part: str | None = None
    text: str
    answerable: bool | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    status: ClaimStatus | None = None
    score: float | None = None
    reason: str | None = None


class LegalSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provision_id: str = Field(min_length=1)
    provision_key: str | None = None
    breadcrumb: str | None = None
    doc_id: str | None = None
    text: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    temporal_warning: str | None = None
    rrf_score: float | None = None
    retriever_sources: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: ChatStatus
    answer: str
    claims: list[LegalClaim] = Field(default_factory=list)
    # Verified citation sources referenced by usable claims.
    sources: list[LegalSource] = Field(default_factory=list)
    # Retrieval candidates retained only for audit/debug; never rendered as citations.
    retrieved_sources: list[LegalSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
