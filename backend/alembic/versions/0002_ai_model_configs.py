"""add admin ai model configuration

Revision ID: 0002_ai_model_configs
Revises: 0001_initial
Create Date: 2026-06-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_ai_model_configs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ai_runtime = sa.Enum("mock", "deepseek", name="ai_runtime", native_enum=False, length=20)
    ai_provider = sa.Enum("mock", "deepseek", name="ai_provider", native_enum=False, length=20)

    op.create_table(
        "ai_model_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("runtime", ai_runtime, nullable=False),
        sa.Column("provider", ai_provider, nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("api_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="2048"),
        sa.Column("timeout", sa.Float(), nullable=False, server_default="60"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_test_status", sa.String(20), nullable=True),
        sa.Column("last_test_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_model_configs_id", "ai_model_configs", ["id"], unique=False)
    op.create_index("ix_ai_model_configs_runtime", "ai_model_configs", ["runtime"], unique=False)
    op.create_index("ix_ai_model_configs_provider", "ai_model_configs", ["provider"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_model_configs_provider", table_name="ai_model_configs")
    op.drop_index("ix_ai_model_configs_runtime", table_name="ai_model_configs")
    op.drop_index("ix_ai_model_configs_id", table_name="ai_model_configs")
    op.drop_table("ai_model_configs")
