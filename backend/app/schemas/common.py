"""通用 schema：分页、消息、ID 引用。"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class Message(BaseModel):
    message: str
    code: str = "OK"


class IdResponse(BaseModel):
    id: int


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20

    @classmethod
    def of(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        return cls(items=items, total=total, page=page, page_size=page_size)


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
