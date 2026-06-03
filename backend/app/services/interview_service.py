"""面试领域服务：状态机 + 子表 + 幂等键 + LLM 评分。

状态流转（同步路径）：
  CREATED -> GENERATING -> IN_PROGRESS -> SCORING -> COMPLETED
                                         \-> FAILED
                            \-> CANCELLED

并发与幂等：
- create_interview 接受 idempotency_key，重复请求直接返回旧面试；
- submit_answer 用 question_id 唯一约束保证同一题不会重复入库，重复提交则更新答案；
- finish_interview 用 SCORING 中间态防止双触发，失败回滚到 IN_PROGRESS。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models.interview import (
    Difficulty,
    Interview,
    InterviewAnswer,
    InterviewQuestion,
    InterviewStatus,
    QuestionType,
)
from app.models.job import JobDirection
from app.models.resume import Resume
from app.models.user import User
from app.services.interview_agents.runtime import get_interview_agent_runtime
from app.services.rag_service import search


logger = structlog.get_logger("interview")


# =====================================================================
# 创建面试 + 出题
# =====================================================================


def create_interview(
    db: Session,
    user: User,
    *,
    resume_id: int,
    job_code: str,
    question_count: int = 6,
    idempotency_key: str | None = None,
) -> Interview:
    if idempotency_key:
        existing = db.scalar(
            select(Interview).where(
                Interview.user_id == user.id,
                Interview.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return _load_full(db, existing.id, user)

    resume = db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id:
        raise NotFoundError("简历不存在或无权限访问")

    job = db.scalar(
        select(JobDirection).where(JobDirection.code == job_code.strip())
    )
    if not job or not job.is_active:
        raise NotFoundError("岗位方向不存在或已下线")

    count = max(1, min(question_count, 12))
    interview = Interview(
        user_id=user.id,
        resume_id=resume.id,
        job_code=job.code,
        job_title=job.title,
        status=InterviewStatus.GENERATING,
        question_count=count,
        idempotency_key=idempotency_key,
        started_at=_now(),
    )
    db.add(interview)
    db.flush()

    profile = resume.parsed_profile or {}
    query = (
        f"{job.title} {' '.join(profile.get('skills', []))} 面试题"
    )
    contexts = search(db, "question_bank", query, top_k=8)
    context_payload = [c.to_context() for c in contexts]

    try:
        questions, meta = get_interview_agent_runtime().generate_interview_questions(
            job_title=job.title,
            job_competency=job.competency_model,
            profile=profile,
            contexts=context_payload,
            count=count,
        )
        if not questions:
            raise DomainError("AI 未返回任何题目，请稍后重试")
        rows = [_build_question_row(interview.id, idx, q) for idx, q in enumerate(questions, start=1)]
        db.add_all(rows)
        interview.status = InterviewStatus.IN_PROGRESS
        db.commit()
        logger.info(
            "interview_created",
            interview_id=interview.id,
            user_id=user.id,
            ai_latency_ms=meta.latency_ms,
            ai_tokens=meta.usage.total_tokens,
        )
    except Exception as exc:
        db.rollback()
        # 重新加载并标失败
        interview = db.get(Interview, interview.id)
        if interview:
            interview.status = InterviewStatus.FAILED
            interview.status_reason = f"出题失败：{exc!s}"[:1000]
            db.commit()
        raise

    return _load_full(db, interview.id, user)


def _build_question_row(
    interview_id: int, position: int, raw: dict[str, Any]
) -> InterviewQuestion:
    qtype = _coerce_enum(QuestionType, raw.get("type"), QuestionType.TECHNICAL)
    diff = _coerce_enum(Difficulty, raw.get("difficulty"), Difficulty.INTERMEDIATE)
    rubric = raw.get("rubric") or []
    if not isinstance(rubric, list):
        rubric = [str(rubric)]
    return InterviewQuestion(
        interview_id=interview_id,
        position=position,
        type=qtype,
        difficulty=diff,
        skill=str(raw.get("skill") or "通用"),
        question=str(raw.get("question") or "请结合项目经验回答这道题。"),
        rubric=[str(item) for item in rubric][:6],
        reference_chunk_ids=[int(x) for x in (raw.get("reference_chunk_ids") or []) if isinstance(x, (int, str)) and str(x).isdigit()][:6],
    )


# =====================================================================
# 提交回答（幂等更新）
# =====================================================================


def submit_answer(
    db: Session,
    user: User,
    interview_id: int,
    *,
    question_id: int,
    answer: str,
    duration_ms: int | None = None,
) -> InterviewAnswer:
    interview = _get_owned(db, interview_id, user)
    if interview.status not in (InterviewStatus.IN_PROGRESS, InterviewStatus.GENERATING):
        raise ConflictError("当前面试状态不允许提交回答")

    question = db.get(InterviewQuestion, question_id)
    if not question or question.interview_id != interview.id:
        raise NotFoundError("问题不存在或不属于当前面试")

    clean = answer.strip()
    if not clean:
        raise DomainError("回答内容不能为空")

    record = db.scalar(
        select(InterviewAnswer).where(InterviewAnswer.question_id == question.id)
    )
    if record:
        record.answer = clean
        record.char_count = len(clean)
        record.duration_ms = duration_ms
        record.answered_at = _now()
    else:
        record = InterviewAnswer(
            interview_id=interview.id,
            question_id=question.id,
            answer=clean,
            char_count=len(clean),
            duration_ms=duration_ms,
            answered_at=_now(),
        )
        db.add(record)
    if interview.status == InterviewStatus.GENERATING:
        interview.status = InterviewStatus.IN_PROGRESS
    db.commit()
    db.refresh(record)
    return record


# =====================================================================
# 完成面试 + 评分
# =====================================================================


def finish_interview(db: Session, user: User, interview_id: int) -> Interview:
    interview = _get_owned(db, interview_id, user)
    if interview.status == InterviewStatus.COMPLETED:
        return _load_full(db, interview.id, user)
    if interview.status != InterviewStatus.IN_PROGRESS:
        raise ConflictError(f"当前状态 {interview.status.value} 不允许完成")
    if not interview.answers:
        raise ConflictError("请至少提交一道题的回答后再生成报告")

    interview.status = InterviewStatus.SCORING
    db.commit()

    resume = db.get(Resume, interview.resume_id)
    profile = (resume.parsed_profile if resume else {}) or {}
    questions = sorted(interview.questions, key=lambda q: q.position)
    answer_index = {a.question_id: a for a in interview.answers}
    qa_pairs = [
        {
            "position": q.position,
            "skill": q.skill,
            "question": q.question,
            "rubric": q.rubric,
            "answer": (answer_index.get(q.id).answer if answer_index.get(q.id) else ""),
            "duration_ms": (answer_index.get(q.id).duration_ms if answer_index.get(q.id) else None),
        }
        for q in questions
    ]
    knowledge_hits = search(
        db,
        "knowledge_base",
        f"{interview.job_title} 面试评价 改进建议",
        top_k=5,
    )

    try:
        report, meta = get_interview_agent_runtime().score_interview(
            job_title=interview.job_title,
            profile=profile,
            question_answers=qa_pairs,
            knowledge_contexts=[h.to_context() for h in knowledge_hits],
        )
        interview.score_report = report
        interview.overall_score = float(report.get("overall_score") or 0)
        interview.status = InterviewStatus.COMPLETED
        interview.completed_at = _now()
        # 把每题分写回子表
        for item in report.get("question_scores") or []:
            try:
                pos = int(item.get("position"))
            except (TypeError, ValueError):
                continue
            target_q = next((q for q in questions if q.position == pos), None)
            if not target_q:
                continue
            ans = answer_index.get(target_q.id)
            if not ans:
                continue
            ans.score = float(item.get("score") or 0)
            ans.comment = str(item.get("comment") or "")[:1000]
        db.commit()
        db.refresh(interview)
        logger.info(
            "interview_completed",
            interview_id=interview.id,
            score=interview.overall_score,
            ai_latency_ms=meta.latency_ms,
        )
    except Exception as exc:
        db.rollback()
        # 回滚到 IN_PROGRESS，让用户可以重试
        interview = db.get(Interview, interview_id)
        if interview:
            interview.status = InterviewStatus.IN_PROGRESS
            interview.status_reason = f"评分失败：{exc!s}"[:1000]
            db.commit()
        raise

    return _load_full(db, interview.id, user)


def cancel_interview(db: Session, user: User, interview_id: int) -> Interview:
    interview = _get_owned(db, interview_id, user)
    if interview.status in (InterviewStatus.COMPLETED, InterviewStatus.CANCELLED):
        return interview
    interview.status = InterviewStatus.CANCELLED
    interview.status_reason = "用户取消"
    db.commit()
    db.refresh(interview)
    return interview


# =====================================================================
# 查询
# =====================================================================


def list_interviews(
    db: Session, user: User, *, page: int = 1, page_size: int = 20
) -> tuple[list[Interview], int]:
    from sqlalchemy import func

    total = db.scalar(
        select(func.count(Interview.id)).where(Interview.user_id == user.id)
    ) or 0
    items = list(
        db.scalars(
            select(Interview)
            .where(Interview.user_id == user.id)
            .options(selectinload(Interview.questions), selectinload(Interview.answers))
            .order_by(Interview.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return items, total


def get_interview(db: Session, user: User, interview_id: int) -> Interview:
    return _load_full(db, interview_id, user)


# =====================================================================
# 内部
# =====================================================================


def _get_owned(db: Session, interview_id: int, user: User) -> Interview:
    interview = db.get(Interview, interview_id)
    if not interview or interview.user_id != user.id:
        raise NotFoundError("面试不存在或无权限访问")
    return interview


def _load_full(db: Session, interview_id: int, user: User) -> Interview:
    interview = db.scalar(
        select(Interview)
        .where(Interview.id == interview_id, Interview.user_id == user.id)
        .options(
            selectinload(Interview.questions).selectinload(InterviewQuestion.answer),
            selectinload(Interview.answers),
        )
    )
    if not interview:
        raise NotFoundError("面试不存在或无权限访问")
    return interview


def _coerce_enum(enum_cls, value, default):
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            return default
    return default


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
