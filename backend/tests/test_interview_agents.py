from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

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
