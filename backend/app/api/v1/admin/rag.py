"""管理员：RAG 文档管理（题库 + 知识库）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.core.exceptions import DomainError
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.rag import (
    RagDocumentCreate,
    RagDocumentRead,
    RagDocumentUpdate,
    RagSearchHit,
    RagSearchRequest,
)
from app.services import rag_service, resume_parser
from app.tasks.indexing import index_rag_document, reindex_document


router = APIRouter(prefix="/rag", tags=["[Admin] RAG"])


@router.get(
    "/documents",
    response_model=Page[RagDocumentRead],
    summary="分页查询 RAG 文档",
)
def list_documents(
    rag_type: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    items, total = rag_service.list_documents(
        db, rag_type=rag_type, keyword=keyword, page=page, page_size=page_size
    )
    return Page[RagDocumentRead].of(
        [RagDocumentRead.model_validate(item) for item in items], total, page, page_size
    )


@router.post(
    "/documents",
    response_model=RagDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="新增 RAG 文档（粘贴文本，同步索引）",
)
def create_document(
    payload: RagDocumentCreate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    document = rag_service.upsert_document(
        db,
        rag_type=payload.rag_type,
        title=payload.title,
        content=payload.content,
        metadata=payload.metadata,
    )
    return document


@router.post(
    "/documents/upload",
    summary="上传 RAG 文件，进入异步索引队列",
)
async def upload_document(
    rag_type: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    _: User = Depends(get_current_admin),
):
    content = await file.read()
    text = resume_parser.extract_text(
        content,
        mime_type=file.content_type,
        filename=file.filename,
    )
    if not text.strip():
        raise DomainError("文件内容为空", status_code=400)
    task = index_rag_document.delay(rag_type, title, text, {"filename": file.filename})
    return {"task_id": task.id, "status": "queued"}


@router.get(
    "/documents/{document_id}",
    response_model=RagDocumentRead,
    summary="获取文档详情",
)
def get_document(
    document_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return rag_service.get_document(db, document_id)


@router.put(
    "/documents/{document_id}",
    response_model=RagDocumentRead,
    summary="更新文档元信息",
)
def update_document(
    document_id: int,
    payload: RagDocumentUpdate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    document = rag_service.get_document(db, document_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "metadata":
            document.extra_meta = value
        else:
            setattr(document, key, value)
    db.commit()
    db.refresh(document)
    return document


@router.delete(
    "/documents/{document_id}",
    response_model=Message,
    summary="删除文档（级联删除 chunk）",
)
def delete_document(
    document_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rag_service.delete_document(db, document_id)
    return Message(message="已删除")


@router.patch(
    "/documents/{document_id}/toggle",
    response_model=RagDocumentRead,
    summary="启用 / 禁用文档",
)
def toggle_document(
    document_id: int,
    is_active: bool,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return rag_service.toggle_document(db, document_id, is_active=is_active)


@router.post(
    "/documents/{document_id}/reindex",
    summary="重新切分并向量化（异步）",
)
def reindex(
    document_id: int,
    _: User = Depends(get_current_admin),
):
    task = reindex_document.delay(document_id)
    return {"task_id": task.id, "status": "queued"}


@router.post(
    "/test-retrieve",
    response_model=list[RagSearchHit],
    summary="管理员检索测试",
)
def test_retrieve(
    payload: RagSearchRequest,
    _: User = Depends(get_current_admin),
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
