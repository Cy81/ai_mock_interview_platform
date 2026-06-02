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
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings


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

    def __init__(self) -> None:
        from openai import OpenAI
        import httpx

        if not settings.DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.AI_TIMEOUT,
                write=10.0,
                pool=5.0,
            ),
            max_retries=0,  # 重试交给 tenacity，行为可控
        )
        self.model = settings.DEEPSEEK_MODEL

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
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": settings.AI_TEMPERATURE if temperature is None else temperature,
            "max_tokens": settings.AI_MAX_TOKENS if max_tokens is None else max_tokens,
        }
        if json_mode and not stream:
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        return self.client.chat.completions.create(**kwargs)

    @retry(
        reraise=True,
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(settings.AI_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=8),
    )
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
        content = response.choices[0].message.content or "{}"
        parsed = _parse_json_safely(content)
        usage = LLMUsage(
            prompt_tokens=getattr(response.usage, "prompt_tokens", 0),
            completion_tokens=getattr(response.usage, "completion_tokens", 0),
            total_tokens=getattr(response.usage, "total_tokens", 0),
        )
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


def get_ai_provider() -> AIProvider:
    """工厂方法，根据 settings.AI_RUNTIME 选择实现。"""
    global _provider_singleton
    if _provider_singleton is not None:
        return _provider_singleton
    if settings.AI_RUNTIME == "deepseek":
        _provider_singleton = DeepSeekProvider()
    else:
        _provider_singleton = MockAIProvider()
    return _provider_singleton


def reset_ai_provider() -> None:
    """测试用：重置单例。"""
    global _provider_singleton
    _provider_singleton = None
