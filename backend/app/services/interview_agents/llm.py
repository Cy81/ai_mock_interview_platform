from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, TypeVar

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.core.config import settings
from app.services.ai_provider import LLMResponse


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def get_chat_model() -> Any | None:
    if settings.AI_RUNTIME != "deepseek":
        return None

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_MODEL,
        temperature=settings.AI_TEMPERATURE,
        timeout=settings.AI_TIMEOUT,
        max_tokens=settings.AI_MAX_TOKENS,
    )


def invoke_structured(
    prompt: ChatPromptTemplate,
    output_model: type[StructuredModel],
    variables: Mapping[str, Any],
) -> tuple[StructuredModel, LLMResponse]:
    llm = get_chat_model()
    if llm is None:
        raise RuntimeError("LangChain structured invocation requires AI_RUNTIME=deepseek")

    parser = PydanticOutputParser(pydantic_object=output_model)
    chain = prompt | llm | StrOutputParser()
    prompt_variables = dict(variables)
    prompt_variables.setdefault("format_instructions", parser.get_format_instructions())

    start = time.perf_counter()
    content = chain.invoke(prompt_variables)
    latency_ms = (time.perf_counter() - start) * 1000

    parsed = parser.parse(content)
    return parsed, LLMResponse(
        content=content,
        latency_ms=round(latency_ms, 2),
        model=settings.DEEPSEEK_MODEL,
    )
