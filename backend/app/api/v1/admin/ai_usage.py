from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.ai_usage import AIUsageStatus
from app.schemas.ai_usage import AIUsageLogRead, AIUsageSummary
from app.schemas.common import Page
from app.services import ai_usage_service


router = APIRouter(
    prefix="/ai/usage",
    tags=["后台 - AI 用量"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=Page[AIUsageLogRead], summary="分页查询大模型调用日志")
def list_ai_usage(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    feature: str | None = Query(default=None, max_length=80),
    status: AIUsageStatus | None = None,
    db: Session = Depends(get_db),
) -> Page[AIUsageLogRead]:
    items, total = ai_usage_service.list_usage_logs(
        db,
        page=page,
        page_size=page_size,
        feature=feature,
        status=status,
    )
    return Page.of(ai_usage_service.to_read_items(items), total, page, page_size)


@router.get("/summary", response_model=AIUsageSummary, summary="查看大模型用量汇总")
def get_ai_usage_summary(
    days: int = Query(default=7, ge=1, le=365),
    db: Session = Depends(get_db),
) -> AIUsageSummary:
    return ai_usage_service.summarize_usage(db, days=days)
