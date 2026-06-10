"""请求级中间件：注入 request_id、记录耗时、写入 structlog 上下文。"""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 X-Request-ID 并绑定到 structlog 上下文。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        start = time.perf_counter()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        logger = structlog.get_logger("http")
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception("request_failed", duration_ms=round(duration_ms, 2))
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        logger.info(
            "request_completed",
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response
