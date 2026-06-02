"""统一异常处理：领域异常 + 校验异常 + 数据库异常 + 兜底异常。"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import structlog


class DomainError(Exception):
    """领域错误：业务规则违反，4xx 语义。"""

    def __init__(self, message: str, status_code: int = 400, code: str | None = None) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code or "DOMAIN_ERROR"
        super().__init__(message)


class NotFoundError(DomainError):
    def __init__(self, message: str = "资源不存在或无权限访问") -> None:
        super().__init__(message, status_code=404, code="NOT_FOUND")


class ConflictError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409, code="CONFLICT")


class PermissionDenied(DomainError):
    def __init__(self, message: str = "权限不足") -> None:
        super().__init__(message, status_code=403, code="PERMISSION_DENIED")


def _payload(detail: str, code: str, request_id: str | None = None) -> dict:
    body = {"detail": detail, "code": code}
    if request_id:
        body["request_id"] = request_id
    return body


def register_exception_handlers(app: FastAPI) -> None:
    logger = structlog.get_logger("exception")

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        logger.info("domain_error", code=exc.code, message=exc.message, status=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.message, exc.code, rid),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        errors = [
            {
                "field": ".".join(str(p) for p in e.get("loc", []) if p != "body"),
                "message": e.get("msg"),
                "type": e.get("type"),
            }
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "请求参数校验失败",
                "code": "VALIDATION_ERROR",
                "errors": errors,
                **({"request_id": rid} if rid else {}),
            },
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        logger.warning("integrity_error", error=str(exc.orig)[:200])
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_payload("数据冲突，资源可能已存在", "INTEGRITY_ERROR", rid),
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_sql_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        logger.exception("database_error")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("数据库错误，请稍后重试", "DATABASE_ERROR", rid),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(str(exc.detail), f"HTTP_{exc.status_code}", rid),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = request.headers.get("X-Request-ID")
        logger.exception("unhandled_exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("服务器内部错误", "INTERNAL_ERROR", rid),
        )
