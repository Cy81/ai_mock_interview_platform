"""客户端：简历路由 (/api/v1/resumes/*)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.resume import Resume
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.resume import ResumeBrief, ResumeRead, ResumeTextCreate
from app.services import resume_parser


router = APIRouter(prefix="/resumes", tags=["简历"])


@router.post(
    "",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="录入文本简历（粘贴全文）",
)
def create_resume_text(
    payload: ResumeTextCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return resume_parser.create_resume_from_text(
        db,
        user,
        filename=payload.filename,
        text=payload.text,
        target_position=payload.target_position,
    )


@router.post(
    "/upload",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="上传文件简历（PDF / DOCX / TXT / Markdown）",
)
async def upload_resume(
    file: UploadFile = File(..., description="简历文件"),
    target_position: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await resume_parser.create_resume_from_upload(db, user, file, target_position)


@router.get("", response_model=Page[ResumeBrief], summary="分页查询当前用户的简历列表")
def list_my_resumes(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count(Resume.id)).where(Resume.user_id == user.id)) or 0
    items = list(
        db.scalars(
            select(Resume)
            .where(Resume.user_id == user.id)
            .order_by(Resume.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return Page[ResumeBrief].of(
        [ResumeBrief.model_validate(item) for item in items], total, page, page_size
    )


@router.get("/{resume_id}", response_model=ResumeRead, summary="获取简历详情")
def get_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id:
        raise NotFoundError("简历不存在或无权限访问")
    return resume


@router.delete("/{resume_id}", response_model=Message, summary="删除简历")
def delete_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id:
        raise NotFoundError("简历不存在或无权限访问")
    db.delete(resume)
    db.commit()
    return Message(message="已删除")
