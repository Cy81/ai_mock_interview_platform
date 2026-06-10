"""add ai model wire api selection

Revision ID: 0004_ai_model_wire_api
Revises: 0003_ai_usage_logs
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004_ai_model_wire_api"
down_revision: Union[str, None] = "0003_ai_usage_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    wire_api = sa.Enum(
        "chat_completions",
        "responses",
        name="ai_wire_api",
        native_enum=False,
        length=32,
    )
    op.add_column(
        "ai_model_configs",
        sa.Column(
            "wire_api",
            wire_api,
            nullable=False,
            server_default="chat_completions",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_model_configs", "wire_api")
