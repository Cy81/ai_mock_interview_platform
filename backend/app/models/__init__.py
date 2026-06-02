"""集中导出所有 ORM 模型，便于 Alembic autogenerate 与依赖注入。"""
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
