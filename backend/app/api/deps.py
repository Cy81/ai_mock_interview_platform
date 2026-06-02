"""FastAPI 依赖：当前用户 / 管理员 / 数据库 / 限流。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import PermissionDenied
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=True,
)
oauth2_optional = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


def _user_from_token(token: str, db: Session) -> User:
    payload = decode_token(token, expected_type="access")
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效或过期的登录凭证")
    sub = payload.get("sub")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "无效或过期的登录凭证") from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在或已禁用")
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return _user_from_token(token, db)


def get_optional_user(
    token: str | None = Depends(oauth2_optional),
    db: Session = Depends(get_db),
) -> User | None:
    if not token:
        return None
    try:
        return _user_from_token(token, db)
    except HTTPException:
        return None


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
        raise PermissionDenied("需要管理员权限")
    return user


def get_current_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SUPERADMIN:
        raise PermissionDenied("需要超级管理员权限")
    return user
