"""客户端：评分报告路由 (/api/v1/reports/*)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError
from app.db.session import get_db
from app.models.interview import InterviewStatus
from app.models.user import User
from app.schemas.interview import ReportRead
from app.services import interview_service


router = APIRouter(prefix="/reports", tags=["评分报告"])


@router.get(
    "/{interview_id}",
    response_model=ReportRead,
    summary="获取指定面试的评分报告",
)
def get_report(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = interview_service.get_interview(db, user, interview_id)
    if interview.status != InterviewStatus.COMPLETED:
        raise ConflictError("面试尚未完成，报告未生成")
    return ReportRead(
        interview_id=interview.id,
        job_title=interview.job_title,
        status=interview.status,
        overall_score=interview.overall_score,
        report=interview.score_report,
        completed_at=interview.completed_at,
    )
