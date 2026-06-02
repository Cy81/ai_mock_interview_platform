"""管理员服务：用户/岗位/题库统计与 CRUD 辅助。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.interview import Interview, InterviewStatus
from app.models.job import JobDirection
from app.models.rag import RagChunk, RagDocument, RagType
from app.models.user import User, UserRole


# =====================================================================
# 用户管理
# =====================================================================


def list_users(
    db: Session,
    *,
    keyword: str | None = None,
    role: UserRole | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[User], int]:
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where((User.email.ilike(like)) | (User.full_name.ilike(like)))
        count_stmt = count_stmt.where((User.email.ilike(like)) | (User.full_name.ilike(like)))
    if role:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
    )
    return items, total


def toggle_user_active(db: Session, user_id: int, *, is_active: bool) -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    user.is_active = is_active
    if is_active:
        user.failed_login_attempts = 0
        user.locked_until = None
    db.commit()
    db.refresh(user)
    return user


def user_stats(db: Session) -> dict[str, Any]:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return {
        "total_users": db.scalar(select(func.count(User.id))) or 0,
        "active_users": db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0,
        "admins": db.scalar(
            select(func.count(User.id)).where(User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN]))
        ) or 0,
        "new_today": db.scalar(select(func.count(User.id)).where(User.created_at >= today)) or 0,
    }


# =====================================================================
# 岗位 CRUD
# =====================================================================


def list_jobs(db: Session) -> list[JobDirection]:
    return list(
        db.scalars(select(JobDirection).order_by(JobDirection.sort_order, JobDirection.id)).all()
    )


def get_job(db: Session, job_id: int) -> JobDirection:
    job = db.get(JobDirection, job_id)
    if not job:
        raise NotFoundError("岗位不存在")
    return job


def create_job(db: Session, payload: dict[str, Any]) -> JobDirection:
    job = JobDirection(**payload)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job_id: int, payload: dict[str, Any]) -> JobDirection:
    job = get_job(db, job_id)
    for key, value in payload.items():
        if value is not None:
            setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return job


def delete_job(db: Session, job_id: int) -> None:
    job = get_job(db, job_id)
    db.delete(job)
    db.commit()


def toggle_job(db: Session, job_id: int, *, is_active: bool) -> JobDirection:
    job = get_job(db, job_id)
    job.is_active = is_active
    db.commit()
    db.refresh(job)
    return job


# =====================================================================
# 面试统计
# =====================================================================


def list_all_interviews(
    db: Session,
    *,
    status: InterviewStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Interview], int]:
    stmt = select(Interview)
    count_stmt = select(func.count(Interview.id))
    if status:
        stmt = stmt.where(Interview.status == status)
        count_stmt = count_stmt.where(Interview.status == status)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(Interview.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
    )
    return items, total


def interview_stats(db: Session) -> dict[str, Any]:
    return {
        "total": db.scalar(select(func.count(Interview.id))) or 0,
        "completed": db.scalar(select(func.count(Interview.id)).where(Interview.status == InterviewStatus.COMPLETED)) or 0,
        "in_progress": db.scalar(select(func.count(Interview.id)).where(Interview.status == InterviewStatus.IN_PROGRESS)) or 0,
        "failed": db.scalar(select(func.count(Interview.id)).where(Interview.status == InterviewStatus.FAILED)) or 0,
        "average_score": db.scalar(select(func.avg(Interview.overall_score)).where(Interview.status == InterviewStatus.COMPLETED)),
    }


# =====================================================================
# RAG 统计
# =====================================================================


def rag_stats(db: Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rt in RagType:
        documents = db.scalar(select(func.count(RagDocument.id)).where(RagDocument.rag_type == rt)) or 0
        chunks = db.scalar(select(func.count(RagChunk.id)).where(RagChunk.rag_type == rt)) or 0
        tokens = db.scalar(select(func.coalesce(func.sum(RagChunk.token_count), 0)).where(RagChunk.rag_type == rt)) or 0
        out.append({"rag_type": rt.value, "documents": documents, "chunks": chunks, "tokens": int(tokens)})
    return out
