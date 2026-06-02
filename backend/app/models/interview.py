"""面试领域模型：状态机 + 子表（题目 / 答案）+ 评分报告。

设计动机：
- 把原本压在主表 JSON 列里的 questions / answers 拆成独立表，
  避免并发提交时整列覆盖丢答案，也方便单题分析、分页和重试评分；
- 状态用 Python Enum + DB Enum 双重约束，状态流转在服务层显式校验；
- 给面试加 idempotency_key（前端去重）和 status_reason（失败可解释）。
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class InterviewStatus(str, enum.Enum):
    CREATED = "created"
    GENERATING = "generating"
    IN_PROGRESS = "in_progress"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QuestionType(str, enum.Enum):
    TECHNICAL = "technical"
    PROJECT = "project"
    SYSTEM_DESIGN = "system_design"
    BEHAVIORAL = "behavioral"


class Difficulty(str, enum.Enum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"
    __table_args__ = (
        Index("ix_interviews_user_status", "user_id", "status"),
        UniqueConstraint("idempotency_key", name="uq_interviews_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="RESTRICT"), index=True, nullable=False)

    job_code: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)

    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, native_enum=False, length=20),
        default=InterviewStatus.CREATED,
        server_default=InterviewStatus.CREATED.value,
        nullable=False,
        index=True,
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=6, server_default="6", nullable=False)

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    score_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User", back_populates="interviews")
    resume = relationship("Resume", back_populates="interviews")
    questions = relationship(
        "InterviewQuestion",
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="InterviewQuestion.position",
    )
    answers = relationship(
        "InterviewAnswer",
        back_populates="interview",
        cascade="all, delete-orphan",
    )


class InterviewQuestion(TimestampMixin, Base):
    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint("interview_id", "position", name="uq_iq_interview_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, native_enum=False, length=20),
        default=QuestionType.TECHNICAL,
        server_default=QuestionType.TECHNICAL.value,
        nullable=False,
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, native_enum=False, length=20),
        default=Difficulty.INTERMEDIATE,
        server_default=Difficulty.INTERMEDIATE.value,
        nullable=False,
    )
    skill: Mapped[str] = mapped_column(String(80), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    rubric: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reference_chunk_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)

    interview = relationship("Interview", back_populates="questions")
    answer = relationship(
        "InterviewAnswer",
        back_populates="question",
        uselist=False,
        cascade="all, delete-orphan",
    )


class InterviewAnswer(TimestampMixin, Base):
    __tablename__ = "interview_answers"
    __table_args__ = (
        UniqueConstraint("question_id", name="uq_ia_question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"), index=True, nullable=False
    )

    answer: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    interview = relationship("Interview", back_populates="answers")
    question = relationship("InterviewQuestion", back_populates="answer")
