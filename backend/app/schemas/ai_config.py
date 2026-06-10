from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.ai_config import AIProvider, AIRuntime, AIWireAPI


class AIModelConfigUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    runtime: AIRuntime
    provider: AIProvider
    base_url: str = Field(default="", max_length=512)
    api_key: str | None = Field(default=None, max_length=4096)
    model: str = Field(min_length=1, max_length=120)
    wire_api: AIWireAPI = AIWireAPI.CHAT_COMPLETIONS
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(ge=1, le=128000)
    timeout: float = Field(ge=1, le=600)
    max_retries: int = Field(ge=0, le=10)

    @model_validator(mode="after")
    def validate_provider(self) -> "AIModelConfigUpdate":
        if self.runtime == AIRuntime.MOCK:
            return self
        if self.provider != AIProvider.DEEPSEEK:
            raise ValueError("deepseek runtime requires deepseek provider")
        if not self.base_url.strip():
            raise ValueError("deepseek runtime requires base_url")
        return self


class AIModelConfigRead(BaseModel):
    id: int | None = None
    name: str
    runtime: AIRuntime
    provider: AIProvider
    base_url: str
    model: str
    wire_api: AIWireAPI
    temperature: float
    max_tokens: int
    timeout: float
    max_retries: int
    is_active: bool
    has_api_key: bool
    api_key_masked: str
    last_test_status: str | None = None
    last_test_latency_ms: float | None = None
    last_test_error: str | None = None
    updated_at: datetime | None = None


class AIModelTestResult(BaseModel):
    ok: bool
    status: str
    runtime: AIRuntime
    provider: AIProvider
    model: str
    wire_api: AIWireAPI
    latency_ms: float
    message: str
    error: str | None = None
