"""客户端：认证路由 (/api/v1/auth/*)。"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, limiter
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    PasswordChange,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserRead,
    UserUpdate,
)
from app.schemas.common import Message
from app.services import auth_service


router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="注册新用户并返回 token",
)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    user = auth_service.register_user(
        db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
    )
    return auth_service.issue_token_pair(user)


@router.post("/login", response_model=TokenPair, summary="邮箱密码登录")
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, payload.email, payload.password)
    return auth_service.issue_token_pair(user)


@router.post("/refresh", response_model=TokenPair, summary="刷新 Access Token")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.post("/logout", response_model=Message, summary="登出（前端清 token）")
def logout(_: User = Depends(get_current_user)):
    return Message(message="已登出")


@router.get("/me", response_model=UserRead, summary="获取当前用户信息")
def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserRead, summary="更新当前用户信息")
def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/change-password", response_model=Message, summary="修改密码")
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(
        db, user, old_password=payload.old_password, new_password=payload.new_password
    )
    return Message(message="密码修改成功")
