"""客户端：岗位与岗位匹配 Agent 路由 (/api/v1/jobs/*)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.job import JobDirection
from app.models.resume import Resume
from app.models.user import User
from app.schemas.job import (
    JobDirectionRead,
    JobRecommendation,
    JobRecommendationRequest,
    JobRecommendationResponse,
)
from app.services import job_agent


router = APIRouter(prefix="/jobs", tags=["岗位"])


@router.get("", response_model=list[JobDirectionRead], summary="可选择的岗位列表")
def list_jobs(db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(JobDirection)
            .where(JobDirection.is_active.is_(True))
            .order_by(JobDirection.sort_order, JobDirection.id)
        ).all()
    )


@router.post(
    "/recommend",
    response_model=JobRecommendationResponse,
    summary="基于简历推荐岗位（岗位匹配 Agent）",
)
def recommend(
    payload: JobRecommendationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = db.get(Resume, payload.resume_id)
    if not resume or resume.user_id != user.id:
        raise NotFoundError("简历不存在或无权限访问")
    items = job_agent.recommend_jobs(db, resume, top_n=payload.top_n)
    return JobRecommendationResponse(
        resume_id=resume.id,
        recommendations=[JobRecommendation(**i) for i in items],
    )
