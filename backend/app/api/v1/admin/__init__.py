"""admin 子路由聚合：/api/v1/admin/* 全部由超级 / 管理员可见。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin.ai_config import router as ai_config_router
from app.api.v1.admin.ai_usage import router as ai_usage_router
from app.api.v1.admin.jobs import router as jobs_router
from app.api.v1.admin.rag import router as rag_router
from app.api.v1.admin.system import router as system_router


admin_v1_router = APIRouter()
admin_v1_router.include_router(system_router)
admin_v1_router.include_router(ai_config_router)
admin_v1_router.include_router(ai_usage_router)
admin_v1_router.include_router(jobs_router)
admin_v1_router.include_router(rag_router)
