from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, TypeVar

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.models.ai_usage import AIUsageStatus
from app.services.ai_provider import LLMResponse
from app.services.ai_config_service import get_effective_config
from app.services import ai_usage_service


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
    config = get_effective_config()
    llm = get_chat_model()
    if llm is None:
        raise RuntimeError("LangChain structured invocation requires AI_RUNTIME=deepseek")

    parser = PydanticOutputParser(pydantic_object=output_model)
    chain = prompt | llm | StrOutputParser()
    prompt_variables = dict(variables)
    prompt_variables.setdefault("format_instructions", parser.get_format_instructions())

    start = time.perf_counter()
    try:
        content = chain.invoke(prompt_variables)
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        ai_usage_service.record_ai_usage_safely(
            feature="interview_agent",
            runtime=config.runtime,
            provider=config.provider,
            model=config.model,
            status=AIUsageStatus.FAILED,
            latency_ms=round(latency_ms, 2),
            error=str(exc)[:1000],
        )
        raise
    latency_ms = (time.perf_counter() - start) * 1000

    parsed = parser.parse(content)
    ai_usage_service.record_ai_usage_safely(
        feature="interview_agent",
        runtime=config.runtime,
        provider=config.provider,
        model=config.model,
        status=AIUsageStatus.OK,
        latency_ms=round(latency_ms, 2),
    )
    return parsed, LLMResponse(
        content=content,
        latency_ms=round(latency_ms, 2),
        model=config.model,
    )
