"""数据库连接池与 Session 管理。

- PostgreSQL 走真实连接池，参数从配置读取；
- SQLite（dev/test）使用 StaticPool；
- 提供 `get_db` 依赖与 `session_scope` 上下文，前者用于 FastAPI，后者用于 Celery / 脚本。
"""
from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def _build_engine_kwargs() -> dict:
    if settings.is_sqlite:
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
            "pool_pre_ping": True,
        }
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": settings.DB_POOL_PRE_PING,
        "pool_use_lifo": True,  # 减少长连接抖动
    }


engine = create_engine(settings.DATABASE_URL, future=True, **_build_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 Session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务上下文：失败回滚，成功提交。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """开发期建表：仅在 AUTO_CREATE_TABLES=True 时使用，生产环境用 Alembic。"""
    from app.db.base import Base
    from app.models import interview, job, rag, resume, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
