from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.schemas.ai_usage import AIFailureOverview
from app.services import ai_usage_service


router = APIRouter(
    prefix="/ai/failures",
    tags=["后台 - AI 异常监控"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/overview", response_model=AIFailureOverview, summary="查看 AI 失败与异常概览")
def get_ai_failure_overview(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AIFailureOverview:
    return ai_usage_service.get_failure_overview(db, days=days, limit=limit)
