from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from app.services.interview_agents.llm import invoke_structured, is_chat_model_enabled
from app.services.interview_agents.models import InterviewPlan


class InterviewPlannerAgent:
    def plan(
        self,
        *,
        job_title: str,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        count: int,
    ) -> InterviewPlan:
        if not is_chat_model_enabled():
            return self._mock_plan(job_competency=job_competency, profile=profile, count=count)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是面试规划 Agent。请根据岗位、能力模型、候选人画像和检索上下文生成结构化面试计划。\n{format_instructions}",
                ),
                (
                    "human",
                    "岗位：{job_title}\n能力模型：{job_competency}\n候选人画像：{profile}\n上下文：{contexts}\n题目数量：{count}",
                ),
            ]
        )
        plan, _meta = invoke_structured(
            prompt,
            InterviewPlan,
            {
                "job_title": job_title,
                "job_competency": json.dumps(job_competency, ensure_ascii=False),
                "profile": json.dumps(profile, ensure_ascii=False),
                "contexts": json.dumps(contexts, ensure_ascii=False),
                "count": count,
            },
        )
        return plan

    def _mock_plan(
        self,
        *,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        count: int,
    ) -> InterviewPlan:
        years = _coerce_years(profile.get("years"))
        target_type = "intern" if years <= 1 else "formal"
        difficulty = "basic" if target_type == "intern" else "intermediate"
        skills = _extract_skills(profile) or _extract_skills(job_competency) or ["Python"]

        return InterviewPlan(
            target_type=target_type,
            difficulty=difficulty,
            core_skills=skills,
            question_mix={"technical": max(count - 2, 1), "project": 1, "behavioral": 1},
            style="structured",
            notes=[
                "结合简历项目追问候选人的实际职责和技术选择。",
                "要求候选人解释工程权衡，包括测试、监控和降级策略。",
            ],
        )


def _extract_skills(data: dict[str, Any]) -> list[str]:
    skills = data.get("skills")
    if not isinstance(skills, list):
        return []
    return [str(skill).strip() for skill in skills if str(skill).strip()]


def _coerce_years(value: Any) -> float:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0
    return 0
