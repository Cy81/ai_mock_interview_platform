"""AI 服务层：DeepSeek（OpenAI 兼容）/ Mock 双实现。

设计要点：
- `tenacity` 指数退避重试，明确重试 5xx / 网络错误，不重试 4xx；
- `httpx.Timeout` 严格控制连接 / 读取超时，避免 Worker 卡死；
- 强制 `response_format=json_object`（DeepSeek 支持），对 JSON 解析做兜底；
- 统一返回 `LLMResponse(content, usage, latency_ms)`，便于上层做费用统计 / 监控；
- 提供同步与流式两种调用入口，流式给"答题中实时反馈"使用。
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator

import structlog
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.models.ai_config import AIProvider as ModelAIProvider
from app.models.ai_config import AIRuntime, AIWireAPI
from app.services.ai_config_service import (
    EffectiveAIConfig,
    build_openai_default_headers,
    build_openai_extra_body,
    build_openai_responses_url,
    get_effective_config,
    normalize_openai_base_url,
)


logger = structlog.get_logger("ai")


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def merge(self, other: "LLMUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


@dataclass
class LLMResponse:
    content: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: float = 0.0
    model: str = ""


class AIProvider(ABC):
    @abstractmethod
    def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[Any, LLMResponse]:
        """返回结构化 JSON 与底层 usage 元数据。"""

    @abstractmethod
    def chat_stream(self, system: str, user: str) -> Iterator[str]:
        """流式返回纯文本片段。"""

    @abstractmethod
    def parse_resume(self, text: str) -> tuple[dict[str, Any], LLMResponse]:
        ...

    @abstractmethod
    def generate_interview_questions(
        self,
        job_title: str,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        count: int,
    ) -> tuple[list[dict[str, Any]], LLMResponse]:
        ...

    @abstractmethod
    def score_interview(
        self,
        job_title: str,
        profile: dict[str, Any],
        question_answers: list[dict[str, Any]],
        knowledge_contexts: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], LLMResponse]:
        ...


# ======================================================================
# DeepSeek 实现
# ======================================================================


class DeepSeekProvider(AIProvider):
    """基于 OpenAI Compatible SDK 的 DeepSeek 实现。"""

    def __init__(self, config: EffectiveAIConfig | None = None) -> None:
        from openai import OpenAI
        import httpx

        self.config = config or _load_effective_config()
        if not self.config.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        timeout = httpx.Timeout(
            connect=10.0,
            read=self.config.timeout,
            write=10.0,
            pool=5.0,
        )
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=normalize_openai_base_url(self.config.base_url),
            default_headers=build_openai_default_headers(),
            timeout=timeout,
            max_retries=0,  # 重试交给 tenacity，行为可控
        )
        self.http_client = httpx.Client(timeout=timeout)
        self.model = self.config.model
        self.temperature = self.config.temperature
        self.max_tokens = self.config.max_tokens
        self.max_retries = max(1, self.config.max_retries)
        self.wire_api = _wire_api_value(self.config)
        self.responses_url = build_openai_responses_url(self.config.base_url)
        self.extra_body = build_openai_extra_body(self.config)

    # ---------- 基础调用 ----------
    def _invoke(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = True,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ):
        if self.wire_api == AIWireAPI.RESPONSES.value and not stream:
            return self._invoke_responses(
                system,
                user,
                json_mode=json_mode,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        if json_mode and not stream:
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        return self.client.chat.completions.create(**kwargs)

    def _invoke_responses(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user}],
                },
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_output_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        if json_mode:
            payload["text"] = {"format": {"type": "json_object"}}
        response = self.http_client.post(
            self.responses_url,
            json=payload,
            headers={
                **build_openai_default_headers(),
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Responses API returned non-object payload")
        return data

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[Any, LLMResponse]:
        start = time.perf_counter()
        try:
            for attempt in Retrying(
                reraise=True,
                retry=retry_if_exception_type(Exception),
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=8),
            ):
                with attempt:
                    response = self._invoke(
                        system, user,
                        json_mode=True,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
        except Exception:
            logger.exception("ai_call_failed", model=self.model)
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        content = _extract_response_content(response)
        parsed = _parse_json_safely(content)
        usage = _extract_response_usage(response)
        meta = LLMResponse(
            content=content,
            usage=usage,
            latency_ms=round(latency_ms, 2),
            model=self.model,
        )
        logger.info(
            "ai_call_success",
            model=self.model,
            latency_ms=meta.latency_ms,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
        return parsed, meta

    def chat_stream(self, system: str, user: str) -> Iterator[str]:
        response = self._invoke(system, user, json_mode=False, stream=True)
        if isinstance(response, str):
            yield response
            return
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text

    # ---------- 业务调用 ----------
    def parse_resume(self, text: str) -> tuple[dict[str, Any], LLMResponse]:
        system = (
            "你是简历解析专家。请只返回严格 JSON，字段为："
            "name(str), years(int), skills(list[str]), projects(list[str]), "
            "highlights(list[str]), summary(str), risk_flags(list[str])。"
            "若信息缺失，给出合理的空值或空数组。"
        )
        user = f"请解析以下简历文本，并返回 JSON：\n\n{text[:8000]}"
        return self.chat_json(system, user, temperature=0.1)

    def generate_interview_questions(
        self,
        job_title: str,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        count: int,
    ) -> tuple[list[dict[str, Any]], LLMResponse]:
        system = (
            "你是资深技术面试官。请基于岗位、能力模型、候选人画像与题库片段，"
            "出 {count} 道结构化面试题。只返回 JSON：{{\"questions\":[...]}}。"
            "每道题字段：position(int), type(technical|project|system_design|behavioral), "
            "difficulty(basic|intermediate|advanced), skill(str), question(str), "
            "rubric(list[str], 3 条评分要点), reference_chunk_ids(list[int])。"
        ).format(count=count)
        user = json.dumps(
            {
                "job_title": job_title,
                "job_competency": job_competency,
                "profile": profile,
                "question_count": count,
                "context_chunks": contexts,
            },
            ensure_ascii=False,
        )
        result, meta = self.chat_json(system, user, temperature=0.4)
        questions = result.get("questions") if isinstance(result, dict) else result
        return list(questions or []), meta

    def score_interview(
        self,
        job_title: str,
        profile: dict[str, Any],
        question_answers: list[dict[str, Any]],
        knowledge_contexts: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], LLMResponse]:
        system = (
            "你是严谨的技术面试评估官。请只返回 JSON 报告："
            "overall_score(0-100, float), level(强匹配|可培养|需要继续准备), "
            "dimension_scores(dict, 至少包含 技术准确性/项目表达/工程化意识/岗位匹配), "
            "question_scores(list of {position,score,comment}), "
            "strengths(list[str]), improvements(list[str]), learning_plan(list[str])。"
        )
        user = json.dumps(
            {
                "job_title": job_title,
                "profile": profile,
                "qa_pairs": question_answers,
                "knowledge_contexts": knowledge_contexts,
            },
            ensure_ascii=False,
        )
        return self.chat_json(system, user, temperature=0.2, max_tokens=2400)


# ======================================================================
# Mock 实现：保证课程在无 API Key 时也能跑通
# ======================================================================


class MockAIProvider(AIProvider):
    SKILL_ALIASES = {
        "python": "Python", "fastapi": "FastAPI", "sqlalchemy": "SQLAlchemy",
        "postgres": "PostgreSQL", "pgvector": "pgvector", "redis": "Redis",
        "celery": "Celery", "rag": "RAG", "langchain": "LangChain", "vue": "Vue",
        "docker": "Docker", "linux": "Linux", "pytest": "pytest", "pandas": "Pandas",
        "numpy": "NumPy", "kafka": "Kafka", "k8s": "Kubernetes", "kubernetes": "Kubernetes",
        "agent": "Agent", "embedding": "Embedding", "deepseek": "DeepSeek",
        "机器学习": "机器学习", "深度学习": "深度学习", "数据分析": "数据分析",
    }

    def chat_json(self, system, user, *, temperature=None, max_tokens=None):
        return {"mock": True, "system": system[:80], "user": user[:80]}, LLMResponse(
            content="{}", model="mock"
        )

    def chat_stream(self, system: str, user: str):
        for chunk in ("【Mock】", "AI ", "正在", "回答……"):
            yield chunk

    # -- 简历解析 --
    def parse_resume(self, text: str) -> tuple[dict[str, Any], LLMResponse]:
        lowered = text.lower()
        skills = sorted({label for k, label in self.SKILL_ALIASES.items() if k in lowered or k in text})
        years_match = re.search(r"(\d+)\s*(?:年|years?)", text, re.IGNORECASE)
        years = int(years_match.group(1)) if years_match else 1
        projects = re.findall(r"(?:项目|Project)[:：]\s*(.+)", text, re.IGNORECASE)
        highlights = re.findall(r"(?:负责|实现|优化|设计|搭建).{0,45}", text)
        profile = {
            "name": _extract_name(text),
            "years": years,
            "skills": skills or ["Python", "FastAPI", "SQL"],
            "projects": projects[:5] or ["建议补充 STAR 结构项目描述"],
            "highlights": highlights[:6] or ["具备后端与 AI 应用学习基础"],
            "summary": (
                f"候选人具备 {years} 年左右经验，核心技能："
                f"{', '.join(skills[:8]) if skills else 'Python/FastAPI/SQL'}。"
            ),
            "risk_flags": _resume_risk_flags(text, skills),
        }
        return profile, LLMResponse(content=json.dumps(profile, ensure_ascii=False), model="mock")

    # -- 出题 --
    def generate_interview_questions(
        self,
        job_title: str,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        count: int,
    ) -> tuple[list[dict[str, Any]], LLMResponse]:
        skills = profile.get("skills") or ["Python", "FastAPI", "数据库"]
        ctx_texts = [c["content"] for c in contexts]
        types = ["technical", "project", "system_design", "behavioral"]
        difficulties = ["basic", "intermediate", "advanced"]
        questions: list[dict[str, Any]] = []
        for i in range(count):
            skill = skills[i % len(skills)]
            ctx = ctx_texts[i % len(ctx_texts)] if ctx_texts else ""
            base = _question_from_context(ctx) or (
                f"请结合你的项目经验，说明 {skill} 在 {job_title} 中的关键应用与取舍。"
            )
            ref_ids = [contexts[i % len(contexts)]["id"]] if contexts else []
            questions.append(
                {
                    "position": i + 1,
                    "type": types[i % 4],
                    "difficulty": difficulties[min(i // 2, 2)],
                    "skill": skill,
                    "question": base,
                    "rubric": [
                        "能准确解释核心概念与原理",
                        "能结合真实项目讲清取舍与量化结果",
                        "能覆盖异常处理 / 性能 / 安全 / 可维护性等工程化维度",
                    ],
                    "reference_chunk_ids": ref_ids,
                }
            )
        return questions, LLMResponse(content="[mock]", model="mock")

    # -- 评分 --
    def score_interview(
        self,
        job_title: str,
        profile: dict[str, Any],
        question_answers: list[dict[str, Any]],
        knowledge_contexts: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], LLMResponse]:
        details: list[dict[str, Any]] = []
        for qa in question_answers:
            answer = qa.get("answer", "") or ""
            length_score = min(len(answer) / 120, 1.0)
            keyword_hits = sum(
                1 for kw in ["原因", "方案", "权衡", "测试", "性能", "安全", "监控"] if kw in answer
            )
            score = round(55 + 35 * length_score + 5 * keyword_hits, 1) if answer else 35.0
            score = min(score, 96)
            details.append(
                {
                    "position": qa["position"],
                    "score": score,
                    "comment": "回答覆盖关键点" if score >= 75 else "回答偏简略，建议补充项目细节与工程化取舍",
                }
            )
        avg = round(sum(d["score"] for d in details) / max(len(details), 1), 1)
        report = {
            "job_title": job_title,
            "overall_score": avg,
            "level": "强匹配" if avg >= 82 else "可培养匹配" if avg >= 68 else "需要继续准备",
            "dimension_scores": {
                "技术准确性": avg,
                "项目表达": max(45, min(95, avg - 4)),
                "工程化意识": max(45, min(95, avg - 2)),
                "岗位匹配": max(45, min(95, avg + 3)),
            },
            "question_scores": details,
            "strengths": [
                f"简历技能与 {job_title} 有基础关联",
                "能围绕问题给出结构化回答" if avg >= 68 else "已完成面试闭环，可继续迭代回答质量",
            ],
            "improvements": _missing_keywords(question_answers),
            "learning_plan": _learning_plan(question_answers, knowledge_contexts),
        }
        return report, LLMResponse(content=json.dumps(report, ensure_ascii=False), model="mock")


# ======================================================================
# 工具函数
# ======================================================================


def _parse_json_safely(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", content, re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        logger.warning("ai_response_invalid_json", preview=content[:200])
        return {}


def _extract_response_content(response: Any) -> str:
    if isinstance(response, str):
        return response or "{}"
    if isinstance(response, dict):
        return _extract_content_from_mapping(response)

    choices = getattr(response, "choices", None)
    if choices:
        first = choices[0]
        message = getattr(first, "message", None)
        content = getattr(message, "content", None)
        if content is not None:
            return _content_to_text(content)

    output_text = getattr(response, "output_text", None)
    if output_text is not None:
        return _content_to_text(output_text)

    if hasattr(response, "model_dump"):
        try:
            dumped = response.model_dump()
            if isinstance(dumped, dict):
                return _extract_content_from_mapping(dumped)
        except Exception:
            pass
    return "{}"


def _extract_content_from_mapping(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message") or {}
            if isinstance(message, dict) and message.get("content") is not None:
                return _content_to_text(message["content"])

    if payload.get("output_text") is not None:
        return _content_to_text(payload["output_text"])

    output = payload.get("output")
    if isinstance(output, list):
        text_parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("text") is not None:
                        text_parts.append(str(part["text"]))
            elif content is not None:
                text_parts.append(_content_to_text(content))
        if text_parts:
            return "".join(text_parts)

    if payload.get("content") is not None:
        return _content_to_text(payload["content"])
    return json.dumps(payload, ensure_ascii=False)


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content or "{}"
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text") is not None:
                parts.append(str(item["text"]))
            elif item is not None:
                parts.append(str(item))
        return "".join(parts) or "{}"
    return str(content) if content is not None else "{}"


def _extract_response_usage(response: Any) -> LLMUsage:
    usage = None
    if isinstance(response, dict):
        usage = response.get("usage")
    elif not isinstance(response, str):
        usage = getattr(response, "usage", None)

    prompt_tokens = _usage_int(usage, "prompt_tokens", "input_tokens")
    completion_tokens = _usage_int(usage, "completion_tokens", "output_tokens")
    total_tokens = _usage_int(usage, "total_tokens")
    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens
    return LLMUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _usage_int(usage: Any, *keys: str) -> int:
    if not usage:
        return 0
    for key in keys:
        value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return 0


def _extract_name(text: str) -> str:
    m = re.search(r"(?:姓名|Name)[:：]\s*([一-龥A-Za-z ]{2,20})", text)
    return m.group(1).strip() if m else "候选人"


def _resume_risk_flags(text: str, skills: list[str]) -> list[str]:
    flags = []
    if len(text) < 200:
        flags.append("简历文本偏短，岗位匹配置信度会下降")
    if len(skills) < 4:
        flags.append("技能关键词较少，建议补充技术栈、项目职责和量化结果")
    return flags


def _question_from_context(ctx: str) -> str | None:
    if not ctx:
        return None
    line = ctx.strip().splitlines()[0]
    line = re.sub(r"^[-*\d.、\s]+", "", line)
    return line if len(line) >= 8 else None


def _missing_keywords(qa_pairs: list[dict[str, Any]]) -> list[str]:
    joined = "\n".join(p.get("answer", "") for p in qa_pairs)
    checks = {
        "补充可观测性：日志、指标、链路追踪如何落地": "监控",
        "补充测试策略：单元测试、集成测试和 Mock 边界": "测试",
        "补充生产故障处理：超时、重试、降级和幂等": "降级",
        "补充安全意识：权限、输入校验和敏感信息保护": "安全",
    }
    return [tip for tip, kw in checks.items() if kw not in joined][:4]


def _learning_plan(qa_pairs, contexts) -> list[str]:
    base = [
        "复盘每道题，按 STAR（背景-任务-行动-结果）结构重写答案",
        "把简历项目补充为可量化指标，例如响应时间、吞吐、召回率或成本",
    ]
    base.extend(_missing_keywords(qa_pairs)[:3])
    base.extend(f"阅读知识库：{c['title']}" for c in contexts[:2])
    return base


_provider_singleton: AIProvider | None = None
_provider_signature: tuple[object, ...] | None = None


def get_ai_provider() -> AIProvider:
    """工厂方法，根据后台生效 AI 配置选择实现。"""
    global _provider_singleton, _provider_signature
    config = _load_effective_config()
    signature = _config_signature(config)
    if _provider_singleton is not None and _provider_signature == signature:
        return _provider_singleton
    if _runtime_value(config) == AIRuntime.DEEPSEEK.value:
        _provider_singleton = DeepSeekProvider(config)
    else:
        _provider_singleton = MockAIProvider()
    _provider_signature = signature
    return _provider_singleton


def reset_ai_provider() -> None:
    """测试用：重置单例。"""
    global _provider_singleton, _provider_signature
    _provider_singleton = None
    _provider_signature = None


def _load_effective_config() -> EffectiveAIConfig:
    try:
        return get_effective_config()
    except Exception as exc:  # pragma: no cover - fallback for scripts before DB init
        logger.warning("ai_config_load_failed_fallback_settings", error=str(exc)[:300])
        return _fallback_effective_config()


def _fallback_effective_config() -> EffectiveAIConfig:
    if settings.AI_RUNTIME == AIRuntime.DEEPSEEK.value:
        return EffectiveAIConfig(
            id=None,
            name="Environment DeepSeek",
            runtime=AIRuntime.DEEPSEEK,
            provider=ModelAIProvider.DEEPSEEK,
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY or "",
            model=settings.DEEPSEEK_MODEL,
            wire_api=AIWireAPI.CHAT_COMPLETIONS,
            temperature=settings.AI_TEMPERATURE,
            max_tokens=settings.AI_MAX_TOKENS,
            timeout=settings.AI_TIMEOUT,
            max_retries=settings.AI_MAX_RETRIES,
        )
    return EffectiveAIConfig(
        id=None,
        name="Local Mock",
        runtime=AIRuntime.MOCK,
        provider=ModelAIProvider.MOCK,
        base_url="",
        api_key="",
        model="mock-interview",
        wire_api=AIWireAPI.CHAT_COMPLETIONS,
        temperature=settings.AI_TEMPERATURE,
        max_tokens=settings.AI_MAX_TOKENS,
        timeout=settings.AI_TIMEOUT,
        max_retries=settings.AI_MAX_RETRIES,
    )


def _config_signature(config: EffectiveAIConfig) -> tuple[object, ...]:
    return (
        config.id,
        _runtime_value(config),
        _provider_value(config),
        config.base_url,
        config.api_key,
        config.model,
        _wire_api_value(config),
        config.temperature,
        config.max_tokens,
        config.timeout,
        config.max_retries,
    )


def _runtime_value(config: EffectiveAIConfig) -> str:
    runtime = getattr(config, "runtime", AIRuntime.MOCK)
    return runtime.value if hasattr(runtime, "value") else str(runtime)


def _provider_value(config: EffectiveAIConfig) -> str:
    provider = getattr(config, "provider", ModelAIProvider.MOCK)
    return provider.value if hasattr(provider, "value") else str(provider)


def _wire_api_value(config: EffectiveAIConfig) -> str:
    wire_api = getattr(config, "wire_api", AIWireAPI.CHAT_COMPLETIONS)
    return wire_api.value if hasattr(wire_api, "value") else str(wire_api)
