"""面试领域服务：状态机 + 子表 + 幂等键 + LLM 评分。

状态流转（同步路径）：
  CREATED -> GENERATING -> IN_PROGRESS -> SCORING -> COMPLETED
                                         -> FAILED
                            -> CANCELLED

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
from app.services.ai_config_service import get_effective_config
from app.services.ai_provider import LLMResponse
from app.services.interview_agents.llm import use_ai_config
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
    conversational: bool = False,
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
    initial_count = 1 if conversational else count
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

    ai_config = get_effective_config(db)
    try:
        try:
            with use_ai_config(ai_config):
                questions, meta = get_interview_agent_runtime().generate_interview_questions(
                    job_title=job.title,
                    job_competency=job.competency_model,
                    profile=profile,
                    contexts=context_payload,
                    count=initial_count,
                )
            if not questions:
                raise DomainError("AI 未返回任何题目，请稍后重试")
        except Exception as exc:
            if not _allow_local_ai_fallback(ai_config):
                logger.exception(
                    "interview_ai_question_generation_failed",
                    interview_id=interview.id,
                    error=str(exc)[:500],
                )
                raise DomainError(
                    f"AI 出题失败：{_ai_error_message(exc)}",
                    status_code=502,
                    code="AI_UPSTREAM_ERROR",
                ) from exc
            logger.exception(
                "interview_ai_question_generation_failed_fallback",
                interview_id=interview.id,
                error=str(exc)[:500],
            )
            questions = _fallback_question_payloads(
                job_title=job.title,
                profile=profile,
                job_skills=[*job.required_skills, *job.nice_to_have_skills],
                contexts=context_payload,
                count=initial_count,
            )
            meta = LLMResponse(content="[fallback-questions]", model="local-fallback")
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


def submit_interview_turn(
    db: Session,
    user: User,
    interview_id: int,
    *,
    question_id: int,
    answer: str,
    duration_ms: int | None = None,
) -> tuple[Interview, InterviewQuestion | None, bool]:
    submit_answer(
        db,
        user,
        interview_id,
        question_id=question_id,
        answer=answer,
        duration_ms=duration_ms,
    )
    interview = _load_full(db, interview_id, user)
    questions = sorted(interview.questions, key=lambda q: q.position)
    current_question = next((q for q in questions if q.id == question_id), None)
    if not current_question:
        raise NotFoundError("问题不存在或不属于当前面试")

    existing_next = next(
        (q for q in questions if q.position > current_question.position),
        None,
    )
    if existing_next:
        return interview, existing_next, False

    if len(questions) >= interview.question_count:
        return interview, None, True

    resume = db.get(Resume, interview.resume_id)
    profile = (resume.parsed_profile if resume else {}) or {}
    job = db.scalar(select(JobDirection).where(JobDirection.code == interview.job_code))
    job_competency = (job.competency_model if job else {}) or {}
    answer_index = {a.question_id: a for a in interview.answers}
    conversation = [
        {
            "position": question.position,
            "skill": question.skill,
            "question": question.question,
            "rubric": question.rubric,
            "answer": (
                answer_index[question.id].answer
                if question.id in answer_index
                else ""
            ),
            "duration_ms": (
                answer_index[question.id].duration_ms
                if question.id in answer_index
                else None
            ),
        }
        for question in questions
    ]
    current_answer = answer_index[current_question.id].answer
    query = (
        f"{interview.job_title} {current_question.skill} {current_question.question} "
        f"{current_answer[:120]}"
    )
    contexts = search(db, "question_bank", query, top_k=6)
    next_position = max(q.position for q in questions) + 1
    context_payload = [context.to_context() for context in contexts]
    ai_config = get_effective_config(db)
    try:
        with use_ai_config(ai_config):
            raw_question, meta = get_interview_agent_runtime().generate_next_question(
                job_title=interview.job_title,
                job_competency=job_competency,
                profile=profile,
                contexts=context_payload,
                conversation=conversation,
                current_question=_question_to_payload(current_question),
                current_answer=current_answer,
                next_position=next_position,
                max_questions=interview.question_count,
            )
        if not raw_question or not str(raw_question.get("question") or "").strip():
            raise DomainError("AI 未返回有效追问题目，请稍后重试")
    except Exception as exc:
        if not _allow_local_ai_fallback(ai_config):
            logger.exception(
                "interview_ai_next_question_generation_failed",
                interview_id=interview.id,
                question_id=current_question.id,
                next_position=next_position,
                error=str(exc)[:500],
            )
            raise DomainError(
                f"AI 追问生成失败：{_ai_error_message(exc)}",
                status_code=502,
                code="AI_UPSTREAM_ERROR",
            ) from exc
        logger.exception(
            "interview_ai_next_question_generation_failed_fallback",
            interview_id=interview.id,
            question_id=current_question.id,
            next_position=next_position,
            error=str(exc)[:500],
        )
        raw_question = _fallback_next_question_payload(
            job_title=interview.job_title,
            profile=profile,
            job_competency=job_competency,
            contexts=context_payload,
            current_question=_question_to_payload(current_question),
            current_answer=current_answer,
            next_position=next_position,
        )
        meta = LLMResponse(content="[fallback-next-question]", model="local-fallback")
    next_question = _build_question_row(interview.id, next_position, raw_question)
    db.add(next_question)
    db.commit()
    next_question_id = next_question.id
    db.expire_all()
    loaded = _load_full(db, interview.id, user)
    loaded_next_question = next(
        (question for question in loaded.questions if question.id == next_question_id),
        None,
    )
    logger.info(
        "interview_turn_generated",
        interview_id=interview.id,
        question_id=current_question.id,
        next_question_id=next_question_id,
        next_position=next_position,
        ai_latency_ms=meta.latency_ms,
        ai_tokens=meta.usage.total_tokens,
    )
    return loaded, loaded_next_question, False


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
        knowledge_payload = [h.to_context() for h in knowledge_hits]
        ai_config = get_effective_config(db)
        try:
            with use_ai_config(ai_config):
                report, meta = get_interview_agent_runtime().score_interview(
                    job_title=interview.job_title,
                    profile=profile,
                    question_answers=qa_pairs,
                    knowledge_contexts=knowledge_payload,
                )
        except Exception as exc:
            if not _allow_local_ai_fallback(ai_config):
                logger.exception(
                    "interview_ai_scoring_failed",
                    interview_id=interview.id,
                    error=str(exc)[:500],
                )
                raise DomainError(
                    f"AI 评分失败：{_ai_error_message(exc)}",
                    status_code=502,
                    code="AI_UPSTREAM_ERROR",
                ) from exc
            logger.exception(
                "interview_ai_scoring_failed_fallback",
                interview_id=interview.id,
                error=str(exc)[:500],
            )
            report = _fallback_score_report(
                job_title=interview.job_title,
                profile=profile,
                question_answers=qa_pairs,
                knowledge_contexts=knowledge_payload,
            )
            meta = LLMResponse(content="[fallback-score-report]", model="local-fallback")
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


def _question_to_payload(question: InterviewQuestion) -> dict[str, Any]:
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


def _fallback_question_payloads(
    *,
    job_title: str,
    profile: dict[str, Any],
    job_skills: list[str],
    contexts: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    skills = _fallback_skills(profile, job_skills)
    context_ids = [
        int(item["id"])
        for item in contexts
        if isinstance(item.get("id"), int)
    ][:3]
    question_types = ["project", "technical", "system_design", "behavioral"]
    difficulty = "basic" if _profile_years(profile) <= 1 else "intermediate"
    questions: list[dict[str, Any]] = []
    for index in range(count):
        skill = skills[index % len(skills)]
        question_type = question_types[index % len(question_types)]
        questions.append(
            {
                "position": index + 1,
                "type": question_type,
                "difficulty": difficulty,
                "skill": skill,
                "question": _fallback_question_text(
                    job_title=job_title,
                    skill=skill,
                    question_type=question_type,
                    profile=profile,
                ),
                "rubric": [
                    "结合真实项目说明个人职责",
                    "解释关键技术选择和工程取舍",
                    "给出测试、监控、指标或上线结果",
                ],
                "reference_chunk_ids": context_ids,
            }
        )
    return questions


def _fallback_next_question_payload(
    *,
    job_title: str,
    profile: dict[str, Any],
    job_competency: dict[str, Any],
    contexts: list[dict[str, Any]],
    current_question: dict[str, Any],
    current_answer: str,
    next_position: int,
) -> dict[str, Any]:
    skill = str(current_question.get("skill") or "").strip()
    if not skill:
        skill = _fallback_skills(profile, _job_competency_skills(job_competency))[0]
    answer_hint = " ".join(current_answer.split())[:80]
    previous_question = str(current_question.get("question") or "").strip()[:80]
    context_ids = [
        int(item["id"])
        for item in contexts
        if isinstance(item.get("id"), int)
    ][:3]
    if answer_hint:
        question = (
            f"刚才你提到「{answer_hint}」。请继续围绕 {skill} 展开："
            f"在面向 {job_title} 的真实项目里，你会如何落地、验证并处理失败场景？"
        )
    else:
        question = (
            f"刚才这道题「{previous_question}」还可以继续深入。"
            f"请结合 {skill} 说明你的具体实现步骤、取舍和验证方式。"
        )
    return {
        "position": next_position,
        "type": "technical",
        "difficulty": "intermediate",
        "skill": skill,
        "question": question,
        "rubric": [
            "回应上一题答案中的具体细节",
            "说明实现步骤、关键取舍和风险处理",
            "给出验证方式、数据指标或复盘结论",
        ],
        "reference_chunk_ids": context_ids,
    }


def _fallback_skills(profile: dict[str, Any], job_skills: list[str]) -> list[str]:
    profile_skills = profile.get("skills")
    if isinstance(profile_skills, list):
        skills = [str(item).strip() for item in profile_skills if str(item).strip()]
        if skills:
            return skills[:8]
    skills = [str(item).strip() for item in job_skills if str(item).strip()]
    return skills[:8] or ["Python", "FastAPI", "项目经验"]


def _job_competency_skills(job_competency: dict[str, Any]) -> list[str]:
    skills: list[str] = []
    for value in job_competency.values():
        if isinstance(value, str):
            skills.append(value)
        elif isinstance(value, list):
            skills.extend(str(item) for item in value)
        elif isinstance(value, dict):
            skills.extend(_job_competency_skills(value))
    return [skill.strip() for skill in skills if skill.strip()]


def _allow_local_ai_fallback(config: Any) -> bool:
    runtime = _config_value(getattr(config, "runtime", "mock"))
    provider = _config_value(getattr(config, "provider", "mock"))
    return runtime == "mock" or provider == "mock"


def _config_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _ai_error_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:300]


def _fallback_question_text(
    *,
    job_title: str,
    skill: str,
    question_type: str,
    profile: dict[str, Any],
) -> str:
    projects = profile.get("projects")
    project_hint = ""
    if isinstance(projects, list):
        project_hint = next((str(item).strip() for item in projects if str(item).strip()), "")
    if question_type == "project":
        suffix = f"可以结合「{project_hint[:50]}」展开。" if project_hint else "请结合一个真实项目展开。"
        return f"面向 {job_title}，请说明你在项目中如何使用 {skill} 解决实际问题。{suffix}"
    if question_type == "system_design":
        return f"请设计一个和 {skill} 相关的小型系统，说明核心模块、数据流、异常处理和扩展方式。"
    if question_type == "behavioral":
        return f"请讲一次你在 {skill} 相关工作中遇到分歧、故障或压力时的处理过程和复盘。"
    return f"请解释 {skill} 的核心原理，并说明你在生产项目中如何验证它的效果。"


def _fallback_score_report(
    *,
    job_title: str,
    profile: dict[str, Any],
    question_answers: list[dict[str, Any]],
    knowledge_contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    _ = (profile, knowledge_contexts)
    question_scores: list[dict[str, Any]] = []
    scores: list[float] = []
    for index, item in enumerate(question_answers, start=1):
        answer = str(item.get("answer") or "").strip()
        rubric = item.get("rubric") if isinstance(item.get("rubric"), list) else []
        score = _fallback_answer_score(answer, rubric)
        scores.append(score)
        question_scores.append(
            {
                "position": item.get("position") or index,
                "score": score,
                "comment": _fallback_score_comment(answer, score),
            }
        )

    overall = round(sum(scores) / len(scores), 1) if scores else 0.0
    level = "优秀" if overall >= 85 else "良好" if overall >= 75 else "可培养" if overall >= 60 else "需补强"
    dimension_scores = {
        "技术理解": round(min(100.0, overall + 2), 1),
        "项目表达": round(overall, 1),
        "工程落地": round(max(0.0, overall - 3), 1),
        "复盘意识": round(max(0.0, overall - 5), 1),
    }
    return {
        "source": "local-fallback",
        "overall_score": overall,
        "level": level,
        "summary": (
            f"本报告由本地规则评分生成：候选人面向 {job_title} 的回答已完成基础评估，"
            "建议在大模型恢复后重新生成更细致的 AI 报告。"
        ),
        "dimension_scores": dimension_scores,
        "question_scores": question_scores,
        "strengths": [
            "能够围绕问题给出项目化回答",
            "回答中包含一定技术关键词和实施思路",
        ],
        "improvements": [
            "补充更具体的架构图、接口边界和数据流",
            "增加测试、监控、降级、成本和安全方面的量化说明",
        ],
        "learning_plan": [
            "复盘一个最有代表性的项目，整理目标、职责、技术取舍和上线结果",
            "针对薄弱题目补充 STAR 案例和生产问题处理记录",
        ],
        "next_practice": [
            "重新进行一轮追问式面试，重点验证工程细节和复盘能力",
        ],
    }


def _fallback_answer_score(answer: str, rubric: list[Any]) -> float:
    if not answer:
        return 0.0
    score = 52.0
    score += min(18.0, len(answer) / 12)
    evidence_terms = ("项目", "接口", "测试", "监控", "指标", "上线", "降级", "安全", "成本", "复盘", "RAG", "LangChain")
    score += min(18.0, sum(1 for term in evidence_terms if term in answer) * 2.0)
    if rubric:
        matched = sum(1 for item in rubric if str(item).strip() and str(item).strip()[:2] in answer)
        score += min(8.0, matched * 2.0)
    return round(min(92.0, max(45.0, score)), 1)


def _fallback_score_comment(answer: str, score: float) -> str:
    if not answer:
        return "未提交有效回答，无法评价。"
    if score >= 80:
        return "回答结构较完整，具备项目化表达，可继续补充量化结果和异常处理细节。"
    if score >= 65:
        return "回答覆盖了基本思路，但需要进一步说明具体职责、技术取舍和验证方式。"
    return "回答偏概括，建议补充真实项目背景、实施步骤、结果指标和复盘。"


def _profile_years(profile: dict[str, Any]) -> float:
    value = profile.get("years")
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
