"""应用全局配置。

设计要点：
- 所有配置通过环境变量注入，符合 12-Factor App 原则；
- `ENVIRONMENT=production` 时强制校验生产敏感项，杜绝默认 SECRET_KEY 上线；
- AI / Embedding / 数据库 / 限流 / 监控 等参数集中管理，便于统一调优。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ---------- 基础应用 ----------
    APP_NAME: str = "AI Mock Interview Platform"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_JSON: bool = False  # 生产建议 True，由 structlog 输出 JSON 格式日志

    # ---------- 数据库 ----------
    DATABASE_URL: str = "sqlite:///./interview_dev.db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True
    AUTO_CREATE_TABLES: bool = True  # 仅 dev/test 用，生产必须 False，由 Alembic 管控

    # ---------- 缓存 / 任务 ----------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    # ---------- JWT ----------
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # ---------- CORS ----------
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )

    # ---------- 速率限制 ----------
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_REGISTER: str = "5/hour"

    # ---------- AI 调用 ----------
    AI_RUNTIME: Literal["mock", "deepseek"] = "mock"
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    AI_TIMEOUT: float = 60.0
    AI_MAX_RETRIES: int = 3
    AI_TEMPERATURE: float = 0.2
    AI_MAX_TOKENS: int = 2048

    # ---------- Embedding ----------
    EMBEDDING_RUNTIME: Literal["mock", "dashscope"] = "mock"
    DASHSCOPE_API_KEY: str | None = None
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIMENSIONS: int = 1024
    EMBEDDING_BATCH_SIZE: int = 10
    EMBEDDING_TIMEOUT: float = 30.0
    EMBEDDING_MAX_RETRIES: int = 3

    # ---------- RAG ----------
    RAG_CHUNK_SIZE: int = 700
    RAG_CHUNK_OVERLAP: int = 120
    RAG_TOP_K: int = 5
    RAG_HNSW_M: int = 16
    RAG_HNSW_EF_CONSTRUCTION: int = 64
    RAG_HNSW_EF_SEARCH: int = 40

    # ---------- 文件上传 ----------
    MAX_RESUME_UPLOAD_MB: int = 10
    ALLOWED_RESUME_MIMETYPES: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown",
        ]
    )

    # ---------- 监控 ----------
    SENTRY_DSN: str | None = None
    PROMETHEUS_ENABLED: bool = True

    # ---------- 默认管理员 ----------
    DEFAULT_ADMIN_EMAIL: str = "admin@ai-interview.com"
    DEFAULT_ADMIN_PASSWORD: str = "admin123"
    DEFAULT_ADMIN_NAME: str = "系统管理员"

    # ============= 校验 =============
    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_mode(cls, v):
        if isinstance(v, str):
            value = v.strip().lower()
            if value in {"release", "prod", "production"}:
                return False
            if value in {"debug", "dev", "development"}:
                return True
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_csv_origins(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("ALLOWED_RESUME_MIMETYPES", mode="before")
    @classmethod
    def split_csv_mimes(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            self._validate_production_hardening()
            if self.SECRET_KEY in {"change-me-in-production", ""}:
                raise ValueError("生产环境 SECRET_KEY 不能使用默认值，请通过环境变量注入")
            if self.DATABASE_URL.startswith("sqlite"):
                raise ValueError("生产环境必须使用 PostgreSQL，不能使用 SQLite")
            if self.AUTO_CREATE_TABLES:
                raise ValueError("生产环境 AUTO_CREATE_TABLES 必须为 False，由 Alembic 管控迁移")
            if self.DEBUG:
                raise ValueError("生产环境 DEBUG 必须为 False")
        # Celery 默认走 Redis
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL
        return self

    def _validate_production_hardening(self) -> None:
        unsafe_secret_keys = {
            "",
            "change-me-in-production",
            "please-rotate-this-in-production-32bytes-min",
        }
        if self.SECRET_KEY in unsafe_secret_keys or len(self.SECRET_KEY) < 32:
            raise ValueError("production SECRET_KEY must be a rotated secret with at least 32 characters")

        unsafe_admin_passwords = {"", "admin123", "password", "changeme", "change-me"}
        if self.DEFAULT_ADMIN_PASSWORD in unsafe_admin_passwords or len(self.DEFAULT_ADMIN_PASSWORD) < 12:
            raise ValueError("production DEFAULT_ADMIN_PASSWORD must be changed before deployment")

        unsafe_origins = {"*", "http://localhost", "http://127.0.0.1"}
        if any(origin in unsafe_origins or origin.startswith("http://localhost:") for origin in self.CORS_ORIGINS):
            raise ValueError("production CORS_ORIGINS must use explicit public HTTPS origins")

        if self.AI_RUNTIME == "deepseek" and not self.DEEPSEEK_API_KEY:
            raise ValueError("production DEEPSEEK_API_KEY is required when AI_RUNTIME=deepseek")
        if self.EMBEDDING_RUNTIME == "dashscope" and not self.DASHSCOPE_API_KEY:
            raise ValueError("production DASHSCOPE_API_KEY is required when EMBEDDING_RUNTIME=dashscope")

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith(("postgresql", "postgres"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
