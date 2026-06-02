"""聚合两个端的根 router：

- `client_router`：/api/v1/* — 普通用户使用；
- `admin_router`：/api/v1/admin/* — 管理员后台。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin import admin_v1_router
from app.api.v1.auth import router as auth_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.rag import router as rag_router
from app.api.v1.reports import router as reports_router
from app.api.v1.resumes import router as resumes_router


client_router = APIRouter()
client_router.include_router(auth_router)
client_router.include_router(resumes_router)
client_router.include_router(jobs_router)
client_router.include_router(interviews_router)
client_router.include_router(reports_router)
client_router.include_router(rag_router)


admin_router = APIRouter()
admin_router.include_router(admin_v1_router)
