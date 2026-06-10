from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from app.services.ai_provider import LLMResponse
from app.services.interview_agents.llm import invoke_structured, is_chat_model_enabled
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
        if not is_chat_model_enabled():
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
        return [question.model_dump(mode="json") for question in result.questions[:count]], meta

    def generate_next(
        self,
        *,
        job_title: str,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        conversation: list[dict[str, Any]],
        current_question: dict[str, Any],
        current_answer: str,
        next_position: int,
        max_questions: int,
    ) -> tuple[dict[str, Any], LLMResponse]:
        if not is_chat_model_enabled():
            return self._mock_next_question(
                job_competency=job_competency,
                profile=profile,
                contexts=contexts,
                conversation=conversation,
                current_question=current_question,
                current_answer=current_answer,
                next_position=next_position,
                max_questions=max_questions,
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是对话式技术面试官 Agent。请根据候选人简历、岗位能力模型、历史问答和刚才的回答，"
                    "生成下一轮结构化面试问题。问题必须像真实面试追问一样承接上一轮回答，不能机械切题；"
                    "必须继续验证简历真实性、项目细节、工程取舍、测试监控和结果指标。\n{format_instructions}",
                ),
                (
                    "human",
                    "岗位：{job_title}\n能力模型：{job_competency}\n候选人画像：{profile}\n"
                    "检索上下文：{contexts}\n历史问答：{conversation}\n当前题目：{current_question}\n"
                    "当前回答：{current_answer}\n下一轮序号：{next_position}\n最大轮数：{max_questions}",
                ),
            ]
        )
        result, meta = invoke_structured(
            prompt,
            GeneratedQuestion,
            {
                "job_title": job_title,
                "job_competency": json.dumps(job_competency, ensure_ascii=False),
                "profile": json.dumps(profile, ensure_ascii=False),
                "contexts": json.dumps(contexts, ensure_ascii=False),
                "conversation": json.dumps(conversation, ensure_ascii=False),
                "current_question": json.dumps(current_question, ensure_ascii=False),
                "current_answer": current_answer,
                "next_position": next_position,
                "max_questions": max_questions,
            },
        )
        question = result.model_copy(update={"position": next_position}).model_dump(mode="json")
        return question, meta

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

    def _mock_next_question(
        self,
        *,
        job_competency: dict[str, Any],
        profile: dict[str, Any],
        contexts: list[dict[str, Any]],
        conversation: list[dict[str, Any]],
        current_question: dict[str, Any],
        current_answer: str,
        next_position: int,
        max_questions: int,
    ) -> tuple[dict[str, Any], LLMResponse]:
        skills = _profile_skills(profile) or _profile_skills(job_competency) or ["Python"]
        current_skill = str(current_question.get("skill") or "").strip()
        if current_skill and current_skill in skills:
            skill = current_skill
        else:
            skill = skills[(next_position - 1) % len(skills)]

        projects = profile.get("projects")
        project_hint = ""
        if isinstance(projects, list):
            project_hint = next((str(item).strip() for item in projects if str(item).strip()), "")
        answer_hint = _compact_text(current_answer, 36) or "你的上一轮回答"
        difficulty = "basic" if _coerce_years(profile.get("years")) <= 1 else "intermediate"
        if next_position >= max_questions:
            question_type = "behavioral"
        elif next_position % 3 == 0:
            question_type = "system_design"
        else:
            question_type = "project"

        if project_hint:
            question_text = (
                f"刚才你提到「{answer_hint}」。请结合简历里的项目「{_compact_text(project_hint, 34)}」，"
                f"继续说明你在 {skill} 相关工作中的具体实现、关键取舍、验证指标和失败兜底。"
            )
        else:
            question_text = (
                f"刚才你提到「{answer_hint}」。请继续围绕 {skill} 说明一个真实项目场景："
                "你负责了什么、怎么验证效果、遇到风险时如何处理？"
            )

        question = GeneratedQuestion(
            position=next_position,
            type=question_type,
            difficulty=difficulty,
            skill=skill,
            question=question_text,
            rubric=[
                "承接上一轮回答，不泛泛而谈",
                "结合简历项目说明个人职责",
                "给出测试、监控、指标或上线结果",
                "说明工程取舍、风险和降级策略",
            ],
            reference_chunk_ids=_context_ids(contexts),
        )
        return question.model_dump(mode="json"), LLMResponse(
            content="[langchain-mock-next-question]",
            model="langchain-mock",
        )


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


def _compact_text(value: str, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit]}..."


def _build_question(*, position: int, question_type: str, skill: str) -> str:
    prompts = {
        "technical": f"请解释 {skill} 的核心原理，并说明你在项目中如何使用它。",
        "project": f"请结合一个项目说明你如何用 {skill} 解决实际问题。",
        "system_design": f"请设计一个涉及 {skill} 的小型系统，并说明关键取舍。",
        "behavioral": f"请描述一次你在使用 {skill} 时遇到分歧或困难后的处理方式。",
    }
    return prompts.get(question_type, f"请围绕 {skill} 回答第 {position} 个面试问题。")
