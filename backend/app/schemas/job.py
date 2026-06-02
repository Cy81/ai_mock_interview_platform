"""岗位与岗位推荐 Schema。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobDirectionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_\-]+$")
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=2, max_length=4000)
    required_skills: list[str] = Field(default_factory=list, max_length=30)
    nice_to_have_skills: list[str] = Field(default_factory=list, max_length=30)
    competency_model: dict[str, float] = Field(default_factory=dict)
    seniority: str = Field(default="junior-mid", max_length=50)
    salary_range: str | None = Field(default=None, max_length=50)
    sort_order: int = Field(default=0, ge=0, le=999)


class JobDirectionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, min_length=2, max_length=4000)
    required_skills: list[str] | None = None
    nice_to_have_skills: list[str] | None = None
    competency_model: dict[str, float] | None = None
    seniority: str | None = Field(default=None, max_length=50)
    salary_range: str | None = Field(default=None, max_length=50)
    sort_order: int | None = Field(default=None, ge=0, le=999)
    is_active: bool | None = None


class JobDirectionRead(BaseModel):
    id: int
    code: str
    title: str
    description: str
    required_skills: list[str]
    nice_to_have_skills: list[str]
    competency_model: dict[str, float]
    seniority: str
    salary_range: str | None = None
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class JobRecommendationRequest(BaseModel):
    resume_id: int = Field(gt=0)
    top_n: int = Field(default=3, ge=1, le=10)


class KnowledgeReference(BaseModel):
    id: int
    title: str
    content: str
    score: float


class JobRecommendation(BaseModel):
    code: str
    title: str
    match_score: float
    reasons: list[str]
    gaps: list[str]
    suggested_learning_path: list[str]
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list)
    source: str = "rule"


class JobRecommendationResponse(BaseModel):
    resume_id: int
    recommendations: list[JobRecommendation]
