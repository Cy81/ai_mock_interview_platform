from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def _to_jsonable(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    return data


def format_sse(event: str, data: Any) -> str:
    payload = json.dumps(_to_jsonable(data), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def error_event(message: str, *, stage: str, interview_id: int | None = None) -> str:
    return format_sse(
        "error",
        {"message": message, "stage": stage, "interview_id": interview_id},
    )
