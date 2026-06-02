"""异步索引任务：RAG 文档向量化与重建。"""
from __future__ import annotations

import structlog

from app.db.session import session_scope
from app.services import rag_service
from app.tasks.celery_app import celery_app


logger = structlog.get_logger("task.indexing")


@celery_app.task(
    name="app.tasks.indexing.index_rag_document",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    soft_time_limit=180,
    acks_late=True,
)
def index_rag_document(
    self,
    rag_type: str,
    title: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    """异步入库：上传后台调用，用户立刻拿到 task_id 轮询。"""
    logger.info(
        "indexing_start",
        task_id=self.request.id,
        rag_type=rag_type,
        title=title[:60],
    )
    with session_scope() as db:
        document = rag_service.upsert_document(
            db,
            rag_type=rag_type,
            title=title,
            content=content,
            metadata=metadata or {},
        )
        return {
            "task_id": self.request.id,
            "document_id": document.id,
            "chunks": document.chunk_count,
            "status": document.index_status.value,
        }


@celery_app.task(
    name="app.tasks.indexing.reindex_document",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=300,
    acks_late=True,
)
def reindex_document(self, document_id: int) -> dict:
    logger.info("reindex_start", task_id=self.request.id, document_id=document_id)
    with session_scope() as db:
        document = rag_service.reindex_document(db, document_id)
        return {
            "task_id": self.request.id,
            "document_id": document.id,
            "chunks": document.chunk_count,
            "status": document.index_status.value,
        }
