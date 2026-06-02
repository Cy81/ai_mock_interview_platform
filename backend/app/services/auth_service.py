"""认证服务：注册 / 登录 / Token 刷新 / 改密 / 失败锁定。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User, UserRole


logger = structlog.get_logger("auth")

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def register_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: UserRole = UserRole.USER,
) -> User:
    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("该邮箱已注册")
    user = User(
        email=email,
        full_name=full_name.strip(),
        hashed_password=get_password_hash(password),
        role=role,
        is_active=True,
        is_email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("user_registered", user_id=user.id, email=email)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise DomainError("邮箱或密码错误", status_code=401)
    if user.locked_until and user.locked_until > _now():
        raise DomainError(
            f"账户因多次登录失败已临时锁定，请在 {user.locked_until:%H:%M} 后重试",
            status_code=423,
        )
    if not verify_password(password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= LOCKOUT_THRESHOLD:
            user.locked_until = _now() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            db.commit()
            raise DomainError("登录失败次数过多，账户已临时锁定", status_code=423)
        db.commit()
        raise DomainError("邮箱或密码错误", status_code=401)
    if not user.is_active:
        raise DomainError("账户已禁用，请联系管理员", status_code=403)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()
    db.commit()
    db.refresh(user)
    return user


def issue_token_pair(user: User) -> dict:
    access = create_access_token(str(user.id), role=user.role.value)
    refresh = create_refresh_token(str(user.id))
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user,
    }


def refresh_access_token(db: Session, refresh_token: str) -> dict:
    payload = decode_token(refresh_token, expected_type="refresh")
    if not payload:
        raise DomainError("Refresh Token 无效或已过期", status_code=401)
    try:
        user_id = int(payload.get("sub") or 0)
    except (TypeError, ValueError):
        raise DomainError("Refresh Token 无效", status_code=401) from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise DomainError("用户不存在或已禁用", status_code=401)
    return issue_token_pair(user)


def change_password(db: Session, user: User, *, old_password: str, new_password: str) -> None:
    if not verify_password(old_password, user.hashed_password):
        raise DomainError("原密码不正确", status_code=400)
    if old_password == new_password:
        raise DomainError("新密码不能与原密码相同", status_code=400)
    user.hashed_password = get_password_hash(new_password)
    db.commit()


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    return user


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
