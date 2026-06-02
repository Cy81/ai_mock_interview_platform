"""管理员侧 Schema：用户管理统计、岗位/题库后台 CRUD 视图。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.user import UserRole


class AdminUserRead(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    is_email_verified: bool
    last_login_at: datetime | None = None
    created_at: datetime
    failed_login_attempts: int

    model_config = {"from_attributes": True}


class AdminUserToggle(BaseModel):
    is_active: bool


class AdminInterviewBrief(BaseModel):
    id: int
    user_id: int
    job_code: str
    job_title: str
    status: str
    overall_score: float | None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserStats(BaseModel):
    total_users: int
    active_users: int
    admins: int
    new_today: int


class InterviewStats(BaseModel):
    total: int
    completed: int
    in_progress: int
    failed: int
    average_score: float | None


class RagStats(BaseModel):
    rag_type: str
    documents: int
    chunks: int
    tokens: int
