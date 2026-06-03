from __future__ import annotations

from collections.abc import Iterator
import json
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.interview_agents.llm import get_chat_model


class FollowupAgent:
    def stream(self, **kwargs: Any) -> Iterator[str]:
        if settings.AI_RUNTIME == "deepseek":
            yield from self._stream_with_langchain(**kwargs)
            return

        yield from self._mock_stream()

    def _mock_stream(self) -> Iterator[str]:
        feedback = "回答覆盖了核心思路，可以继续补充项目细节、工程权衡和验证方式。"
        for index in range(0, len(feedback), 8):
            yield feedback[index:index + 8]

    def _stream_with_langchain(self, **kwargs: Any) -> Iterator[str]:
        llm = get_chat_model()
        if llm is None:
            raise RuntimeError("LangChain follow-up requires a chat model")

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是技术面试官。请基于候选人的当前回答给出一段简短、具体、可执行的追问或点评，"
                    "重点关注工程取舍、测试、监控、异常处理和上线效果。不要重复题目，不超过120字。",
                ),
                (
                    "human",
                    "岗位：{job_title}\n候选人画像：{profile}\n题目：{question}\n"
                    "回答：{answer}\n参考上下文：{knowledge_contexts}",
                ),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        variables = {
            "job_title": kwargs.get("job_title", ""),
            "profile": json.dumps(kwargs.get("profile") or {}, ensure_ascii=False),
            "question": json.dumps(kwargs.get("question") or {}, ensure_ascii=False),
            "answer": str(kwargs.get("answer") or ""),
            "knowledge_contexts": json.dumps(
                kwargs.get("knowledge_contexts") or [],
                ensure_ascii=False,
            ),
        }
        for chunk in chain.stream(variables):
            if chunk:
                yield str(chunk)
