"""面试相关 Schema：创建 / 答题 / 报告。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.interview import Difficulty, InterviewStatus, QuestionType


class InterviewCreate(BaseModel):
    resume_id: int = Field(gt=0)
    job_code: str = Field(min_length=1, max_length=80)
    question_count: int = Field(default=6, ge=1, le=12)
    idempotency_key: str | None = Field(default=None, max_length=64)
    conversational: bool = False


class AnswerSubmit(BaseModel):
    question_id: int = Field(gt=0)
    answer: str = Field(min_length=1, max_length=8000)
    duration_ms: int | None = Field(default=None, ge=0, le=24 * 3600 * 1000)


class InterviewQuestionRead(BaseModel):
    id: int
    position: int
    type: QuestionType
    difficulty: Difficulty
    skill: str
    question: str
    rubric: list[str]
    reference_chunk_ids: list[int]

    model_config = {"from_attributes": True}


class InterviewAnswerRead(BaseModel):
    id: int
    question_id: int
    answer: str
    char_count: int
    duration_ms: int | None
    score: float | None
    comment: str | None
    answered_at: datetime

    model_config = {"from_attributes": True}


class InterviewBrief(BaseModel):
    id: int
    job_code: str
    job_title: str
    status: InterviewStatus
    overall_score: float | None = None
    question_count: int
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class InterviewRead(InterviewBrief):
    resume_id: int
    started_at: datetime | None = None
    questions: list[InterviewQuestionRead] = Field(default_factory=list)
    answers: list[InterviewAnswerRead] = Field(default_factory=list)
    score_report: dict[str, Any] | None = None
    status_reason: str | None = None


class InterviewTurnRead(BaseModel):
    interview: InterviewRead
    answered_question_id: int
    next_question: InterviewQuestionRead | None = None
    completed: bool = False


class ReportRead(BaseModel):
    interview_id: int
    job_title: str
    status: InterviewStatus
    overall_score: float | None
    report: dict[str, Any] | None
    completed_at: datetime | None
