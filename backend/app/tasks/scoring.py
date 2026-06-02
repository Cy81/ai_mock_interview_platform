"""异步评分任务：finish_interview 同步链路慢时可走异步。"""
from __future__ import annotations

import structlog

from app.db.session import session_scope
from app.models.interview import Interview
from app.models.user import User
from app.services import interview_service
from app.tasks.celery_app import celery_app


logger = structlog.get_logger("task.scoring")


@celery_app.task(
    name="app.tasks.scoring.score_interview_async",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
    soft_time_limit=240,
    acks_late=True,
)
def score_interview_async(self, interview_id: int) -> dict:
    logger.info("scoring_start", task_id=self.request.id, interview_id=interview_id)
    with session_scope() as db:
        interview = db.get(Interview, interview_id)
        if not interview:
            raise ValueError(f"interview {interview_id} not found")
        user = db.get(User, interview.user_id)
        if not user:
            raise ValueError(f"user {interview.user_id} not found")
        interview = interview_service.finish_interview(db, user, interview_id)
        return {
            "task_id": self.request.id,
            "interview_id": interview.id,
            "score": interview.overall_score,
            "status": interview.status.value,
        }
