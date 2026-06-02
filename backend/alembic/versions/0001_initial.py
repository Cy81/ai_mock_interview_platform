"""initial schema with users / jobs / resumes / interviews+子表 / rag 文档+chunk

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-31

注意：HNSW 索引带 vector_cosine_ops opclass + m / ef_construction 参数；
所有时间戳走 server_default = NOW()。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op
from pgvector.sqlalchemy import Vector


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    bind = context.get_bind()
    return bind is not None and bind.dialect.name in {"postgresql", "postgres"}


def upgrade() -> None:
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    user_role = sa.Enum(
        "user", "admin", "superadmin", name="user_role", native_enum=False, length=20
    )
    interview_status = sa.Enum(
        "created", "generating", "in_progress", "scoring", "completed", "failed", "cancelled",
        name="interview_status", native_enum=False, length=20,
    )
    question_type = sa.Enum(
        "technical", "project", "system_design", "behavioral",
        name="question_type", native_enum=False, length=20,
    )
    difficulty = sa.Enum(
        "basic", "intermediate", "advanced",
        name="difficulty", native_enum=False, length=20,
    )
    rag_type = sa.Enum(
        "question_bank", "knowledge_base",
        name="rag_type", native_enum=False, length=20,
    )
    index_status = sa.Enum(
        "pending", "indexing", "ready", "failed",
        name="index_status", native_enum=False, length=20,
    )
    parse_status = sa.Enum(
        "pending", "parsing", "parsed", "failed",
        name="resume_parse_status", native_enum=False, length=20,
    )

    # ----- users -----
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    # ----- job_directions -----
    op.create_table(
        "job_directions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("nice_to_have_skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("competency_model", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("seniority", sa.String(50), nullable=False, server_default="junior-mid"),
        sa.Column("salary_range", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_job_directions_code"),
        sa.UniqueConstraint("title", name="uq_job_directions_title"),
    )
    op.create_index("ix_job_directions_active", "job_directions", ["is_active", "sort_order"])

    # ----- resumes -----
    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parsed_profile", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("target_position", sa.String(120), nullable=True),
        sa.Column("parse_status", parse_status, nullable=False, server_default="pending"),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_resumes_user_id", "resumes", ["user_id"])
    op.create_index("ix_resumes_content_hash", "resumes", ["content_hash"])
    op.create_index("ix_resumes_parse_status", "resumes", ["parse_status"])

    # ----- interviews -----
    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("job_code", sa.String(80), nullable=False),
        sa.Column("job_title", sa.String(120), nullable=False),
        sa.Column("status", interview_status, nullable=False, server_default="created"),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("score_report", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name="uq_interviews_idempotency_key"),
    )
    op.create_index("ix_interviews_user_status", "interviews", ["user_id", "status"])
    op.create_index("ix_interviews_job_code", "interviews", ["job_code"])
    op.create_index("ix_interviews_overall_score", "interviews", ["overall_score"])

    # ----- interview_questions -----
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("type", question_type, nullable=False, server_default="technical"),
        sa.Column("difficulty", difficulty, nullable=False, server_default="intermediate"),
        sa.Column("skill", sa.String(80), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rubric", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reference_chunk_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("interview_id", "position", name="uq_iq_interview_position"),
    )
    op.create_index("ix_iq_interview_id", "interview_questions", ["interview_id"])

    # ----- interview_answers -----
    op.create_table(
        "interview_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["interview_questions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("question_id", name="uq_ia_question_id"),
    )
    op.create_index("ix_ia_interview_id", "interview_answers", ["interview_id"])

    # ----- rag_documents -----
    op.create_table(
        "rag_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rag_type", rag_type, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_uri", sa.String(512), nullable=True),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("index_status", index_status, nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rag_documents_rag_type", "rag_documents", ["rag_type"])
    op.create_index("ix_rag_documents_title", "rag_documents", ["title"])
    op.create_index("ix_rag_documents_hash", "rag_documents", ["content_hash"])

    # ----- rag_chunks -----
    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("rag_type", rag_type, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rag_chunks_doc_chunk", "rag_chunks", ["document_id", "chunk_index"], unique=True)
    op.create_index("ix_rag_chunks_type_active", "rag_chunks", ["rag_type", "is_active"])
    op.create_index("ix_rag_chunks_hash", "rag_chunks", ["content_hash"])

    if _is_postgres():
        # HNSW + 余弦距离 opclass + 调优参数
        op.execute(
            "CREATE INDEX ix_rag_chunks_embedding_hnsw "
            "ON rag_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_rag_chunks_embedding_hnsw")
    op.drop_table("rag_chunks")
    op.drop_table("rag_documents")
    op.drop_table("interview_answers")
    op.drop_table("interview_questions")
    op.drop_table("interviews")
    op.drop_table("resumes")
    op.drop_table("job_directions")
    op.drop_table("users")
