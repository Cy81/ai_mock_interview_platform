"""Embedding 服务层：DashScope（OpenAI 兼容）/ Mock。

设计要点：
- batch 切分（DashScope text-embedding-v3/v4 单次最多 25 条）；
- 指数退避重试 + 严格超时；
- 用 numpy 做归一化与余弦相似度，性能远好于纯 Python；
- 单例缓存，避免重复创建 SDK 客户端。
"""
from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings


logger = structlog.get_logger("embedding")


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        ...


# ======================================================================


class DashScopeEmbeddingProvider(EmbeddingProvider):
    """阿里云 DashScope (兼容 OpenAI 协议) Embedding。"""

    BATCH_LIMIT = 10  # 兼容多种版本的安全值

    def __init__(self) -> None:
        from openai import OpenAI
        import httpx

        if not settings.DASHSCOPE_API_KEY:
            raise RuntimeError("DASHSCOPE_API_KEY 未配置")
        self.client = OpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.DASHSCOPE_BASE_URL,
            timeout=httpx.Timeout(connect=10.0, read=settings.EMBEDDING_TIMEOUT, write=10.0, pool=5.0),
            max_retries=0,
        )
        self.model = settings.DASHSCOPE_EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIMENSIONS
        self.batch_size = min(settings.EMBEDDING_BATCH_SIZE, self.BATCH_LIMIT)

    @retry(
        reraise=True,
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(settings.EMBEDDING_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=8),
    )
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model,
            input=batch,
            dimensions=self.dim,
            encoding_format="float",
        )
        return [item.embedding for item in response.data]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned = [t if t and t.strip() else "·" for t in texts]
        out: list[list[float]] = []
        start = time.perf_counter()
        for i in range(0, len(cleaned), self.batch_size):
            batch = cleaned[i : i + self.batch_size]
            try:
                out.extend(self._embed_batch(batch))
            except Exception:
                logger.exception("embedding_batch_failed", batch_index=i, batch_size=len(batch))
                raise
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "embedding_batch_done",
            count=len(cleaned),
            dim=self.dim,
            latency_ms=latency_ms,
        )
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


# ======================================================================


class MockEmbeddingProvider(EmbeddingProvider):
    """确定性 hash embedding，保证 chunk 相同向量相同（便于离线测试与课程演示）。"""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        dim = settings.EMBEDDING_DIMENSIONS
        vec = np.zeros(dim, dtype=np.float32)
        if not text:
            text = "·"
        # bigram + trigram，简单可用
        tokens = [text[i : i + 2] for i in range(max(len(text) - 1, 1))]
        tokens.extend(text[i : i + 3] for i in range(max(len(text) - 2, 1)))
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


# ======================================================================


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    a = np.asarray(left, dtype=np.float32)
    b = np.asarray(right, dtype=np.float32)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


_provider_singleton: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton
    if settings.EMBEDDING_RUNTIME == "dashscope":
        _provider_singleton = DashScopeEmbeddingProvider()
    else:
        _provider_singleton = MockEmbeddingProvider()
    return _provider_singleton


def reset_embedding_provider() -> None:
    global _provider_singleton
    _provider_singleton = None
