from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.ai_config import AIProvider, AIRuntime
from app.models.ai_usage import AIUsageStatus


class AIUsageLogRead(BaseModel):
    id: int
    feature: str
    runtime: AIRuntime
    provider: AIProvider
    model: str
    status: AIUsageStatus
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    error: str | None = None
    request_id: str | None = None
    user_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIUsageModelBucket(BaseModel):
    model: str
    runtime: AIRuntime
    provider: AIProvider
    calls: int
    total_tokens: int
    avg_latency_ms: float
    failed_calls: int


class AIUsageSummary(BaseModel):
    total_calls: int
    success_calls: int
    failed_calls: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    avg_latency_ms: float
    by_model: list[AIUsageModelBucket]
