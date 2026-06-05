from __future__ import annotations

import enum

from sqlalchemy import Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.ai_config import AIProvider, AIRuntime


class AIUsageStatus(str, enum.Enum):
    OK = "ok"
    FAILED = "failed"


class AIUsageLog(TimestampMixin, Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (
        Index("ix_ai_usage_created_status", "created_at", "status"),
        Index("ix_ai_usage_feature_model", "feature", "model"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    feature: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    runtime: Mapped[AIRuntime] = mapped_column(
        Enum(AIRuntime, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    provider: Mapped[AIProvider] = mapped_column(
        Enum(AIProvider, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[AIUsageStatus] = mapped_column(
        Enum(AIUsageStatus, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
