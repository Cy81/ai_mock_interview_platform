from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, TypeVar

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.core.config import settings
from app.services.ai_provider import LLMResponse
from app.services.ai_config_service import get_effective_config


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def get_chat_model() -> Any | None:
    config = get_effective_config()
    if config.runtime.value != "deepseek":
        return None

    if not config.api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=config.temperature,
        timeout=config.timeout,
        max_tokens=config.max_tokens,
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
        model=get_effective_config().model,
    )
