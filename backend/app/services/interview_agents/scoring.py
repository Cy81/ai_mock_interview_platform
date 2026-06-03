from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.ai_provider import LLMResponse
from app.services.interview_agents.llm import invoke_structured
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
        if settings.AI_RUNTIME == "deepseek":
            return self._score_with_langchain(
                job_title=job_title,
                profile=profile,
                question_answers=question_answers,
                knowledge_contexts=knowledge_contexts,
            )

        return self._mock_score(
            job_title=job_title,
            profile=profile,
            question_answers=question_answers,
            knowledge_contexts=knowledge_contexts,
        )

    def _mock_score(
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

    def _score_with_langchain(
        self,
        *,
        job_title: str,
        profile: dict[str, Any],
        question_answers: list[dict[str, Any]],
        knowledge_contexts: list[dict[str, Any]],
    ) -> tuple[ScoreResult, LLMResponse]:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是技术面试评分 Agent。请严格按给定题目、rubric 和候选人回答生成结构化评分。"
                    "评分必须客观，包含总分、等级、维度分、逐题分、优势、改进建议和学习计划。\n"
                    "{format_instructions}",
                ),
                (
                    "human",
                    "岗位：{job_title}\n候选人画像：{profile}\n问答记录：{question_answers}\n"
                    "参考上下文：{knowledge_contexts}",
                ),
            ]
        )
        return invoke_structured(
            prompt,
            ScoreResult,
            {
                "job_title": job_title,
                "profile": json.dumps(profile, ensure_ascii=False),
                "question_answers": json.dumps(question_answers, ensure_ascii=False),
                "knowledge_contexts": json.dumps(knowledge_contexts, ensure_ascii=False),
            },
        )
