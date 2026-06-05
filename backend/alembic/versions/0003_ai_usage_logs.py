"""add ai usage logs

Revision ID: 0003_ai_usage_logs
Revises: 0002_ai_model_configs
Create Date: 2026-06-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_ai_usage_logs"
down_revision: Union[str, None] = "0002_ai_model_configs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ai_runtime = sa.Enum("mock", "deepseek", name="ai_runtime", native_enum=False, length=20)
    ai_provider = sa.Enum("mock", "deepseek", name="ai_provider", native_enum=False, length=20)
    ai_usage_status = sa.Enum("ok", "failed", name="ai_usage_status", native_enum=False, length=20)

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("runtime", ai_runtime, nullable=False),
        sa.Column("provider", ai_provider, nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", ai_usage_status, nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_usage_logs_id", "ai_usage_logs", ["id"], unique=False)
    op.create_index("ix_ai_usage_logs_feature", "ai_usage_logs", ["feature"], unique=False)
    op.create_index("ix_ai_usage_logs_runtime", "ai_usage_logs", ["runtime"], unique=False)
    op.create_index("ix_ai_usage_logs_provider", "ai_usage_logs", ["provider"], unique=False)
    op.create_index("ix_ai_usage_logs_model", "ai_usage_logs", ["model"], unique=False)
    op.create_index("ix_ai_usage_logs_status", "ai_usage_logs", ["status"], unique=False)
    op.create_index("ix_ai_usage_logs_request_id", "ai_usage_logs", ["request_id"], unique=False)
    op.create_index("ix_ai_usage_logs_user_id", "ai_usage_logs", ["user_id"], unique=False)
    op.create_index("ix_ai_usage_created_status", "ai_usage_logs", ["created_at", "status"], unique=False)
    op.create_index("ix_ai_usage_feature_model", "ai_usage_logs", ["feature", "model"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_usage_feature_model", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_created_status", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_user_id", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_request_id", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_status", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_model", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_provider", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_runtime", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_feature", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_id", table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")
