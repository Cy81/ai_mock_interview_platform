from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AIRuntime(str, enum.Enum):
    MOCK = "mock"
    DEEPSEEK = "deepseek"


class AIProvider(str, enum.Enum):
    MOCK = "mock"
    DEEPSEEK = "deepseek"


class AIModelConfig(TimestampMixin, Base):
    __tablename__ = "ai_model_configs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
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
    base_url: Mapped[str] = mapped_column(String(512), default="", server_default="", nullable=False)
    api_key: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.2, server_default="0.2", nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, server_default="2048", nullable=False)
    timeout: Mapped[float] = mapped_column(Float, default=60.0, server_default="60", nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_test_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)
