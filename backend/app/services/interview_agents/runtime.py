from __future__ import annotations

from functools import lru_cache
from typing import Any

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
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        count: int,
    ) -> tuple[list[dict[str, Any]], LLMResponse]:
        plan = self.planner.plan(
            job_title=job_title,
            job_competency=job_competency,
            profile=profile,
            contexts=contexts,
            count=count,
        )
        return self.question_generator.generate(
            plan=plan,
            job_title=job_title,
            job_competency=job_competency,
            profile=profile,
            contexts=contexts,
            count=count,
        )

    def stream_followup(self, **kwargs: Any):
        return self.followup.stream(**kwargs)

    def score_interview(
        self,
        *,
        job_title: str,
        profile: dict[str, Any],
        question_answers: list[dict[str, Any]],
        knowledge_contexts: list[dict[str, Any]],
    ) -> tuple[dict[str, object], LLMResponse]:
        score, meta = self.scoring.score(
            job_title=job_title,
            profile=profile,
            question_answers=question_answers,
            knowledge_contexts=knowledge_contexts,
        )
        return self.report.build_report(score), meta


@lru_cache
def get_interview_agent_runtime() -> InterviewAgentRuntime:
    return InterviewAgentRuntime()
