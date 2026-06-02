from __future__ import annotations

from typing import Any

from app.services.ai_provider import LLMResponse
from app.services.interview_agents.models import ScoreResult


class ScoringAgent:
    def score(
        self,
        *,
        job_title: str,
        profile: dict[str, Any],
        question_answers: list[dict[str, Any]],
        knowledge_contexts: list[dict[str, Any]],
    ) -> tuple[ScoreResult, LLMResponse]:
        _ = (job_title, profile, knowledge_contexts)
        question_scores = [
            {
                "position": answer.get("position", index),
                "score": 75.0,
                "comment": "回答结构清晰，可继续补充工程细节。",
            }
            for index, answer in enumerate(question_answers, start=1)
        ]
        return ScoreResult(
            overall_score=75.0,
            level="可培养",
            dimension_scores={"技术准确性": 75.0, "项目表达": 75.0},
            question_scores=question_scores,
            strengths=["能够围绕问题给出基本思路"],
            improvements=["补充测试、监控和降级策略"],
            learning_plan=["复盘项目中的关键技术决策"],
        ), LLMResponse(content="[langchain-mock-score]", model="langchain-mock")
