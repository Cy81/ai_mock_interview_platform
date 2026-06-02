"""RAG 文档与切片：源文件作为父表，chunk 作为子表，向量字段独立索引。

为何拆分：
- 一个原始文档（PDF / Markdown）会被切成 N 个 chunk，每个 chunk 才是检索粒度；
- 拆分后支持：按文档启停、重新索引、批量删除、Token 计费；
- chunk 表带 content_hash，可做幂等去重；embedding 字段单独建 HNSW 索引。
"""
from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, TimestampMixin


# pgvector 在生产用真实向量类型；SQLite 测试环境降级为 JSON。
try:  # pragma: no cover - 简单兼容
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:  # pragma: no cover
    from sqlalchemy.types import JSON as _JSON

    class Vector(_JSON):  # type: ignore[no-redef]
        def __init__(self, dimensions: int | None = None) -> None:
            super().__init__()
            self.dimensions = dimensions


class RagType(str, enum.Enum):
    QUESTION_BANK = "question_bank"
    KNOWLEDGE_BASE = "knowledge_base"


class IndexStatus(str, enum.Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class RagDocument(TimestampMixin, Base):
    """原始文档，作为后台 CRUD 的主体。"""

    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    rag_type: Mapped[RagType] = mapped_column(
        Enum(RagType, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False, index=True
    )
    index_status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus, native_enum=False, length=20),
        default=IndexStatus.PENDING,
        server_default=IndexStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks = relationship(
        "RagChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="RagChunk.chunk_index",
    )


class RagChunk(TimestampMixin, Base):
    """切片：检索的最小单元，带 embedding 与 metadata。"""

    __tablename__ = "rag_chunks"
    __table_args__ = (
        Index("ix_rag_chunks_doc_chunk", "document_id", "chunk_index", unique=True),
        Index("ix_rag_chunks_type_active", "rag_type", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rag_type: Mapped[RagType] = mapped_column(
        Enum(RagType, native_enum=False, length=20),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBEDDING_DIMENSIONS), nullable=False)
    extra_meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    document = relationship("RagDocument", back_populates="chunks")
