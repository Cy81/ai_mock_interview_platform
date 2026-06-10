"""Runtime health and readiness checks."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Literal

from sqlalchemy import text

from app.core.config import settings


HealthStatus = Literal["ok", "error"]


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: HealthStatus
    latency_ms: float | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        return {
            key: value
            for key, value in asdict(self).items()
            if key != "name" and value is not None
        }


def _measure(name: str, operation: Callable[[], None]) -> ComponentHealth:
    started = perf_counter()
    try:
        operation()
    except Exception as exc:  # pragma: no cover - driver-specific errors vary.
        return ComponentHealth(name=name, status="error", detail=str(exc)[:200])
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    return ComponentHealth(name=name, status="ok", latency_ms=elapsed_ms)


def check_database() -> ComponentHealth:
    def ping() -> None:
        from app.db.session import engine

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    return _measure("database", ping)


def check_redis() -> ComponentHealth:
    def ping() -> None:
        from redis import Redis

        client = Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        try:
            client.ping()
        finally:
            client.close()

    return _measure("redis", ping)


def get_readiness(
    checks: list[Callable[[], ComponentHealth]] | None = None,
) -> dict:
    health_checks = checks or [check_database, check_redis]
    results = [check() for check in health_checks]
    ready = all(result.status == "ok" for result in results)

    return {
        "status": "ready" if ready else "not_ready",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "ai_runtime": settings.AI_RUNTIME,
        "embedding_runtime": settings.EMBEDDING_RUNTIME,
        "components": {result.name: result.to_dict() for result in results},
    }
