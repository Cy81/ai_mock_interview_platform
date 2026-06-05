"""集中导出所有 ORM 模型，便于 Alembic autogenerate 与依赖注入。"""
from app.models.ai_config import AIModelConfig, AIProvider, AIRuntime
from app.models.ai_usage import AIUsageLog, AIUsageStatus
from app.models.interview import (
    Difficulty,
    Interview,
    InterviewAnswer,
    InterviewQuestion,
    InterviewStatus,
    QuestionType,
)
from app.models.job import JobDirection
from app.models.rag import IndexStatus, RagChunk, RagDocument, RagType
from app.models.resume import Resume, ResumeParseStatus
from app.models.user import User, UserRole

__all__ = [
    "Difficulty",
    "AIModelConfig",
    "AIProvider",
    "AIRuntime",
    "AIUsageLog",
    "AIUsageStatus",
    "IndexStatus",
    "Interview",
    "InterviewAnswer",
    "InterviewQuestion",
    "InterviewStatus",
    "JobDirection",
    "QuestionType",
    "RagChunk",
    "RagDocument",
    "RagType",
    "Resume",
    "ResumeParseStatus",
    "User",
    "UserRole",
]
