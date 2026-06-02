from __future__ import annotations

import json
from typing import Any

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
        plan: InterviewPlan,
        job_title: str,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        count: int,
    ) -> tuple[list[dict[str, Any]], LLMResponse]:
        if settings.AI_RUNTIME != "deepseek":
            return self._mock_generate(plan=plan, profile=profile, contexts=contexts, count=count)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是面试题生成 Agent。请严格根据面试计划生成结构化题目，题目需要可用于真实面试。\n{format_instructions}",
                ),
                (
                    "human",
                    "岗位：{job_title}\n能力模型：{job_competency}\n候选人画像：{profile}\n面试计划：{plan}\n上下文：{contexts}\n题目数量：{count}",
                ),
            ]
        )
        result, meta = invoke_structured(
            prompt,
            QuestionGenerationResult,
            {
                "job_title": job_title,
                "job_competency": json.dumps(job_competency, ensure_ascii=False),
                "profile": json.dumps(profile, ensure_ascii=False),
                "plan": plan.model_dump_json(),
                "contexts": json.dumps(contexts, ensure_ascii=False),
                "count": count,
            },
        )
        return [question.model_dump(mode="json") for question in result.questions], meta

    def _mock_generate(
        self,
        *,
        plan: InterviewPlan,
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        count: int,
    ) -> tuple[list[dict[str, Any]], LLMResponse]:
        skills = plan.core_skills or _profile_skills(profile) or ["Python"]
        question_types = ["technical", "project", "system_design", "behavioral"]
        reference_chunk_ids = _context_ids(contexts)
        questions = [
            GeneratedQuestion(
                position=position,
                type=question_types[(position - 1) % len(question_types)],
                difficulty=plan.difficulty,
                skill=skills[(position - 1) % len(skills)],
                question=_build_question(
                    position=position,
                    question_type=question_types[(position - 1) % len(question_types)],
                    skill=skills[(position - 1) % len(skills)],
                ),
                rubric=["解释核心原理", "结合项目经验", "说明测试、监控或降级策略"],
                reference_chunk_ids=reference_chunk_ids,
            ).model_dump(mode="json")
            for position in range(1, count + 1)
        ]
        return questions, LLMResponse(content="[langchain-mock-questions]", model="langchain-mock")


def _profile_skills(profile: dict[str, Any]) -> list[str]:
    skills = profile.get("skills")
    if not isinstance(skills, list):
        return []
    return [str(skill).strip() for skill in skills if str(skill).strip()]


def _context_ids(contexts: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for context in contexts:
        context_id = context.get("id")
        if isinstance(context_id, int):
            ids.append(context_id)
    return ids


def _build_question(*, position: int, question_type: str, skill: str) -> str:
    prompts = {
        "technical": f"请解释 {skill} 的核心原理，并说明你在项目中如何使用它。",
        "project": f"请结合一个项目说明你如何用 {skill} 解决实际问题。",
        "system_design": f"请设计一个涉及 {skill} 的小型系统，并说明关键取舍。",
        "behavioral": f"请描述一次你在使用 {skill} 时遇到分歧或困难后的处理方式。",
    }
    return prompts.get(question_type, f"请围绕 {skill} 回答第 {position} 个面试问题。")
