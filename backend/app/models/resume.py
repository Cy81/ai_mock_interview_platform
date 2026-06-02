"""简历模型：补全文件元信息、版本号、解析状态。"""
from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ResumeParseStatus(str, enum.Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    target_position: Mapped[str | None] = mapped_column(String(120), nullable=True)

    parse_status: Mapped[ResumeParseStatus] = mapped_column(
        Enum(ResumeParseStatus, native_enum=False, length=20),
        default=ResumeParseStatus.PENDING,
        server_default=ResumeParseStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    user = relationship("User", back_populates="resumes")
    interviews = relationship("Interview", back_populates="resume")
