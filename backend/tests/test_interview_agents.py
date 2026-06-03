from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

import app.services.interview_agents.llm as agent_llm
import app.services.interview_agents.question_generator as question_generator
from app.services.ai_provider import LLMResponse
from app.services.interview_agents.events import format_sse
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


def test_deepseek_chat_model_requires_deepseek_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fallback")
    monkeypatch.setattr(agent_llm.settings, "AI_RUNTIME", "deepseek")
    monkeypatch.setattr(agent_llm.settings, "DEEPSEEK_API_KEY", None)

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY is not configured"):
        agent_llm.get_chat_model()


def test_deepseek_question_generation_limits_result_to_requested_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(question_generator.settings, "AI_RUNTIME", "deepseek")
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
