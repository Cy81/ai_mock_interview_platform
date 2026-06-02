"""FastAPI 应用入口：生命周期、中间件、监控、路由装配。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import structlog

from app.api.deps import limiter
from app.api.v1.router import client_router, admin_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.db.session import SessionLocal, init_db


configure_logging()
logger = get_logger("startup")


def _init_sentry() -> None:
    if not settings.SENTRY_DSN:
        return
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("app_starting", env=settings.ENVIRONMENT, version=settings.APP_VERSION)
    if settings.AUTO_CREATE_TABLES:
        init_db()
        from app.services.bootstrap import bootstrap_data

        with SessionLocal() as db:
            bootstrap_data(db)
    _init_sentry()
    yield
    logger.info("app_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG or settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.DEBUG or settings.ENVIRONMENT != "production" else None,
    )

    # 中间件顺序：CORS -> 限流 -> RequestContext
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    )
    app.add_middleware(RequestContextMiddleware)

    # 限流
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 异常
    register_exception_handlers(app)

    # 路由：客户端 API + 后台管理 API
    app.include_router(client_router, prefix=settings.API_V1_PREFIX)
    app.include_router(admin_router, prefix=f"{settings.API_V1_PREFIX}/admin")

    # 监控指标
    if settings.PROMETHEUS_ENABLED:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    @app.get("/healthz", tags=["健康检查"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["健康检查"])
    def readyz() -> dict[str, str]:
        # 真实环境可以加 DB / Redis ping
        return {
            "status": "ready",
            "ai_runtime": settings.AI_RUNTIME,
            "embedding_runtime": settings.EMBEDDING_RUNTIME,
            "version": settings.APP_VERSION,
        }

    return app


app = create_app()
