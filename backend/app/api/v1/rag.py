"""客户端：RAG 检索路由（只读）。

注意：客户端仅可检索，不能写。后台 admin 才能写。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.rag import RagSearchHit, RagSearchRequest
from app.services import rag_service


router = APIRouter(prefix="/rag", tags=["RAG 检索"])


@router.post(
    "/search",
    response_model=list[RagSearchHit],
    summary="向量检索：题库 / 知识库",
)
def search(
    payload: RagSearchRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hits = rag_service.search(
        db,
        rag_type=payload.rag_type,
        query=payload.query,
        top_k=payload.top_k,
        metadata_filter=payload.metadata_filter,
    )
    return [
        RagSearchHit(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            title=h.title,
            content=h.content,
            score=h.score,
            rag_type=h.rag_type,
            metadata=h.metadata,
        )
        for h in hits
    ]
