from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.core.config import settings
from app.models.ai_usage import AIUsageStatus
from app.services.ai_provider import DeepSeekProvider, LLMResponse
from app.services.ai_config_service import (
    EffectiveAIConfig,
    build_openai_default_headers,
    build_openai_extra_body,
    get_effective_config,
    normalize_openai_base_url,
)
from app.services import ai_usage_service


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
_active_ai_config: ContextVar[EffectiveAIConfig | None] = ContextVar(
    "active_ai_config",
    default=None,
)


@contextmanager
def use_ai_config(config: EffectiveAIConfig):
    token = _active_ai_config.set(config)
    try:
        yield
    finally:
        _active_ai_config.reset(token)


def get_chat_model() -> Any | None:
    config = _current_effective_config()
    if _runtime_value(config) != "deepseek":
        return None

    if not config.api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    from langchain_openai import ChatOpenAI

    kwargs = {
        "api_key": config.api_key,
        "base_url": normalize_openai_base_url(config.base_url),
        "model": config.model,
        "temperature": config.temperature,
        "timeout": config.timeout,
        "max_tokens": config.max_tokens,
        "max_retries": getattr(config, "max_retries", 2),
        "default_headers": build_openai_default_headers(),
    }
    extra_body = build_openai_extra_body(config)
    if extra_body:
        kwargs["extra_body"] = extra_body
    return ChatOpenAI(**kwargs)


def is_chat_model_enabled() -> bool:
    try:
        config = _current_effective_config()
    except Exception:
        return settings.AI_RUNTIME == "deepseek"
    return _runtime_value(config) == "deepseek"


def invoke_structured(
    prompt: ChatPromptTemplate,
    output_model: type[StructuredModel],
    variables: Mapping[str, Any],
) -> tuple[StructuredModel, LLMResponse]:
    config = _current_effective_config()
    llm = get_chat_model()
    if llm is None:
        raise RuntimeError("LangChain structured invocation requires active AI runtime=deepseek")

    parser = PydanticOutputParser(pydantic_object=output_model)
    chain = prompt | llm | StrOutputParser()
    prompt_variables = dict(variables)
    prompt_variables.setdefault("format_instructions", parser.get_format_instructions())

    start = time.perf_counter()
    try:
        content = chain.invoke(prompt_variables)
        parsed = parser.parse(content)
    except Exception as exc:
        try:
            parsed, meta = _invoke_structured_with_provider(
                prompt,
                output_model,
                prompt_variables,
                config,
            )
        except Exception as fallback_exc:
            latency_ms = (time.perf_counter() - start) * 1000
            ai_usage_service.record_ai_usage_safely(
                feature="interview_agent",
                runtime=config.runtime,
                provider=config.provider,
                model=config.model,
                status=AIUsageStatus.FAILED,
                latency_ms=round(latency_ms, 2),
                error=f"{exc}; fallback failed: {fallback_exc}"[:1000],
            )
            raise exc
        latency_ms = (time.perf_counter() - start) * 1000
        ai_usage_service.record_ai_usage_safely(
            feature="interview_agent",
            runtime=config.runtime,
            provider=config.provider,
            model=config.model,
            status=AIUsageStatus.OK,
            latency_ms=round(latency_ms, 2),
        )
        return parsed, meta
    latency_ms = (time.perf_counter() - start) * 1000

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


def _runtime_value(config: Any) -> str:
    runtime = getattr(config, "runtime", "mock")
    return runtime.value if hasattr(runtime, "value") else str(runtime)


def _current_effective_config() -> EffectiveAIConfig:
    return _active_ai_config.get() or get_effective_config()


def _invoke_structured_with_provider(
    prompt: ChatPromptTemplate,
    output_model: type[StructuredModel],
    variables: Mapping[str, Any],
    config: EffectiveAIConfig,
) -> tuple[StructuredModel, LLMResponse]:
    system, user = _format_prompt_for_provider(prompt, variables)
    payload, meta = DeepSeekProvider(config).chat_json(
        system,
        user,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    return output_model.model_validate(payload), meta


def _format_prompt_for_provider(
    prompt: ChatPromptTemplate,
    variables: Mapping[str, Any],
) -> tuple[str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []
    for message in prompt.format_messages(**dict(variables)):
        content = _message_content_to_text(getattr(message, "content", ""))
        role = getattr(message, "type", "human")
        if role == "system":
            system_parts.append(content)
        else:
            user_parts.append(content)
    return "\n\n".join(system_parts), "\n\n".join(user_parts)


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text") is not None:
                parts.append(str(item["text"]))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)
