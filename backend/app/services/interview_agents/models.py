from __future__ import annotations

import enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


QuestionKind = Literal["technical", "project", "system_design", "behavioral"]
DifficultyLevel = Literal["basic", "intermediate", "advanced"]
TargetType = Literal["intern", "formal"]


class FollowupAction(str, enum.Enum):
    FOLLOWUP = "followup"
    COMMENT = "comment"
    NEXT_QUESTION_HINT = "next_question_hint"


class InterviewPlan(BaseModel):
    target_type: TargetType
    difficulty: DifficultyLevel
    core_skills: list[str] = Field(default_factory=list)
    question_mix: dict[str, int] = Field(default_factory=dict)
    style: str = "structured"
    notes: list[str] = Field(default_factory=list)

    @field_validator("core_skills")
    @classmethod
    def limit_core_skills(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()][:8]


class GeneratedQuestion(BaseModel):
    position: int = Field(ge=1)
    type: QuestionKind = "technical"
    difficulty: DifficultyLevel = "intermediate"
    skill: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=6)
    rubric: list[str] = Field(default_factory=list)
    reference_chunk_ids: list[int] = Field(default_factory=list)

    @field_validator("rubric")
    @classmethod
    def limit_rubric(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()][:6]


class QuestionGenerationResult(BaseModel):
    plan: InterviewPlan
    questions: list[GeneratedQuestion]


class FollowupResult(BaseModel):
    action: FollowupAction
    content: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    suggested_next_position: int | None = Field(default=None, ge=1)


class ScoreResult(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    level: str
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    question_scores: list[dict[str, object]] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    learning_plan: list[str] = Field(default_factory=list)


class ReportResult(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    level: str
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    question_scores: list[dict[str, object]] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    learning_plan: list[str] = Field(default_factory=list)
    next_practice: list[str] = Field(default_factory=list)
