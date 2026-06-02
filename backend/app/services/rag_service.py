"""RAG 服务：双知识库（题库 / 知识库）

设计要点：
- 文档 - 切片两级模型：文档存原文/状态，切片承载向量；
- 写：用 RecursiveCharacterTextSplitter + content_hash 去重；
- 读：在 PostgreSQL 上用 pgvector 的 `<=>` 余弦距离 + HNSW 索引，
       走 SQL 层 ORDER BY ... LIMIT k，禁止 Python 全表扫描；
- SQLite（离线 / 测试）：自动降级为 Python 余弦相似度排序；
- 支持 metadata 过滤（rag_type / is_active / 作者 / 难度等）。
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Sequence

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DomainError, NotFoundError
from app.models.rag import IndexStatus, RagChunk, RagDocument, RagType
from app.services.embedding_provider import cosine_similarity, get_embedding_provider


logger = structlog.get_logger("rag")


# =====================================================================
# 数据结构
# =====================================================================


@dataclass
class RetrievalHit:
    chunk_id: int
    document_id: int
    title: str
    content: str
    score: float
    rag_type: str
    metadata: dict[str, Any]

    def to_context(self) -> dict[str, Any]:
        """给 LLM 当上下文用的最小投影。"""
        return {
            "id": self.chunk_id,
            "title": self.title,
            "content": self.content,
            "score": round(self.score, 4),
        }


# =====================================================================
# 工具
# =====================================================================


def _normalize_rag_type(value: str | RagType) -> RagType:
    if isinstance(value, RagType):
        return value
    try:
        return RagType(value)
    except ValueError:
        raise DomainError(
            "RAG 类型仅支持 question_bank 或 knowledge_base", status_code=422
        ) from None


def split_text(text: str) -> list[str]:
    """RecursiveCharacterTextSplitter，对中文友好的分隔符列表。"""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "；", "！", "？", "，", " ", ""],
            length_function=len,
        )
        chunks = [c.strip() for c in splitter.split_text(text) if c.strip()]
        if chunks:
            return chunks
    except Exception:  # pragma: no cover
        logger.warning("text_splitter_fallback")
    # 降级：按 chunk_size 滑窗
    step = max(1, settings.RAG_CHUNK_SIZE - settings.RAG_CHUNK_OVERLAP)
    return [
        text[i : i + settings.RAG_CHUNK_SIZE]
        for i in range(0, len(text), step)
    ]


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# =====================================================================
# 写入：文档 -> 切片 -> 向量化
# =====================================================================


def upsert_document(
    db: Session,
    *,
    rag_type: str | RagType,
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    source_uri: str | None = None,
    mime_type: str | None = None,
) -> RagDocument:
    """新建或更新文档，并同步触发切片向量化。

    幂等策略：(rag_type, content_hash) 命中则直接返回旧文档。
    """
    rt = _normalize_rag_type(rag_type)
    clean_title = title.strip()
    clean_content = content.strip()
    if not clean_title:
        raise DomainError("RAG 文档标题不能为空")
    if not clean_content:
        raise DomainError("RAG 文档内容不能为空")
    digest = _hash(clean_content)

    existing = db.scalar(
        select(RagDocument).where(
            and_(RagDocument.rag_type == rt, RagDocument.content_hash == digest)
        )
    )
    if existing:
        logger.info("rag_document_dedupe", document_id=existing.id, title=clean_title[:40])
        return existing

    document = RagDocument(
        rag_type=rt,
        title=clean_title[:255],
        raw_content=clean_content,
        content_hash=digest,
        source_uri=source_uri,
        mime_type=mime_type,
        extra_meta=metadata or {},
        index_status=IndexStatus.PENDING,
    )
    db.add(document)
    db.flush()
    _index_document(db, document)
    db.commit()
    db.refresh(document)
    logger.info(
        "rag_document_indexed",
        document_id=document.id,
        chunk_count=document.chunk_count,
        rag_type=rt.value,
    )
    return document


def reindex_document(db: Session, document_id: int) -> RagDocument:
    """重新切分并重新向量化整个文档。"""
    document = db.get(RagDocument, document_id)
    if not document:
        raise NotFoundError("RAG 文档不存在")
    if not document.raw_content:
        raise DomainError("文档原文为空，无法重新索引", status_code=409)

    db.execute(
        RagChunk.__table__.delete().where(RagChunk.document_id == document_id)
    )
    document.index_status = IndexStatus.PENDING
    document.chunk_count = 0
    document.last_error = None
    db.flush()
    _index_document(db, document)
    db.commit()
    db.refresh(document)
    return document


def _index_document(db: Session, document: RagDocument) -> None:
    """切分 + 调用 embedding 模型 + 入库（事务由调用方控制）。"""
    document.index_status = IndexStatus.INDEXING
    db.flush()
    try:
        pieces = split_text(document.raw_content or "")
        if not pieces:
            raise DomainError("切分结果为空，请检查文档内容")
        provider = get_embedding_provider()
        start = time.perf_counter()
        vectors = provider.embed(pieces)
        duration_ms = (time.perf_counter() - start) * 1000
        chunks = [
            RagChunk(
                document_id=document.id,
                rag_type=document.rag_type,
                chunk_index=i,
                content=piece,
                content_hash=_hash(piece),
                token_count=max(1, len(piece) // 2),  # 粗估
                embedding=vec,
                extra_meta={"title": document.title},
            )
            for i, (piece, vec) in enumerate(zip(pieces, vectors))
        ]
        db.add_all(chunks)
        document.chunk_count = len(chunks)
        document.total_tokens = sum(c.token_count for c in chunks)
        document.index_status = IndexStatus.READY
        logger.info(
            "rag_index_done",
            document_id=document.id,
            chunks=len(chunks),
            embedding_ms=round(duration_ms, 2),
        )
    except Exception as exc:
        document.index_status = IndexStatus.FAILED
        document.last_error = str(exc)[:1000]
        logger.exception("rag_index_failed", document_id=document.id)
        raise


# =====================================================================
# 读：向量检索
# =====================================================================


def search(
    db: Session,
    rag_type: str | RagType,
    query: str,
    *,
    top_k: int | None = None,
    metadata_filter: dict[str, Any] | None = None,
) -> list[RetrievalHit]:
    """语义检索 top_k 切片，返回 RetrievalHit 列表。"""
    rt = _normalize_rag_type(rag_type)
    clean_query = query.strip()
    if not clean_query:
        raise DomainError("RAG 检索问题不能为空")
    limit = max(1, min(top_k or settings.RAG_TOP_K, 20))

    query_vector = get_embedding_provider().embed_query(clean_query)

    if settings.is_postgres:
        return _search_pgvector(db, rt, query_vector, limit, metadata_filter)
    return _search_python(db, rt, query_vector, limit, metadata_filter)


def _search_pgvector(
    db: Session,
    rag_type: RagType,
    query_vector: Sequence[float],
    limit: int,
    metadata_filter: dict[str, Any] | None,
) -> list[RetrievalHit]:
    # `cosine_distance` 由 pgvector 的 SQLAlchemy 类型提供；distance 越小越相近
    distance = RagChunk.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(
            RagChunk.id,
            RagChunk.document_id,
            RagChunk.content,
            RagChunk.rag_type,
            RagChunk.extra_meta,
            RagDocument.title,
            distance,
        )
        .join(RagDocument, RagDocument.id == RagChunk.document_id)
        .where(
            RagChunk.rag_type == rag_type,
            RagChunk.is_active.is_(True),
            RagDocument.is_active.is_(True),
        )
    )
    if metadata_filter:
        for key, value in metadata_filter.items():
            stmt = stmt.where(RagChunk.extra_meta[key].astext == str(value))
    stmt = stmt.order_by(distance).limit(limit)

    rows = db.execute(stmt).all()
    return [
        RetrievalHit(
            chunk_id=row.id,
            document_id=row.document_id,
            title=row.title,
            content=row.content,
            score=float(1 - row.distance),  # 转回相似度
            rag_type=row.rag_type.value if hasattr(row.rag_type, "value") else str(row.rag_type),
            metadata=row.extra_meta or {},
        )
        for row in rows
    ]


def _search_python(
    db: Session,
    rag_type: RagType,
    query_vector: Sequence[float],
    limit: int,
    metadata_filter: dict[str, Any] | None,
) -> list[RetrievalHit]:
    """SQLite 等无 pgvector 环境的降级路径。"""
    stmt = (
        select(RagChunk, RagDocument.title)
        .join(RagDocument, RagDocument.id == RagChunk.document_id)
        .where(
            RagChunk.rag_type == rag_type,
            RagChunk.is_active.is_(True),
            RagDocument.is_active.is_(True),
        )
    )
    rows = db.execute(stmt).all()
    if metadata_filter:
        rows = [
            r for r in rows
            if all(str((r[0].extra_meta or {}).get(k)) == str(v) for k, v in metadata_filter.items())
        ]
    scored = [
        RetrievalHit(
            chunk_id=row[0].id,
            document_id=row[0].document_id,
            title=row[1],
            content=row[0].content,
            score=cosine_similarity(query_vector, row[0].embedding),
            rag_type=row[0].rag_type.value if hasattr(row[0].rag_type, "value") else str(row[0].rag_type),
            metadata=row[0].extra_meta or {},
        )
        for row in rows
    ]
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:limit]


# =====================================================================
# 后台管理辅助
# =====================================================================


def list_documents(
    db: Session,
    *,
    rag_type: str | RagType | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[RagDocument], int]:
    stmt = select(RagDocument)
    count_stmt = select(func.count(RagDocument.id))
    if rag_type:
        rt = _normalize_rag_type(rag_type)
        stmt = stmt.where(RagDocument.rag_type == rt)
        count_stmt = count_stmt.where(RagDocument.rag_type == rt)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(RagDocument.title.ilike(like))
        count_stmt = count_stmt.where(RagDocument.title.ilike(like))
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(RagDocument.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return items, total


def get_document(db: Session, document_id: int) -> RagDocument:
    document = db.get(RagDocument, document_id)
    if not document:
        raise NotFoundError("RAG 文档不存在")
    return document


def delete_document(db: Session, document_id: int) -> None:
    document = get_document(db, document_id)
    db.delete(document)
    db.commit()


def toggle_document(db: Session, document_id: int, *, is_active: bool) -> RagDocument:
    document = get_document(db, document_id)
    document.is_active = is_active
    db.commit()
    db.refresh(document)
    return document
