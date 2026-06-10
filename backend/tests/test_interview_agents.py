from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from pydantic import BaseModel, ValidationError

import app.services.interview_agents.followup as followup_module
import app.services.interview_agents.llm as agent_llm
import app.services.interview_agents.question_generator as question_generator
import app.services.interview_agents.scoring as scoring_module
from app.services.ai_provider import LLMResponse
from app.models.ai_config import AIProvider, AIRuntime
from app.models.ai_usage import AIUsageStatus
from app.services.interview_agents.events import format_sse
from app.services.interview_agents.followup import FollowupAgent
from app.services.interview_agents.models import (
    FollowupAction,
    FollowupResult,
    GeneratedQuestion,
    InterviewPlan,
    QuestionGenerationResult,
    ScoreResult,
)
from app.services.interview_agents.planner import InterviewPlannerAgent
from app.services.interview_agents.question_generator import QuestionGenerationAgent
from app.services.interview_agents.runtime import get_interview_agent_runtime
from app.services.interview_agents.scoring import ScoringAgent


class ProbeResult(BaseModel):
    answer: str


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


def test_mock_runtime_generates_resume_aware_next_question_from_answer() -> None:
    runtime = get_interview_agent_runtime()

    question, meta = runtime.generate_next_question(
        job_title="AI 应用工程师",
        job_competency={"skills": ["FastAPI", "RAG", "LangChain"]},
        profile={
            "skills": ["FastAPI", "RAG", "LangChain"],
            "projects": ["AI 模拟面试平台：简历解析、RAG 题库召回、SSE 流式追问。"],
        },
        contexts=[{"id": 101, "title": "RAG 追问", "content": "关注召回质量和回答证据。"}],
        conversation=[
            {
                "position": 1,
                "skill": "RAG",
                "question": "请说明你如何设计 RAG 召回。",
                "answer": "我会用向量召回题库，结合岗位和简历技能筛选问题，并通过 SSE 流式展示追问。",
            }
        ],
        current_question={
            "position": 1,
            "skill": "RAG",
            "question": "请说明你如何设计 RAG 召回。",
        },
        current_answer="我会用向量召回题库，结合岗位和简历技能筛选问题，并通过 SSE 流式展示追问。",
        next_position=2,
        max_questions=4,
    )

    assert meta.model == "langchain-mock"
    assert question["position"] == 2
    assert question["skill"] in {"RAG", "LangChain", "FastAPI"}
    assert "刚才" in question["question"]
    assert "RAG" in question["question"] or "LangChain" in question["question"]


def test_deepseek_chat_model_requires_deepseek_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent_llm,
        "get_effective_config",
        lambda: SimpleNamespace(
            runtime=AIRuntime.DEEPSEEK,
            provider=AIProvider.DEEPSEEK,
            base_url="https://api.deepseek.com",
            api_key="",
            model="deepseek-chat",
            temperature=0.2,
            timeout=60,
            max_tokens=2048,
        ),
    )

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY is not configured"):
        agent_llm.get_chat_model()


def test_langchain_chat_model_forwards_responses_wire_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeChatOpenAI))
    monkeypatch.setattr(
        agent_llm,
        "get_effective_config",
        lambda: SimpleNamespace(
            runtime=AIRuntime.DEEPSEEK,
            provider=AIProvider.DEEPSEEK,
            base_url="https://www.sailcode.store",
            api_key="sk-test",
            model="grok-4.3-high",
            wire_api="responses",
            temperature=0.2,
            timeout=60,
            max_tokens=2048,
            max_retries=3,
        ),
    )

    agent_llm.get_chat_model()

    assert captured["extra_body"] == {"wire_api": "responses"}
    assert captured["default_headers"]["User-Agent"] == "Mozilla/5.0"


def test_langchain_structured_invocation_records_ai_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict] = []
    monkeypatch.setattr(
        agent_llm,
        "get_effective_config",
        lambda: SimpleNamespace(
            runtime=AIRuntime.DEEPSEEK,
            provider=AIProvider.DEEPSEEK,
            model="deepseek-test",
        ),
    )
    monkeypatch.setattr(
        agent_llm,
        "get_chat_model",
        lambda: FakeListChatModel(responses=['{"answer":"ok"}']),
    )
    monkeypatch.setattr(
        agent_llm.ai_usage_service,
        "record_ai_usage_safely",
        lambda **kwargs: records.append(kwargs),
    )
    prompt = ChatPromptTemplate.from_messages(
        [("human", "{question}\n{format_instructions}")]
    )

    parsed, meta = agent_llm.invoke_structured(
        prompt,
        ProbeResult,
        {"question": "ping"},
    )

    assert parsed.answer == "ok"
    assert meta.model == "deepseek-test"
    assert records
    assert records[0]["feature"] == "interview_agent"
    assert records[0]["runtime"] == AIRuntime.DEEPSEEK
    assert records[0]["provider"] == AIProvider.DEEPSEEK
    assert records[0]["model"] == "deepseek-test"
    assert records[0]["status"] == AIUsageStatus.OK
    assert records[0]["latency_ms"] >= 0


def test_langchain_structured_invocation_falls_back_to_provider_on_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict] = []
    monkeypatch.setattr(
        agent_llm,
        "get_effective_config",
        lambda: SimpleNamespace(
            runtime=AIRuntime.DEEPSEEK,
            provider=AIProvider.DEEPSEEK,
            base_url="https://www.sailcode.store",
            api_key="sk-test",
            model="grok-4.3-high",
            wire_api="responses",
            temperature=0.2,
            timeout=60,
            max_tokens=2048,
            max_retries=2,
        ),
    )
    monkeypatch.setattr(
        agent_llm,
        "get_chat_model",
        lambda: FakeListChatModel(responses=["这不是 JSON"]),
    )

    class FakeProvider:
        def __init__(self, config):
            self.config = config

        def chat_json(self, system, user, *, temperature=None, max_tokens=None):
            assert "format_instructions" not in user
            return {"answer": "fallback-ok"}, LLMResponse(
                content='{"answer":"fallback-ok"}',
                model=self.config.model,
            )

    monkeypatch.setattr(agent_llm, "DeepSeekProvider", FakeProvider, raising=False)
    monkeypatch.setattr(
        agent_llm.ai_usage_service,
        "record_ai_usage_safely",
        lambda **kwargs: records.append(kwargs),
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", "只返回 JSON。"), ("human", "{question}\n{format_instructions}")]
    )

    parsed, meta = agent_llm.invoke_structured(
        prompt,
        ProbeResult,
        {"question": "ping"},
    )

    assert parsed.answer == "fallback-ok"
    assert meta.model == "grok-4.3-high"
    assert records[-1]["status"] == AIUsageStatus.OK


def test_question_generation_uses_active_ai_config_when_env_runtime_is_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(question_generator, "is_chat_model_enabled", lambda: True, raising=False)
    plan = InterviewPlan(
        target_type="formal",
        difficulty="intermediate",
        core_skills=["FastAPI"],
    )

    def fake_invoke_structured(*args, **kwargs):
        _prompt, output_model, variables = args
        assert output_model is QuestionGenerationResult
        assert variables["job_title"] == "AI 应用工程师"
        return (
            QuestionGenerationResult(
                plan=plan,
                questions=[
                    GeneratedQuestion(
                        position=1,
                        type="technical",
                        difficulty="intermediate",
                        skill="FastAPI",
                        question="请说明 FastAPI 依赖注入的生产实践。",
                        rubric=["解释原理", "结合项目"],
                    )
                ],
            ),
            LLMResponse(content="[admin-configured]", model="admin-model"),
        )

    monkeypatch.setattr(question_generator, "invoke_structured", fake_invoke_structured)

    questions, meta = QuestionGenerationAgent().generate(
        plan=plan,
        job_title="AI 应用工程师",
        job_competency={"skills": ["FastAPI"]},
        profile={"years": 2, "skills": ["FastAPI"]},
        contexts=[],
        count=1,
    )

    assert meta.model == "admin-model"
    assert questions[0]["question"] == "请说明 FastAPI 依赖注入的生产实践。"


def test_followup_stream_uses_active_ai_config_when_env_runtime_is_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(followup_module, "is_chat_model_enabled", lambda: True, raising=False)
    monkeypatch.setattr(
        followup_module,
        "get_chat_model",
        lambda: FakeListChatModel(responses=["请补充上线指标。"]),
        raising=False,
    )

    chunks = list(
        FollowupAgent().stream(
            interview_id=1,
            question_id=2,
            answer="我会设计接口并补充测试。",
            job_title="AI 应用工程师",
            profile={"skills": ["FastAPI"]},
            question={"question": "如何设计接口？", "rubric": ["结构", "测试"]},
            knowledge_contexts=[],
        )
    )

    assert "".join(chunks) == "请补充上线指标。"


def test_scoring_uses_active_ai_config_when_env_runtime_is_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scoring_module, "is_chat_model_enabled", lambda: True, raising=False)

    def fake_invoke_structured(*args, **kwargs):
        _prompt, output_model, _variables = args
        assert output_model is ScoreResult
        return (
            ScoreResult(
                overall_score=91.0,
                level="匹配",
                dimension_scores={"技术准确性": 91.0},
                question_scores=[{"position": 1, "score": 91.0, "comment": "证据充分"}],
                strengths=["回答有项目证据"],
                improvements=["继续量化指标"],
                learning_plan=["复盘线上压测数据"],
            ),
            LLMResponse(content="[admin-score]", model="admin-model"),
        )

    monkeypatch.setattr(scoring_module, "invoke_structured", fake_invoke_structured, raising=False)

    score, meta = ScoringAgent().score(
        job_title="AI 应用工程师",
        profile={"skills": ["FastAPI"]},
        question_answers=[{"position": 1, "answer": "有测试和监控。"}],
        knowledge_contexts=[],
    )

    assert meta.model == "admin-model"
    assert score.overall_score == 91.0


def test_deepseek_question_generation_limits_result_to_requested_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(question_generator, "is_chat_model_enabled", lambda: True, raising=False)
    plan = InterviewPlan(
        target_type="intern",
        difficulty="basic",
        core_skills=["FastAPI"],
    )
    generated = [
        GeneratedQuestion(
            position=position,
            type="technical",
            difficulty="basic",
            skill="FastAPI",
            question=f"请解释 FastAPI 测试策略 {position}。",
            rubric=["解释核心原理"],
        )
        for position in range(1, 4)
    ]

    def fake_invoke_structured(*args, **kwargs):
        _prompt, output_model, variables = args
        assert output_model is QuestionGenerationResult
        assert variables["count"] == 2
        return (
            QuestionGenerationResult(plan=plan, questions=generated),
            LLMResponse(content="[fake-deepseek]", model="deepseek-chat"),
        )

    monkeypatch.setattr(question_generator, "invoke_structured", fake_invoke_structured)

    questions, meta = QuestionGenerationAgent().generate(
        plan=plan,
        job_title="AI 应用工程师",
        job_competency={"skills": ["FastAPI"]},
        profile={"years": 1, "skills": ["FastAPI"]},
        contexts=[],
        count=2,
    )

    assert meta.model == "deepseek-chat"
    assert len(questions) == 2
    assert questions[-1]["position"] == 2


def test_deepseek_followup_stream_uses_langchain_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(followup_module, "is_chat_model_enabled", lambda: True, raising=False)
    monkeypatch.setattr(
        followup_module,
        "get_chat_model",
        lambda: FakeListChatModel(responses=["请补充监控指标和失败降级策略。"]),
        raising=False,
    )

    chunks = list(
        FollowupAgent().stream(
            interview_id=1,
            question_id=2,
            answer="我会设计接口并补充测试。",
            job_title="AI 应用工程师",
            profile={"skills": ["FastAPI"]},
            question={"question": "如何设计接口？", "rubric": ["结构", "测试"]},
            knowledge_contexts=[],
        )
    )

    assert "".join(chunks) == "请补充监控指标和失败降级策略。"


def test_deepseek_scoring_uses_langchain_structured_invoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scoring_module, "is_chat_model_enabled", lambda: True, raising=False)

    def fake_invoke_structured(*args, **kwargs):
        _prompt, output_model, variables = args
        assert output_model is ScoreResult
        assert variables["job_title"] == "AI 应用工程师"
        assert "FastAPI" in variables["question_answers"]
        return (
            ScoreResult(
                overall_score=88.0,
                level="匹配",
                dimension_scores={"技术准确性": 88.0},
                question_scores=[{"position": 1, "score": 88.0, "comment": "工程细节充分"}],
                strengths=["结构清晰"],
                improvements=["继续量化效果"],
                learning_plan=["复盘线上指标"],
            ),
            LLMResponse(content="[fake-deepseek-score]", model="deepseek-chat"),
        )

    monkeypatch.setattr(scoring_module, "invoke_structured", fake_invoke_structured, raising=False)

    score, meta = ScoringAgent().score(
        job_title="AI 应用工程师",
        profile={"skills": ["FastAPI"]},
        question_answers=[
            {
                "position": 1,
                "skill": "FastAPI",
                "question": "如何设计接口？",
                "answer": "我会明确边界并设计测试、监控和降级。",
            }
        ],
        knowledge_contexts=[],
    )

    assert meta.model == "deepseek-chat"
    assert score.overall_score == 88.0
    assert score.question_scores[0]["comment"] == "工程细节充分"


def test_mock_planner_treats_invalid_years_as_intern() -> None:
    plan = InterviewPlannerAgent().plan(
        job_title="AI 应用工程师",
        job_competency={"skills": ["FastAPI"]},
        profile={"years": "unknown", "skills": ["FastAPI"]},
        contexts=[],
        count=2,
    )

    assert plan.target_type == "intern"
    assert plan.difficulty == "basic"


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


def test_agent_models_trim_and_limit_list_validators() -> None:
    plan = InterviewPlan(
        target_type="formal",
        difficulty="intermediate",
        core_skills=[
            " FastAPI ",
            "",
            " RAG ",
            " ",
            "Python",
            "SQL",
            "Docker",
            "Vue",
            "Redis",
            "Celery",
            "LangChain",
        ],
    )
    question = GeneratedQuestion(
        position=1,
        skill="FastAPI",
        question="Explain dependency injection in FastAPI projects.",
        rubric=[
            " Explain principles ",
            "",
            "Use project examples",
            " ",
            "Discuss testing",
            "Mention monitoring",
            "Cover fallbacks",
            "Describe tradeoffs",
            "Extra item",
        ],
    )

    assert plan.core_skills == [
        "FastAPI",
        "RAG",
        "Python",
        "SQL",
        "Docker",
        "Vue",
        "Redis",
        "Celery",
    ]
    assert question.rubric == [
        "Explain principles",
        "Use project examples",
        "Discuss testing",
        "Mention monitoring",
        "Cover fallbacks",
        "Describe tradeoffs",
    ]


def test_agent_models_reject_out_of_range_scores() -> None:
    with pytest.raises(ValidationError):
        FollowupResult(
            action=FollowupAction.COMMENT,
            content="Needs more detail.",
            confidence=1.01,
        )

    with pytest.raises(ValidationError):
        ScoreResult(overall_score=100.01, level="out of range")


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
