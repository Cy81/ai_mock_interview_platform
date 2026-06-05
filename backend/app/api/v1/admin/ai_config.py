from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_config import AIModelConfigRead, AIModelConfigUpdate, AIModelTestResult
from app.services import ai_config_service


router = APIRouter(
    prefix="/ai/config",
    tags=["后台 - AI 配置"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=AIModelConfigRead, summary="获取当前活动大模型配置")
def get_ai_config(db: Session = Depends(get_db)) -> AIModelConfigRead:
    return ai_config_service.get_config(db)


@router.put("", response_model=AIModelConfigRead, summary="保存当前活动大模型配置")
def update_ai_config(
    payload: AIModelConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AIModelConfigRead:
    return ai_config_service.upsert_config(db, payload)


@router.post("/test", response_model=AIModelTestResult, summary="测试当前活动大模型配置")
def test_ai_config(db: Session = Depends(get_db)) -> AIModelTestResult:
    return ai_config_service.test_active_config(db)
