"""认证相关 Schema：注册、登录、刷新、用户视图。"""
from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserRole


PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,72}$")


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not PASSWORD_RULE.match(value):
            raise ValueError("密码至少 8 位，并同时包含字母和数字")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not PASSWORD_RULE.match(value):
            raise ValueError("新密码至少 8 位，并同时包含字母和数字")
        return value


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    avatar_url: str | None = Field(default=None, max_length=512)


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    is_email_verified: bool
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒
    user: UserRead


class RefreshRequest(BaseModel):
    refresh_token: str
