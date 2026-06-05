from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_config import AIProvider, AIRuntime
from app.models.ai_usage import AIUsageLog, AIUsageStatus
from app.schemas.ai_usage import AIUsageLogRead, AIUsageModelBucket, AIUsageSummary


logger = structlog.get_logger("ai.usage")


def record_ai_usage(
    db: Session,
    *,
    feature: str,
    runtime: AIRuntime | str,
    provider: AIProvider | str,
    model: str,
    status: AIUsageStatus | str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: float = 0.0,
    error: str | None = None,
    request_id: str | None = None,
    user_id: int | None = None,
    commit: bool = True,
) -> AIUsageLog:
    log = AIUsageLog(
        feature=feature[:80],
        runtime=AIRuntime(runtime),
        provider=AIProvider(provider),
        model=(model or "unknown")[:120],
        status=AIUsageStatus(status),
        prompt_tokens=max(int(prompt_tokens or 0), 0),
        completion_tokens=max(int(completion_tokens or 0), 0),
        total_tokens=max(int(total_tokens or 0), 0),
        latency_ms=max(float(latency_ms or 0), 0.0),
        error=(error or None),
        request_id=request_id,
        user_id=user_id,
    )
    db.add(log)
    if commit:
        db.commit()
        db.refresh(log)
    return log


def record_ai_usage_safely(**kwargs: Any) -> None:
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            record_ai_usage(db, **kwargs)
    except Exception as exc:  # noqa: BLE001 - observability must not break product flow
        logger.warning("ai_usage_record_failed", error=str(exc)[:300])


def list_usage_logs(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    feature: str | None = None,
    status: AIUsageStatus | str | None = None,
) -> tuple[list[AIUsageLog], int]:
    stmt = select(AIUsageLog).order_by(AIUsageLog.created_at.desc(), AIUsageLog.id.desc())
    count_stmt = select(func.count(AIUsageLog.id))
    if feature:
        stmt = stmt.where(AIUsageLog.feature == feature)
        count_stmt = count_stmt.where(AIUsageLog.feature == feature)
    if status:
        normalized = AIUsageStatus(status)
        stmt = stmt.where(AIUsageLog.status == normalized)
        count_stmt = count_stmt.where(AIUsageLog.status == normalized)

    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


def summarize_usage(db: Session, *, days: int = 7) -> AIUsageSummary:
    since = datetime.utcnow() - timedelta(days=max(days, 1))
    rows = list(db.scalars(select(AIUsageLog).where(AIUsageLog.created_at >= since)))
    if not rows:
        return AIUsageSummary(
            total_calls=0,
            success_calls=0,
            failed_calls=0,
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            avg_latency_ms=0,
            by_model=[],
        )

    total_calls = len(rows)
    success_calls = sum(1 for row in rows if row.status == AIUsageStatus.OK)
    failed_calls = total_calls - success_calls
    prompt_tokens = sum(row.prompt_tokens for row in rows)
    completion_tokens = sum(row.completion_tokens for row in rows)
    total_tokens = sum(row.total_tokens for row in rows)
    avg_latency_ms = round(sum(row.latency_ms for row in rows) / total_calls, 2)

    grouped: dict[tuple[str, AIRuntime, AIProvider], list[AIUsageLog]] = defaultdict(list)
    for row in rows:
        grouped[(row.model, row.runtime, row.provider)].append(row)

    by_model = [
        AIUsageModelBucket(
            model=model,
            runtime=runtime,
            provider=provider,
            calls=len(items),
            total_tokens=sum(item.total_tokens for item in items),
            avg_latency_ms=round(sum(item.latency_ms for item in items) / len(items), 2),
            failed_calls=sum(1 for item in items if item.status == AIUsageStatus.FAILED),
        )
        for (model, runtime, provider), items in grouped.items()
    ]
    by_model.sort(key=lambda item: (item.total_tokens, item.calls), reverse=True)

    return AIUsageSummary(
        total_calls=total_calls,
        success_calls=success_calls,
        failed_calls=failed_calls,
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        avg_latency_ms=avg_latency_ms,
        by_model=by_model,
    )


def to_read_items(items: list[AIUsageLog]) -> list[AIUsageLogRead]:
    return [AIUsageLogRead.model_validate(item) for item in items]
