"""简历相关 Schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.resume import ResumeParseStatus


class ResumeTextCreate(BaseModel):
    filename: str = Field(default="manual-input.txt", min_length=1, max_length=255)
    text: str = Field(min_length=20, max_length=200_000)
    target_position: str | None = Field(default=None, max_length=120)


class ResumeRead(BaseModel):
    id: int
    filename: str
    mime_type: str | None = None
    file_size: int
    content_hash: str | None = None
    raw_text: str
    parsed_profile: dict[str, Any]
    target_position: str | None = None
    parse_status: ResumeParseStatus
    parse_error: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResumeBrief(BaseModel):
    id: int
    filename: str
    parse_status: ResumeParseStatus
    target_position: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
