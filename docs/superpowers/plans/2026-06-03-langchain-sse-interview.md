# LangChain SSE Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LangChain-based interview agent layer and structured SSE stream so the existing mock interview flow supports AI follow-up, scoring progress, and report-ready events.

**Architecture:** Add a focused `interview_agents` service package for LangChain prompts, structured models, deterministic mock chains, and SSE formatting. Keep `interview_service` responsible for ownership checks, status transitions, persistence, and compatibility with existing endpoints.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, LangChain 0.3.x, langchain-openai, Vue 3, Element Plus, fetch streaming, pytest.

---

## File Structure

- Create `backend/app/services/interview_agents/__init__.py`: public exports for runtime and SSE helpers.
- Create `backend/app/services/interview_agents/models.py`: Pydantic models for plans, generated questions, follow-up, scoring, report, and SSE payloads.
- Create `backend/app/services/interview_agents/events.py`: JSON SSE formatting and stream-safe error events.
- Create `backend/app/services/interview_agents/llm.py`: LangChain ChatModel factory and structured invocation helper.
- Create `backend/app/services/interview_agents/planner.py`: `InterviewPlannerAgent`.
- Create `backend/app/services/interview_agents/question_generator.py`: `QuestionGenerationAgent`.
- Create `backend/app/services/interview_agents/followup.py`: `FollowupAgent`.
- Create `backend/app/services/interview_agents/scoring.py`: `ScoringAgent`.
- Create `backend/app/services/interview_agents/report.py`: `ReportAgent`.
- Create `backend/app/services/interview_agents/runtime.py`: orchestration facade used by services and API routes.
- Modify `backend/app/services/interview_service.py`: call the runtime for question generation and scoring/report generation.
- Modify `backend/app/api/v1/interviews.py`: add `GET /api/v1/interviews/{interview_id}/stream`.
- Create `backend/tests/test_interview_agents.py`: unit tests for models, SSE formatting, and mock runtime.
- Create `backend/tests/test_interview_stream.py`: API tests for follow-up SSE and scoring SSE.
- Modify `frontend/src/api/client.js`: export base URL and auth headers for non-Axios streaming calls.
- Modify `frontend/src/api/modules.js`: add `interviewApi.stream`.
- Modify `frontend/src/views/MockInterview.vue`: display AI feedback and consume SSE after answer submission.

---

### Task 1: Agent Models And SSE Formatting

**Files:**
- Create: `backend/app/services/interview_agents/__init__.py`
- Create: `backend/app/services/interview_agents/models.py`
- Create: `backend/app/services/interview_agents/events.py`
- Create: `backend/tests/test_interview_agents.py`

- [ ] **Step 1: Write failing model and SSE tests**

Create `backend/tests/test_interview_agents.py` with:

```python
from __future__ import annotations

import json

from app.services.interview_agents.events import format_sse
from app.services.interview_agents.models import (
    FollowupAction,
    FollowupResult,
    GeneratedQuestion,
    InterviewPlan,
    ScoreResult,
)


def test_format_sse_serializes_json_payload() -> None:
    event = format_sse(
        "followup_delta",
        {"interview_id": 7, "question_id": 11, "content": "继续说明项目取舍"},
    )

    assert event.startswith("event: followup_delta\n")
    assert event.endswith("\n\n")
    payload = json.loads(event.split("data: ", 1)[1])
    assert payload["interview_id"] == 7
    assert payload["content"] == "继续说明项目取舍"


def test_agent_models_validate_core_shapes() -> None:
    plan = InterviewPlan(
        target_type="formal",
        difficulty="intermediate",
        core_skills=["FastAPI", "RAG"],
        question_mix={"technical": 2, "project": 1},
        style="structured",
        notes=["关注工程化表达"],
    )
    question = GeneratedQuestion(
        position=1,
        type="technical",
        difficulty="intermediate",
        skill="FastAPI",
        question="请说明 FastAPI 依赖注入在项目中的使用方式。",
        rubric=["解释原理", "结合项目", "说明测试"],
        reference_chunk_ids=[1, 2],
    )
    followup = FollowupResult(
        action=FollowupAction.COMMENT,
        content="回答覆盖了核心点，可以补充监控和降级策略。",
        confidence=0.82,
        suggested_next_position=2,
    )
    score = ScoreResult(
        overall_score=82.5,
        level="可培养匹配",
        dimension_scores={"技术准确性": 82.5},
        question_scores=[{"position": 1, "score": 82.5, "comment": "结构清晰"}],
        strengths=["表达有条理"],
        improvements=["补充异常处理"],
        learning_plan=["复盘项目指标"],
    )

    assert plan.core_skills == ["FastAPI", "RAG"]
    assert question.reference_chunk_ids == [1, 2]
    assert followup.action == FollowupAction.COMMENT
    assert score.overall_score == 82.5
```

- [ ] **Step 2: Run test and verify it fails**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_agents.py -q
```

Expected result: import failure for `app.services.interview_agents`.

- [ ] **Step 3: Add package exports**

Create `backend/app/services/interview_agents/__init__.py`:

```python
"""LangChain interview agent package."""

from app.services.interview_agents.events import format_sse

__all__ = ["format_sse"]
```

- [ ] **Step 4: Add Pydantic models**

Create `backend/app/services/interview_agents/models.py`:

```python
from __future__ import annotations

import enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


QuestionKind = Literal["technical", "project", "system_design", "behavioral"]
DifficultyLevel = Literal["basic", "intermediate", "advanced"]
TargetType = Literal["intern", "formal"]


class FollowupAction(str, enum.Enum):
    FOLLOWUP = "followup"
    COMMENT = "comment"
    NEXT_QUESTION_HINT = "next_question_hint"


class InterviewPlan(BaseModel):
    target_type: TargetType
    difficulty: DifficultyLevel
    core_skills: list[str] = Field(default_factory=list)
    question_mix: dict[str, int] = Field(default_factory=dict)
    style: str = "structured"
    notes: list[str] = Field(default_factory=list)

    @field_validator("core_skills")
    @classmethod
    def limit_core_skills(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()][:8]


class GeneratedQuestion(BaseModel):
    position: int = Field(ge=1)
    type: QuestionKind = "technical"
    difficulty: DifficultyLevel = "intermediate"
    skill: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=6)
    rubric: list[str] = Field(default_factory=list)
    reference_chunk_ids: list[int] = Field(default_factory=list)

    @field_validator("rubric")
    @classmethod
    def limit_rubric(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()][:6]


class QuestionGenerationResult(BaseModel):
    plan: InterviewPlan
    questions: list[GeneratedQuestion]


class FollowupResult(BaseModel):
    action: FollowupAction
    content: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    suggested_next_position: int | None = Field(default=None, ge=1)


class ScoreResult(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    level: str
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    question_scores: list[dict[str, object]] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    learning_plan: list[str] = Field(default_factory=list)


class ReportResult(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    level: str
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    question_scores: list[dict[str, object]] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    learning_plan: list[str] = Field(default_factory=list)
    next_practice: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Add SSE formatter**

Create `backend/app/services/interview_agents/events.py`:

```python
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
```

- [ ] **Step 6: Run test and verify it passes**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_agents.py -q
```

Expected result: `2 passed`.

- [ ] **Step 7: Commit task 1**

```powershell
git add backend/app/services/interview_agents backend/tests/test_interview_agents.py
git commit -m "Add interview agent models and SSE formatter"
```

---

### Task 2: LangChain Runtime For Planning And Question Generation

**Files:**
- Create: `backend/app/services/interview_agents/llm.py`
- Create: `backend/app/services/interview_agents/planner.py`
- Create: `backend/app/services/interview_agents/question_generator.py`
- Create: `backend/app/services/interview_agents/runtime.py`
- Modify: `backend/tests/test_interview_agents.py`

- [ ] **Step 1: Add failing mock runtime test**

Append to `backend/tests/test_interview_agents.py`:

```python
from app.services.interview_agents.runtime import get_interview_agent_runtime


def test_mock_runtime_generates_questions_with_langchain_facade() -> None:
    runtime = get_interview_agent_runtime()
    questions, meta = runtime.generate_interview_questions(
        job_title="AI 应用工程师",
        job_competency={"skills": ["FastAPI", "RAG"]},
        profile={"years": 1, "skills": ["FastAPI", "LangChain"]},
        contexts=[{"id": 101, "title": "FastAPI 题库", "content": "请解释依赖注入。"}],
        count=3,
    )

    assert meta.model == "langchain-mock"
    assert len(questions) == 3
    assert questions[0]["position"] == 1
    assert questions[0]["skill"] in {"FastAPI", "LangChain"}
    assert questions[0]["rubric"]
```

- [ ] **Step 2: Run test and verify it fails**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_agents.py::test_mock_runtime_generates_questions_with_langchain_facade -q
```

Expected result: import failure for `runtime` or missing method failure.

- [ ] **Step 3: Add LangChain LLM helper**

Create `backend/app/services/interview_agents/llm.py`:

```python
from __future__ import annotations

import time
from typing import Any, TypeVar

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.core.config import settings
from app.services.ai_provider import LLMResponse


TModel = TypeVar("TModel", bound=BaseModel)


def get_chat_model():
    if settings.AI_RUNTIME != "deepseek":
        return None
    from langchain_openai import ChatOpenAI

    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return ChatOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_MODEL,
        temperature=settings.AI_TEMPERATURE,
        timeout=settings.AI_TIMEOUT,
        max_tokens=settings.AI_MAX_TOKENS,
    )


def invoke_structured(
    *,
    prompt: ChatPromptTemplate,
    output_model: type[TModel],
    inputs: dict[str, Any],
    model_name: str,
) -> tuple[TModel, LLMResponse]:
    llm = get_chat_model()
    if llm is None:
        raise RuntimeError("mock runtime should not call invoke_structured")
    parser = PydanticOutputParser(pydantic_object=output_model)
    chain = prompt | llm | StrOutputParser()
    start = time.perf_counter()
    content = chain.invoke(
        {**inputs, "format_instructions": parser.get_format_instructions()}
    )
    parsed = parser.parse(content)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return parsed, LLMResponse(content=content, latency_ms=latency_ms, model=model_name)
```

- [ ] **Step 4: Add planner agent**

Create `backend/app/services/interview_agents/planner.py`:

```python
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.interview_agents.llm import invoke_structured
from app.services.interview_agents.models import InterviewPlan


class InterviewPlannerAgent:
    def plan(
        self,
        *,
        job_title: str,
        job_competency: dict,
        profile: dict,
        count: int,
    ) -> InterviewPlan:
        if settings.AI_RUNTIME != "deepseek":
            years = int(profile.get("years") or 0)
            target_type = "intern" if years <= 1 else "formal"
            skills = profile.get("skills") or job_competency.get("skills") or ["Python"]
            return InterviewPlan(
                target_type=target_type,
                difficulty="basic" if target_type == "intern" else "intermediate",
                core_skills=[str(item) for item in skills][:6],
                question_mix={"technical": max(count - 2, 1), "project": 1, "behavioral": 1},
                style="实战追问",
                notes=["结合简历项目提问", "要求候选人解释工程取舍"],
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是技术面试规划 Agent。只返回符合格式要求的 JSON。\\n{format_instructions}"),
                (
                    "human",
                    "岗位：{job_title}\\n能力模型：{job_competency}\\n简历画像：{profile}\\n题目数量：{count}",
                ),
            ]
        )
        result, _ = invoke_structured(
            prompt=prompt,
            output_model=InterviewPlan,
            inputs={
                "job_title": job_title,
                "job_competency": job_competency,
                "profile": profile,
                "count": count,
            },
            model_name=settings.DEEPSEEK_MODEL,
        )
        return result
```

- [ ] **Step 5: Add question generator agent**

Create `backend/app/services/interview_agents/question_generator.py`:

```python
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.ai_provider import LLMResponse
from app.services.interview_agents.llm import invoke_structured
from app.services.interview_agents.models import (
    GeneratedQuestion,
    InterviewPlan,
    QuestionGenerationResult,
)


class QuestionGenerationAgent:
    def generate(
        self,
        *,
        job_title: str,
        job_competency: dict,
        profile: dict,
        contexts: list[dict],
        count: int,
        plan: InterviewPlan,
    ) -> tuple[list[dict], LLMResponse]:
        if settings.AI_RUNTIME != "deepseek":
            questions = self._mock_questions(
                job_title=job_title,
                profile=profile,
                contexts=contexts,
                count=count,
                plan=plan,
            )
            return [item.model_dump(mode="json") for item in questions], LLMResponse(
                content="[langchain-mock]",
                model="langchain-mock",
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是结构化出题 Agent。只返回 JSON。\\n{format_instructions}"),
                (
                    "human",
                    "岗位：{job_title}\\n能力模型：{job_competency}\\n简历：{profile}\\n面试计划：{plan}\\n题库片段：{contexts}\\n题目数量：{count}",
                ),
            ]
        )
        result, meta = invoke_structured(
            prompt=prompt,
            output_model=QuestionGenerationResult,
            inputs={
                "job_title": job_title,
                "job_competency": job_competency,
                "profile": profile,
                "plan": plan.model_dump(mode="json"),
                "contexts": contexts,
                "count": count,
            },
            model_name=settings.DEEPSEEK_MODEL,
        )
        return [item.model_dump(mode="json") for item in result.questions[:count]], meta

    def _mock_questions(
        self,
        *,
        job_title: str,
        profile: dict,
        contexts: list[dict],
        count: int,
        plan: InterviewPlan,
    ) -> list[GeneratedQuestion]:
        skills = plan.core_skills or profile.get("skills") or ["Python"]
        types = ["technical", "project", "system_design", "behavioral"]
        questions: list[GeneratedQuestion] = []
        for index in range(count):
            skill = str(skills[index % len(skills)])
            context = contexts[index % len(contexts)] if contexts else {}
            context_text = str(context.get("content") or "").strip()
            question = context_text.splitlines()[0] if context_text else f"请结合项目说明 {skill} 在 {job_title} 中的关键应用。"
            questions.append(
                GeneratedQuestion(
                    position=index + 1,
                    type=types[index % len(types)],
                    difficulty=plan.difficulty,
                    skill=skill,
                    question=question,
                    rubric=["解释核心原理", "结合项目经验", "说明测试、监控或降级策略"],
                    reference_chunk_ids=[int(context["id"])] if context.get("id") is not None else [],
                )
            )
        return questions
```

- [ ] **Step 6: Add temporary follow-up, scoring, and report stubs with deterministic behavior**

Create `backend/app/services/interview_agents/followup.py`:

```python
from __future__ import annotations

from typing import Iterator


class FollowupAgent:
    def stream(self, *, interview: dict, question: dict, answer: dict, history: list[dict]) -> Iterator[str]:
        text = "你的回答已经提交。建议补充一次具体项目背景、关键取舍、测试方式和上线后的监控指标。"
        for index in range(0, len(text), 8):
            yield text[index : index + 8]
```

Create `backend/app/services/interview_agents/scoring.py`:

```python
from __future__ import annotations

from app.services.ai_provider import LLMResponse
from app.services.interview_agents.models import ScoreResult


class ScoringAgent:
    def score(
        self,
        *,
        job_title: str,
        profile: dict,
        question_answers: list[dict],
        knowledge_contexts: list[dict],
    ) -> tuple[ScoreResult, LLMResponse]:
        question_scores = []
        for item in question_answers:
            answer = str(item.get("answer") or "")
            score = 88.0 if len(answer) >= 80 else 70.0 if answer else 35.0
            question_scores.append(
                {
                    "position": item["position"],
                    "score": score,
                    "comment": "回答结构清晰，可以继续补充工程化细节。",
                }
            )
        average = round(sum(float(item["score"]) for item in question_scores) / max(len(question_scores), 1), 1)
        return ScoreResult(
            overall_score=average,
            level="可培养匹配" if average >= 70 else "需要继续准备",
            dimension_scores={"技术准确性": average, "项目表达": max(0, average - 3), "岗位匹配": min(100, average + 2)},
            question_scores=question_scores,
            strengths=["能围绕问题给出结构化回答"],
            improvements=["补充异常处理、监控和降级策略"],
            learning_plan=["用 STAR 结构复盘每道题", "为项目补充可量化指标"],
        ), LLMResponse(content="[langchain-mock-score]", model="langchain-mock")
```

Create `backend/app/services/interview_agents/report.py`:

```python
from __future__ import annotations

from app.services.interview_agents.models import ReportResult, ScoreResult


class ReportAgent:
    def build_report(self, *, scoring: ScoreResult, profile: dict, job_title: str) -> dict:
        report = ReportResult(
            overall_score=scoring.overall_score,
            level=scoring.level,
            dimension_scores=scoring.dimension_scores,
            question_scores=scoring.question_scores,
            strengths=scoring.strengths,
            improvements=scoring.improvements,
            learning_plan=scoring.learning_plan,
            next_practice=[f"围绕 {job_title} 再完成一轮项目深挖练习"],
        )
        return report.model_dump(mode="json")
```

- [ ] **Step 7: Add runtime facade for question generation**

Create `backend/app/services/interview_agents/runtime.py`:

```python
from __future__ import annotations

from functools import lru_cache
from typing import Iterator

from app.services.ai_provider import LLMResponse
from app.services.interview_agents.followup import FollowupAgent
from app.services.interview_agents.planner import InterviewPlannerAgent
from app.services.interview_agents.question_generator import QuestionGenerationAgent
from app.services.interview_agents.report import ReportAgent
from app.services.interview_agents.scoring import ScoringAgent


class InterviewAgentRuntime:
    def __init__(self) -> None:
        self.planner = InterviewPlannerAgent()
        self.question_generator = QuestionGenerationAgent()
        self.followup = FollowupAgent()
        self.scoring = ScoringAgent()
        self.report = ReportAgent()

    def generate_interview_questions(
        self,
        *,
        job_title: str,
        job_competency: dict,
        profile: dict,
        contexts: list[dict],
        count: int,
    ) -> tuple[list[dict], LLMResponse]:
        plan = self.planner.plan(
            job_title=job_title,
            job_competency=job_competency,
            profile=profile,
            count=count,
        )
        return self.question_generator.generate(
            job_title=job_title,
            job_competency=job_competency,
            profile=profile,
            contexts=contexts,
            count=count,
            plan=plan,
        )

    def stream_followup(self, *, interview: dict, question: dict, answer: dict, history: list[dict]) -> Iterator[str]:
        yield from self.followup.stream(
            interview=interview,
            question=question,
            answer=answer,
            history=history,
        )

    def score_interview(
        self,
        *,
        job_title: str,
        profile: dict,
        question_answers: list[dict],
        knowledge_contexts: list[dict],
    ) -> tuple[dict, LLMResponse]:
        scoring, meta = self.scoring.score(
            job_title=job_title,
            profile=profile,
            question_answers=question_answers,
            knowledge_contexts=knowledge_contexts,
        )
        report = self.report.build_report(scoring=scoring, profile=profile, job_title=job_title)
        return report, meta


@lru_cache
def get_interview_agent_runtime() -> InterviewAgentRuntime:
    return InterviewAgentRuntime()
```

- [ ] **Step 8: Export runtime from the package**

Update `backend/app/services/interview_agents/__init__.py`:

```python
"""LangChain interview agent package."""

from app.services.interview_agents.events import format_sse
from app.services.interview_agents.runtime import get_interview_agent_runtime

__all__ = ["format_sse", "get_interview_agent_runtime"]
```

- [ ] **Step 9: Run runtime test and verify it passes**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_agents.py -q
```

Expected result: `3 passed`.

- [ ] **Step 10: Commit task 2**

```powershell
git add backend/app/services/interview_agents backend/tests/test_interview_agents.py
git commit -m "Add LangChain interview question runtime"
```

---

### Task 3: Wire Question Generation Into Interview Service

**Files:**
- Modify: `backend/app/services/interview_service.py`
- Modify: `backend/tests/test_interview_flow.py`

- [ ] **Step 1: Add assertion that generated questions are still compatible**

In `backend/tests/test_interview_flow.py`, after `assert len(interview["questions"]) == 3`, add:

```python
    assert all(q["rubric"] for q in interview["questions"])
    assert all(q["difficulty"] in {"basic", "intermediate", "advanced"} for q in interview["questions"])
```

- [ ] **Step 2: Run flow test and verify current behavior**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_flow.py::test_full_business_flow -q
```

Expected result before service change: PASS, because the old mock provider already returns compatible questions.

- [ ] **Step 3: Replace provider import and question generation call**

In `backend/app/services/interview_service.py`, replace:

```python
from app.services.ai_provider import get_ai_provider
```

with:

```python
from app.services.interview_agents.runtime import get_interview_agent_runtime
```

In `create_interview`, replace:

```python
        questions, meta = get_ai_provider().generate_interview_questions(
            job_title=job.title,
            job_competency=job.competency_model,
            profile=profile,
            contexts=context_payload,
            count=count,
        )
```

with:

```python
        questions, meta = get_interview_agent_runtime().generate_interview_questions(
            job_title=job.title,
            job_competency=job.competency_model,
            profile=profile,
            contexts=context_payload,
            count=count,
        )
```

- [ ] **Step 4: Run flow test**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_flow.py::test_full_business_flow -q
```

Expected result: PASS.

- [ ] **Step 5: Commit task 3**

```powershell
git add backend/app/services/interview_service.py backend/tests/test_interview_flow.py
git commit -m "Use LangChain runtime for interview questions"
```

---

### Task 4: Wire Scoring And Report Generation Into Interview Service

**Files:**
- Modify: `backend/app/services/interview_service.py`
- Modify: `backend/tests/test_interview_agents.py`

- [ ] **Step 1: Add runtime scoring unit test**

Append to `backend/tests/test_interview_agents.py`:

```python
def test_mock_runtime_scores_and_builds_report() -> None:
    runtime = get_interview_agent_runtime()
    report, meta = runtime.score_interview(
        job_title="AI 应用工程师",
        profile={"skills": ["FastAPI"]},
        question_answers=[
            {
                "position": 1,
                "skill": "FastAPI",
                "question": "如何设计接口？",
                "rubric": ["结构", "测试"],
                "answer": "我会先定义边界，再设计接口、测试、监控、降级和安全策略，并根据指标复盘。",
                "duration_ms": 30000,
            }
        ],
        knowledge_contexts=[{"id": 1, "title": "工程化", "content": "关注测试和监控。"}],
    )

    assert meta.model == "langchain-mock"
    assert report["overall_score"] >= 70
    assert report["question_scores"][0]["position"] == 1
    assert report["next_practice"]
```

- [ ] **Step 2: Run scoring unit test**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_agents.py::test_mock_runtime_scores_and_builds_report -q
```

Expected result: PASS after task 2 stubs.

- [ ] **Step 3: Replace scoring provider call**

In `backend/app/services/interview_service.py`, replace:

```python
        report, meta = get_ai_provider().score_interview(
            job_title=interview.job_title,
            profile=profile,
            question_answers=qa_pairs,
            knowledge_contexts=[h.to_context() for h in knowledge_hits],
        )
```

with:

```python
        report, meta = get_interview_agent_runtime().score_interview(
            job_title=interview.job_title,
            profile=profile,
            question_answers=qa_pairs,
            knowledge_contexts=[h.to_context() for h in knowledge_hits],
        )
```

- [ ] **Step 4: Run business flow**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_flow.py::test_full_business_flow -q
```

Expected result: PASS, with `finished["score_report"]["question_scores"]` populated.

- [ ] **Step 5: Commit task 4**

```powershell
git add backend/app/services/interview_service.py backend/tests/test_interview_agents.py
git commit -m "Use LangChain runtime for interview scoring"
```

---

### Task 5: Backend Structured SSE Endpoint

**Files:**
- Modify: `backend/app/api/v1/interviews.py`
- Create: `backend/tests/test_interview_stream.py`

- [ ] **Step 1: Write stream API tests**

Create `backend/tests/test_interview_stream.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient


def _create_answered_interview(client: TestClient, auth_headers: dict[str, str]) -> dict:
    resume_response = client.post(
        "/api/v1/resumes",
        headers=auth_headers,
        json={
            "filename": "stream-resume.txt",
            "target_position": "AI 应用工程师",
            "text": "姓名：王明\n1年 Python FastAPI RAG LangChain 项目经验，负责接口、测试和监控。",
        },
    )
    assert resume_response.status_code == 201, resume_response.text
    resume = resume_response.json()
    jobs = client.get("/api/v1/jobs", headers=auth_headers)
    assert jobs.status_code == 200, jobs.text
    job_code = jobs.json()["items"][0]["code"] if isinstance(jobs.json(), dict) else jobs.json()[0]["code"]
    interview_response = client.post(
        "/api/v1/interviews",
        headers=auth_headers,
        json={
            "resume_id": resume["id"],
            "job_code": job_code,
            "question_count": 2,
            "idempotency_key": "stream-test-key",
        },
    )
    assert interview_response.status_code == 201, interview_response.text
    interview = interview_response.json()
    first_question = interview["questions"][0]
    answer_response = client.post(
        f"/api/v1/interviews/{interview['id']}/answers",
        headers=auth_headers,
        json={
            "question_id": first_question["id"],
            "answer": "我会先明确接口边界，再补充测试、监控、降级、安全和复盘指标。",
            "duration_ms": 12000,
        },
    )
    assert answer_response.status_code == 200, answer_response.text
    interview["answered_question_id"] = first_question["id"]
    return interview


def test_followup_stream_returns_structured_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    interview = _create_answered_interview(client, auth_headers)
    with client.stream(
        "GET",
        f"/api/v1/interviews/{interview['id']}/stream?mode=followup&question_id={interview['answered_question_id']}",
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: followup_started" in text
    assert "event: followup_delta" in text
    assert "event: followup_done" in text
    assert "event: done" in text


def test_scoring_stream_finishes_report(client: TestClient, auth_headers: dict[str, str]) -> None:
    interview = _create_answered_interview(client, auth_headers)
    second_question = interview["questions"][1]
    answer_response = client.post(
        f"/api/v1/interviews/{interview['id']}/answers",
        headers=auth_headers,
        json={
            "question_id": second_question["id"],
            "answer": "我会结合项目目标说明方案设计，并补充测试、监控、异常处理和上线复盘。",
            "duration_ms": 10000,
        },
    )
    assert answer_response.status_code == 200, answer_response.text

    with client.stream(
        "GET",
        f"/api/v1/interviews/{interview['id']}/stream?mode=scoring",
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: scoring_started" in text
    assert "event: scoring_done" in text
    assert "event: report_ready" in text
    assert "event: done" in text
```

- [ ] **Step 2: Run stream tests and verify they fail**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_stream.py -q
```

Expected result: 404 for `/stream`.

- [ ] **Step 3: Add imports to interviews route**

In `backend/app/api/v1/interviews.py`, add:

```python
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
```

Replace the existing `from fastapi import APIRouter, Depends, status` import with the block above.

Also add:

```python
from app.services.interview_agents.events import error_event, format_sse
from app.services.interview_agents.runtime import get_interview_agent_runtime
```

- [ ] **Step 4: Add stream endpoint**

In `backend/app/api/v1/interviews.py`, insert this endpoint before the existing demo `/{interview_id}/answer/stream` endpoint:

```python
@router.get(
    "/{interview_id}/stream",
    summary="结构化面试事件流（SSE）",
    response_class=StreamingResponse,
)
def stream_interview_events(
    interview_id: int,
    mode: Literal["followup", "scoring"] = Query(default="followup"),
    question_id: int | None = Query(default=None, gt=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = interview_service.get_interview(db, user, interview_id)

    def event_stream():
        try:
            if mode == "followup":
                if question_id is None:
                    yield error_event("question_id is required in followup mode", stage="followup", interview_id=interview_id)
                    yield format_sse("done", {"interview_id": interview_id})
                    return
                questions = sorted(interview.questions, key=lambda q: q.position)
                question = next((item for item in questions if item.id == question_id), None)
                answer = next((item for item in interview.answers if item.question_id == question_id), None)
                if question is None or answer is None:
                    yield error_event("question or answer not found", stage="followup", interview_id=interview_id)
                    yield format_sse("done", {"interview_id": interview_id})
                    return
                payload = {"interview_id": interview_id, "question_id": question_id}
                yield format_sse("followup_started", payload)
                full_content = ""
                for token in get_interview_agent_runtime().stream_followup(
                    interview={"id": interview.id, "job_title": interview.job_title},
                    question={
                        "id": question.id,
                        "position": question.position,
                        "question": question.question,
                        "skill": question.skill,
                        "rubric": question.rubric,
                    },
                    answer={"id": answer.id, "answer": answer.answer, "duration_ms": answer.duration_ms},
                    history=[
                        {"question": item.question, "answer": item.answer.answer if item.answer else ""}
                        for item in questions
                    ],
                ):
                    full_content += token
                    yield format_sse("followup_delta", {**payload, "content": token})
                yield format_sse("followup_done", {**payload, "content": full_content})
                yield format_sse("done", payload)
                return

            yield format_sse("scoring_started", {"interview_id": interview_id})
            finished = interview_service.finish_interview(db, user, interview_id)
            yield format_sse(
                "scoring_done",
                {"interview_id": interview_id, "overall_score": finished.overall_score},
            )
            yield format_sse(
                "report_ready",
                {"interview_id": interview_id, "report": finished.score_report},
            )
            yield format_sse("done", {"interview_id": interview_id})
        except Exception as exc:
            yield error_event(str(exc), stage=mode, interview_id=interview_id)
            yield format_sse("done", {"interview_id": interview_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 5: Run stream tests**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_stream.py -q
```

Expected result: `2 passed`.

- [ ] **Step 6: Run interview flow regression**

Run from `backend`:

```powershell
python -m pytest tests/test_interview_flow.py -q
```

Expected result: all tests in `test_interview_flow.py` pass.

- [ ] **Step 7: Commit task 5**

```powershell
git add backend/app/api/v1/interviews.py backend/tests/test_interview_stream.py
git commit -m "Add structured interview SSE endpoint"
```

---

### Task 6: Frontend Streaming Client And Mock Interview UI

**Files:**
- Modify: `frontend/src/api/client.js`
- Modify: `frontend/src/api/modules.js`
- Modify: `frontend/src/views/MockInterview.vue`

- [ ] **Step 1: Export base URL and auth headers**

In `frontend/src/api/client.js`, replace:

```javascript
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
```

with:

```javascript
export const apiBaseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const baseURL = apiBaseURL
```

After `injectAuth(config)`, add:

```javascript
export function authHeaders() {
  const session = useSessionStore()
  return session.token ? { Authorization: `Bearer ${session.token}` } : {}
}
```

- [ ] **Step 2: Add stream parser to modules**

In `frontend/src/api/modules.js`, change the first import to:

```javascript
import { api, uploadApi, apiBaseURL, authHeaders, on401Logout } from './client'
```

Add this helper above `export const interviewApi`:

```javascript
async function streamSse(path, { params = {}, signal, onEvent } = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const url = `${apiBaseURL}${path}${search.toString() ? `?${search}` : ''}`
  const response = await fetch(url, {
    method: 'GET',
    headers: authHeaders(),
    signal,
  })
  if (response.status === 401) {
    on401Logout()
    throw new Error('登录已过期')
  }
  if (!response.ok || !response.body) {
    throw new Error(`流式请求失败：${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const lines = block.split('\n')
      const eventLine = lines.find((line) => line.startsWith('event: '))
      const dataLine = lines.find((line) => line.startsWith('data: '))
      if (!eventLine || !dataLine) continue
      const event = eventLine.slice(7).trim()
      const data = JSON.parse(dataLine.slice(6))
      onEvent?.({ event, data })
    }
  }
}
```

In `interviewApi`, add:

```javascript
  stream: (id, options) => streamSse(`/interviews/${id}/stream`, options),
```

- [ ] **Step 3: Add stream state to MockInterview**

In `frontend/src/views/MockInterview.vue`, after `const sidebarLoading = ref(false)`, add:

```javascript
const aiFeedback = reactive({
  loading: false,
  content: '',
  error: '',
  event: '',
})
let streamController = null
```

Add these functions before `submitAnswer`:

```javascript
function resetAiFeedback() {
  aiFeedback.loading = false
  aiFeedback.content = ''
  aiFeedback.error = ''
  aiFeedback.event = ''
}

async function runFollowupStream(questionId) {
  if (!current.value || !questionId) return
  if (streamController) streamController.abort()
  streamController = new AbortController()
  aiFeedback.loading = true
  aiFeedback.content = ''
  aiFeedback.error = ''
  aiFeedback.event = 'followup_started'
  try {
    await interviewApi.stream(current.value.id, {
      params: { mode: 'followup', question_id: questionId },
      signal: streamController.signal,
      onEvent: ({ event, data }) => {
        aiFeedback.event = event
        if (event === 'followup_delta') aiFeedback.content += data.content || ''
        if (event === 'followup_done') aiFeedback.content = data.content || aiFeedback.content
        if (event === 'error') aiFeedback.error = data.message || 'AI 追问生成失败'
      },
    })
  } catch (err) {
    if (err.name !== 'AbortError') aiFeedback.error = err?.message || 'AI 追问生成失败'
  } finally {
    aiFeedback.loading = false
    streamController = null
  }
}
```

Change `onUnmounted(stopTimer)` to:

```javascript
onUnmounted(() => {
  stopTimer()
  if (streamController) streamController.abort()
})
```

- [ ] **Step 4: Trigger follow-up after answer submission**

In `submitAnswer`, replace the success block after `current.value = updated` with:

```javascript
    const answeredQuestionId = currentQuestion.value.id
    current.value = updated
    localStorage.removeItem(draftKey(current.value.id, answeredQuestionId))
    ElMessage.success('已提交')
    await runFollowupStream(answeredQuestionId)
```

This intentionally removes automatic navigation to the next question so the user can read the AI feedback before moving on.

- [ ] **Step 5: Add AI feedback panel in template**

In `frontend/src/views/MockInterview.vue`, insert this block after the existing `answered-banner` block:

```vue
            <div
              v-if="aiFeedback.loading || aiFeedback.content || aiFeedback.error"
              class="ai-feedback"
            >
              <div class="ai-feedback-head">
                <span>AI 面试官反馈</span>
                <el-tag v-if="aiFeedback.loading" size="small" type="warning">生成中</el-tag>
                <el-tag v-else size="small" type="success">已生成</el-tag>
              </div>
              <p v-if="aiFeedback.content">{{ aiFeedback.content }}</p>
              <p v-if="aiFeedback.error" class="ai-feedback-error">{{ aiFeedback.error }}</p>
            </div>
```

Add CSS before `.qa-actions`:

```css
.ai-feedback {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
}
.ai-feedback-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #1e3a8a;
  font-size: 13px;
  font-weight: 600;
}
.ai-feedback p {
  margin: 8px 0 0;
  color: #1f2937;
  line-height: 1.7;
  font-size: 13px;
  white-space: pre-wrap;
}
.ai-feedback-error {
  color: #b91c1c;
}
```

- [ ] **Step 6: Reset feedback when changing question or interview**

In `pickInterview`, after `currentIndex.value = 0`, add:

```javascript
    resetAiFeedback()
```

In `createInterview`, after `currentIndex.value = 0`, add:

```javascript
    resetAiFeedback()
```

In `go(delta)`, after `currentIndex.value = next`, add:

```javascript
  resetAiFeedback()
```

In the route watcher, after `currentIndex.value = 0`, add:

```javascript
        resetAiFeedback()
```

- [ ] **Step 7: Build frontend**

Run from `frontend`:

```powershell
npm run build
```

Expected result: Vite build completes with no syntax error.

- [ ] **Step 8: Commit task 6**

```powershell
git add frontend/src/api/client.js frontend/src/api/modules.js frontend/src/views/MockInterview.vue
git commit -m "Add streaming interview feedback UI"
```

---

### Task 7: Full Verification And Handoff

**Files:**
- No new files.
- Verify all modified backend and frontend files.

- [ ] **Step 1: Run backend tests**

Run from `backend`:

```powershell
python -m pytest -q
```

Expected result: all backend tests pass.

- [ ] **Step 2: Run frontend build**

Run from `frontend`:

```powershell
npm run build
```

Expected result: Vite build completes.

- [ ] **Step 3: Check git status**

Run from repository root:

```powershell
git status --short
```

Expected result: no unstaged implementation files. Ignored runtime artifacts may remain invisible.

- [ ] **Step 4: Start backend for manual smoke test**

Run from `backend`:

```powershell
python -m uvicorn app.main:app --reload
```

Expected result includes:

```text
Uvicorn running on http://127.0.0.1:8000
```

- [ ] **Step 5: Start frontend for manual smoke test**

Run from `frontend`:

```powershell
npm run dev
```

Expected result includes a local Vite URL such as:

```text
Local:   http://localhost:5173/
```

- [ ] **Step 6: Manual browser flow**

Open the frontend URL, log in or register, create or select an interview, submit one answer, and verify:

- The answer saves.
- The AI feedback panel appears.
- Text streams into the panel.
- No automatic jump hides the feedback.
- Completing the interview produces a report.

- [ ] **Step 7: Commit verification-only adjustments if any were needed**

If a syntax or test fix was required during verification, inspect the changed files and commit the implementation paths touched by this plan:

```powershell
git status --short
git add backend/app/services/interview_agents backend/app/services/interview_service.py backend/app/api/v1/interviews.py backend/tests/test_interview_agents.py backend/tests/test_interview_stream.py backend/tests/test_interview_flow.py frontend/src/api/client.js frontend/src/api/modules.js frontend/src/views/MockInterview.vue
git commit -m "Fix interview SSE verification issues"
```

If no fix was required, do not create an empty commit.
