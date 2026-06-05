from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_config import AIModelConfig, AIProvider, AIRuntime
from app.models.ai_usage import AIUsageStatus
from app.schemas.ai_config import AIModelConfigRead, AIModelConfigUpdate, AIModelTestResult
from app.services import ai_usage_service


logger = structlog.get_logger("ai.config")


@dataclass(frozen=True)
class EffectiveAIConfig:
    id: int | None
    name: str
    runtime: AIRuntime
    provider: AIProvider
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    timeout: float
    max_retries: int
    is_active: bool = True
    last_test_status: str | None = None
    last_test_latency_ms: float | None = None
    last_test_error: str | None = None
    updated_at: datetime | None = None


def get_config(db: Session) -> AIModelConfigRead:
    return to_read(get_effective_config(db))


def upsert_config(db: Session, payload: AIModelConfigUpdate) -> AIModelConfigRead:
    config = _active_row(db)
    if not config:
        config = AIModelConfig(
            name=payload.name,
            runtime=payload.runtime,
            provider=payload.provider,
            base_url=payload.base_url.strip(),
            api_key=(payload.api_key or "").strip(),
            model=payload.model.strip(),
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            timeout=payload.timeout,
            max_retries=payload.max_retries,
            is_active=True,
        )
        db.add(config)
    else:
        config.name = payload.name
        config.runtime = payload.runtime
        config.provider = payload.provider
        config.base_url = payload.base_url.strip()
        if payload.api_key is not None:
            config.api_key = payload.api_key.strip()
        config.model = payload.model.strip()
        config.temperature = payload.temperature
        config.max_tokens = payload.max_tokens
        config.timeout = payload.timeout
        config.max_retries = payload.max_retries
        config.is_active = True
        config.last_test_status = None
        config.last_test_latency_ms = None
        config.last_test_error = None

    db.commit()
    db.refresh(config)
    return to_read(_from_row(config))


def test_active_config(db: Session) -> AIModelTestResult:
    config = get_effective_config(db)
    start = time.perf_counter()
    ok = False
    error: str | None = None

    try:
        if config.runtime == AIRuntime.MOCK:
            ok = True
        elif config.runtime == AIRuntime.DEEPSEEK:
            _test_openai_compatible(config)
            ok = True
        else:  # pragma: no cover - enum guard
            raise RuntimeError(f"unsupported runtime: {config.runtime}")
    except Exception as exc:  # noqa: BLE001 - store provider-specific failure text
        error = str(exc)[:1000]
        logger.warning("ai_config_test_failed", runtime=config.runtime.value, error=error)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    status = "ok" if ok else "failed"
    _persist_test_result(db, status=status, latency_ms=latency_ms, error=error)
    ai_usage_service.record_ai_usage_safely(
        feature="config_test",
        runtime=config.runtime,
        provider=config.provider,
        model=config.model,
        status=AIUsageStatus.OK if ok else AIUsageStatus.FAILED,
        latency_ms=latency_ms,
        error=error,
    )
    return AIModelTestResult(
        ok=ok,
        status=status,
        runtime=config.runtime,
        provider=config.provider,
        model=config.model,
        latency_ms=latency_ms,
        message="model configuration is reachable" if ok else "model configuration test failed",
        error=error,
    )


def get_effective_config(db: Session | None = None) -> EffectiveAIConfig:
    if db is not None:
        row = _active_row(db)
        return _from_row(row) if row else _from_settings()

    from app.db.session import SessionLocal

    with SessionLocal() as runtime_db:
        row = _active_row(runtime_db)
        return _from_row(row) if row else _from_settings()


def to_read(config: EffectiveAIConfig) -> AIModelConfigRead:
    return AIModelConfigRead(
        id=config.id,
        name=config.name,
        runtime=config.runtime,
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout,
        max_retries=config.max_retries,
        is_active=config.is_active,
        has_api_key=bool(config.api_key),
        api_key_masked=mask_api_key(config.api_key),
        last_test_status=config.last_test_status,
        last_test_latency_ms=config.last_test_latency_ms,
        last_test_error=config.last_test_error,
        updated_at=config.updated_at,
    )


def mask_api_key(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _active_row(db: Session) -> AIModelConfig | None:
    return db.scalar(
        select(AIModelConfig)
        .where(AIModelConfig.is_active.is_(True))
        .order_by(AIModelConfig.id.desc())
        .limit(1)
    )


def _from_row(row: AIModelConfig) -> EffectiveAIConfig:
    return EffectiveAIConfig(
        id=row.id,
        name=row.name,
        runtime=row.runtime,
        provider=row.provider,
        base_url=row.base_url,
        api_key=row.api_key,
        model=row.model,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        timeout=row.timeout,
        max_retries=row.max_retries,
        is_active=row.is_active,
        last_test_status=row.last_test_status,
        last_test_latency_ms=row.last_test_latency_ms,
        last_test_error=row.last_test_error,
        updated_at=row.updated_at,
    )


def _from_settings() -> EffectiveAIConfig:
    if settings.AI_RUNTIME == "deepseek":
        return EffectiveAIConfig(
            id=None,
            name="Environment DeepSeek",
            runtime=AIRuntime.DEEPSEEK,
            provider=AIProvider.DEEPSEEK,
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY or "",
            model=settings.DEEPSEEK_MODEL,
            temperature=settings.AI_TEMPERATURE,
            max_tokens=settings.AI_MAX_TOKENS,
            timeout=settings.AI_TIMEOUT,
            max_retries=settings.AI_MAX_RETRIES,
        )
    return EffectiveAIConfig(
        id=None,
        name="Local Mock",
        runtime=AIRuntime.MOCK,
        provider=AIProvider.MOCK,
        base_url="",
        api_key="",
        model="mock-interview",
        temperature=settings.AI_TEMPERATURE,
        max_tokens=settings.AI_MAX_TOKENS,
        timeout=settings.AI_TIMEOUT,
        max_retries=settings.AI_MAX_RETRIES,
    )


def _persist_test_result(
    db: Session, *, status: str, latency_ms: float, error: str | None
) -> None:
    row = _active_row(db)
    if not row:
        return
    row.last_test_status = status
    row.last_test_latency_ms = latency_ms
    row.last_test_error = error
    db.commit()


def _test_openai_compatible(config: EffectiveAIConfig) -> None:
    if not config.api_key:
        raise RuntimeError("api_key is required")

    from openai import OpenAI
    import httpx

    client = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=httpx.Timeout(
            connect=10.0,
            read=config.timeout,
            write=10.0,
            pool=5.0,
        ),
        max_retries=0,
    )
    client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": "You are a health check endpoint."},
            {"role": "user", "content": "Reply with ok."},
        ],
        temperature=0,
        max_tokens=8,
    )
