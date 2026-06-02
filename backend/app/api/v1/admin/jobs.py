"""管理员：岗位 CRUD + 启用切换。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Message
from app.schemas.job import JobDirectionCreate, JobDirectionRead, JobDirectionUpdate
from app.services import admin_service


router = APIRouter(prefix="/jobs", tags=["[Admin] 岗位"])


@router.get("", response_model=list[JobDirectionRead], summary="岗位列表（含已下线）")
def list_jobs(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return admin_service.list_jobs(db)


@router.post(
    "",
    response_model=JobDirectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="新建岗位",
)
def create_job(
    payload: JobDirectionCreate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_service.create_job(db, payload.model_dump())


@router.put("/{job_id}", response_model=JobDirectionRead, summary="更新岗位")
def update_job(
    job_id: int,
    payload: JobDirectionUpdate,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_service.update_job(
        db, job_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/{job_id}", response_model=Message, summary="删除岗位")
def delete_job(
    job_id: int,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    admin_service.delete_job(db, job_id)
    return Message(message="已删除")


@router.patch(
    "/{job_id}/toggle",
    response_model=JobDirectionRead,
    summary="启用 / 禁用岗位",
)
def toggle_job(
    job_id: int,
    is_active: bool,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_service.toggle_job(db, job_id, is_active=is_active)
