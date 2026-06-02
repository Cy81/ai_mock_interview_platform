"""管理员：用户管理 + 后台仪表盘统计。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminInterviewBrief,
    AdminUserRead,
    AdminUserToggle,
    InterviewStats,
    RagStats,
    UserStats,
)
from app.schemas.common import Page
from app.services import admin_service


router = APIRouter(tags=["[Admin] 系统"])


# ---------- 用户 ----------


@router.get("/users", response_model=Page[AdminUserRead], summary="分页查询用户")
def list_users(
    keyword: str | None = None,
    role: UserRole | None = None,
    page: int = 1,
    page_size: int = 20,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    items, total = admin_service.list_users(
        db, keyword=keyword, role=role, page=page, page_size=page_size
    )
    return Page[AdminUserRead].of(
        [AdminUserRead.model_validate(u) for u in items], total, page, page_size
    )


@router.put(
    "/users/{user_id}/toggle-active",
    response_model=AdminUserRead,
    summary="启用 / 禁用用户",
)
def toggle_user(
    user_id: int,
    payload: AdminUserToggle,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = admin_service.toggle_user_active(db, user_id, is_active=payload.is_active)
    return user


@router.get("/users/stats", response_model=UserStats, summary="用户统计")
def user_stats(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return admin_service.user_stats(db)


# ---------- 面试 ----------


@router.get(
    "/interviews",
    response_model=Page[AdminInterviewBrief],
    summary="所有面试列表",
)
def list_interviews(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.models.interview import InterviewStatus

    enum_status = None
    if status:
        try:
            enum_status = InterviewStatus(status)
        except ValueError:
            from app.core.exceptions import DomainError

            raise DomainError(f"非法 status：{status}", status_code=422)
    items, total = admin_service.list_all_interviews(
        db, status=enum_status, page=page, page_size=page_size
    )
    return Page[AdminInterviewBrief].of(
        [AdminInterviewBrief.model_validate(i) for i in items], total, page, page_size
    )


@router.get("/interviews/stats", response_model=InterviewStats, summary="面试统计")
def interview_stats(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return admin_service.interview_stats(db)


# ---------- RAG 总览 ----------


@router.get("/rag/stats", response_model=list[RagStats], summary="RAG 文档与切片统计")
def rag_stats(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return admin_service.rag_stats(db)
