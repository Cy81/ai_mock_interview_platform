"""客户端：面试路由 (/api/v1/interviews/*)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
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
        from app.core.exceptions import DomainError

        raise DomainError("面试还没有题目")

    system = "你是技术面试官，请给候选人一段简短的引导和澄清，不超过 80 字。"
    user_prompt = f"岗位：{interview.job_title}\n首题：{questions[0].question}"

    def event_stream():
        for token in get_ai_provider().chat_stream(system, user_prompt):
            yield f"data: {token}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
