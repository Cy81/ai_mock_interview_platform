"""岗位方向模型：支持后台启停、排序、薪资区间、岗位画像。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class JobDirection(TimestampMixin, Base):
    __tablename__ = "job_directions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    nice_to_have_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    competency_model: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    seniority: Mapped[str] = mapped_column(String(50), default="junior-mid", server_default="junior-mid", nullable=False)
    salary_range: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False, index=True)
