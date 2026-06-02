"""用户模型：增加 role / 多状态字段 / 登录失败计数。"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    interviews = relationship("Interview", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.SUPERADMIN)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email} role={self.role.value}>"
