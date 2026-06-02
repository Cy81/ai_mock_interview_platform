"""RAG 文档 / 检索 Schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.rag import IndexStatus, RagType


RagTypeLiteral = Literal["question_bank", "knowledge_base"]


class RagDocumentCreate(BaseModel):
    rag_type: RagTypeLiteral
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class RagDocumentRead(BaseModel):
    id: int
    rag_type: RagType
    title: str
    source_uri: str | None = None
    mime_type: str | None = None
    is_active: bool
    index_status: IndexStatus
    chunk_count: int
    total_tokens: int
    last_error: str | None = None
    extra_meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RagSearchRequest(BaseModel):
    rag_type: RagTypeLiteral
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    metadata_filter: dict[str, Any] | None = None


class RagSearchHit(BaseModel):
    chunk_id: int
    document_id: int
    title: str
    content: str
    score: float
    rag_type: str
    metadata: dict[str, Any]
