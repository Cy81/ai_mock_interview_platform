"""JWT 与密码哈希。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_context.hash(password)


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "type": token_type,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    return _create_token(
        subject,
        "access",
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        {"role": role},
    )


def create_refresh_token(subject: str, expires_delta: timedelta | None = None) -> str:
    return _create_token(
        subject,
        "refresh",
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if expected_type and payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None
