"""Interview routes for /api/v1/interviews/*."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import DomainError
from app.db.session import SessionLocal, get_db
from app.models.interview import InterviewQuestion
from app.models.resume import Resume
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.interview import (
    AnswerSubmit,
    InterviewBrief,
    InterviewCreate,
    InterviewRead,
)
from app.services import interview_service
from app.services.ai_provider import get_ai_provider
from app.services.interview_agents.events import error_event, format_sse
from app.services.interview_agents.runtime import get_interview_agent_runtime
from app.services.rag_service import search


router = APIRouter(prefix="/interviews", tags=["面试"])


@router.post(
    "",
    response_model=InterviewRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建面试并生成题目",
)
def create_interview(
    payload: InterviewCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = interview_service.create_interview(
        db,
        user,
        resume_id=payload.resume_id,
        job_code=payload.job_code,
        question_count=payload.question_count,
        idempotency_key=payload.idempotency_key,
    )
    return InterviewRead.model_validate(interview)


@router.get("", response_model=Page[InterviewBrief], summary="分页查询当前用户的面试")
def list_interviews(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = interview_service.list_interviews(db, user, page=page, page_size=page_size)
    return Page[InterviewBrief].of(
        [InterviewBrief.model_validate(i) for i in items], total, page, page_size
    )


@router.get("/{interview_id}", response_model=InterviewRead, summary="获取面试详情")
def get_interview(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = interview_service.get_interview(db, user, interview_id)
    return InterviewRead.model_validate(interview)


@router.post(
    "/{interview_id}/answers",
    response_model=InterviewRead,
    summary="提交回答（同一题重复提交会覆盖）",
)
def submit_answer(
    interview_id: int,
    payload: AnswerSubmit,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview_service.submit_answer(
        db,
        user,
        interview_id,
        question_id=payload.question_id,
        answer=payload.answer,
        duration_ms=payload.duration_ms,
    )
    interview = interview_service.get_interview(db, user, interview_id)
    return InterviewRead.model_validate(interview)


@router.post(
    "/{interview_id}/finish",
    response_model=InterviewRead,
    summary="完成面试并生成评分报告",
)
def finish(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = interview_service.finish_interview(db, user, interview_id)
    return InterviewRead.model_validate(interview)


@router.post(
    "/{interview_id}/cancel",
    response_model=InterviewRead,
    summary="取消面试",
)
def cancel(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = interview_service.cancel_interview(db, user, interview_id)
    return InterviewRead.model_validate(interview)


@router.delete("/{interview_id}", response_model=Message, summary="删除面试记录")
def delete_interview(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.core.exceptions import NotFoundError
    from app.models.interview import Interview

    interview = db.get(Interview, interview_id)
    if not interview or interview.user_id != user.id:
        raise NotFoundError("面试不存在或无权限访问")
    db.delete(interview)
    db.commit()
    return Message(message="已删除")


@router.get(
    "/{interview_id}/stream",
    summary="结构化面试流（SSE）",
    response_class=StreamingResponse,
)
def stream_interview(
    interview_id: int,
    mode: Literal["followup", "scoring"] = "followup",
    question_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if mode == "followup":
        followup_payload = _prepare_followup_stream_payload(db, user, interview_id, question_id)
        db.close()
        return StreamingResponse(
            _followup_event_stream(followup_payload),
            media_type="text/event-stream",
        )

    scoring_payload = _prepare_scoring_stream_payload(db, user, interview_id)
    db.close()
    return StreamingResponse(
        _scoring_event_stream(scoring_payload),
        media_type="text/event-stream",
    )


@router.get(
    "/{interview_id}/answer/stream",
    summary="流式追问（SSE，演示）",
    response_class=StreamingResponse,
)
def stream_answer(
    interview_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = interview_service.get_interview(db, user, interview_id)
    questions = sorted(interview.questions, key=lambda q: q.position)
    if not questions:
        raise DomainError("面试还没有题目")

    system = "你是技术面试官，请给候选人一段简短的引导和澄清，不超过80字。"
    user_prompt = f"岗位：{interview.job_title}\n首题：{questions[0].question}"

    def event_stream():
        for token in get_ai_provider().chat_stream(system, user_prompt):
            yield f"data: {token}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _prepare_followup_stream_payload(
    db: Session,
    user: User,
    interview_id: int,
    question_id: int | None,
) -> dict[str, object]:
    interview = interview_service.get_interview(db, user, interview_id)
    if question_id is None:
        raise DomainError("followup mode requires question_id")

    question = next((item for item in interview.questions if item.id == question_id), None)
    if not question:
        raise DomainError("题目不存在或不属于当前面试")

    answer = question.answer
    if not answer:
        raise DomainError("该题尚未提交答案")

    resume = db.get(Resume, interview.resume_id)
    profile = (resume.parsed_profile if resume else {}) or {}
    knowledge_contexts = [
        hit.to_context()
        for hit in search(
            db,
            "question_bank",
            f"{interview.job_title} {question.question}",
            top_k=5,
        )
    ]
    return {
        "interview_id": interview.id,
        "question": _question_payload(question),
        "answer": {
            "id": answer.id,
            "text": answer.answer,
        },
        "job_title": interview.job_title,
        "profile": profile,
        "knowledge_contexts": knowledge_contexts,
    }


def _prepare_scoring_stream_payload(db: Session, user: User, interview_id: int) -> dict[str, object]:
    interview = interview_service.get_interview(db, user, interview_id)
    if not interview.answers:
        raise DomainError("请至少提交一道题的回答后再生成报告")
    return {
        "interview_id": interview.id,
        "user": user,
    }


def _followup_event_stream(payload: dict[str, object]):
    interview_id = int(payload["interview_id"])
    question = payload["question"]
    answer = payload["answer"]
    job_title = str(payload["job_title"])
    profile = payload["profile"]
    knowledge_contexts = payload["knowledge_contexts"]

    yield format_sse(
        "followup_started",
        {
            "interview_id": interview_id,
            "question_id": question["id"],
            "answer_id": answer["id"],
        },
    )

    chunks: list[str] = []
    try:
        for token in get_interview_agent_runtime().stream_followup(
            interview_id=interview_id,
            question_id=int(question["id"]),
            answer=str(answer["text"]),
            job_title=job_title,
            profile=profile,  # already detached plain data
            question=question,
            knowledge_contexts=knowledge_contexts,
        ):
            chunks.append(token)
            yield format_sse(
                "followup_delta",
                {
                    "interview_id": interview_id,
                    "question_id": question["id"],
                    "content": token,
                },
            )
    except Exception as exc:
        yield error_event(str(exc), stage="followup", interview_id=interview_id)
        yield format_sse("done", {"interview_id": interview_id})
        return

    yield format_sse(
        "followup_done",
        {
            "interview_id": interview_id,
            "question_id": question["id"],
            "content": "".join(chunks),
        },
    )
    yield format_sse("done", {"interview_id": interview_id})


def _scoring_event_stream(payload: dict[str, object]):
    interview_id = int(payload["interview_id"])
    user = payload["user"]
    yield format_sse("scoring_started", {"interview_id": interview_id})

    try:
        with SessionLocal() as stream_db:
            interview = interview_service.finish_interview(stream_db, user, interview_id)
            report = interview.score_report
            yield format_sse(
                "scoring_done",
                {
                    "interview_id": interview.id,
                    "status": interview.status.value,
                    "overall_score": interview.overall_score,
                },
            )
            yield format_sse(
                "report_ready",
                {
                    "interview_id": interview.id,
                    "report": report,
                },
            )
    except Exception as exc:
        yield error_event(str(exc), stage="scoring", interview_id=interview_id)
        yield format_sse("done", {"interview_id": interview_id})
        return

    yield format_sse("done", {"interview_id": interview_id})


def _question_payload(question: InterviewQuestion) -> dict[str, object]:
    return {
        "id": question.id,
        "position": question.position,
        "type": question.type.value,
        "difficulty": question.difficulty.value,
        "skill": question.skill,
        "question": question.question,
        "rubric": list(question.rubric),
        "reference_chunk_ids": list(question.reference_chunk_ids),
    }
