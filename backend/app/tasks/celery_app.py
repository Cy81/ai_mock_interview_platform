"""Celery 应用：生产级配置。"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "ai_mock_interview",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.indexing", "app.tasks.scoring"],
)

celery_app.conf.update(
    # 序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # 可靠性
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,

    # 限流与超时
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=2,
    worker_max_tasks_per_child=200,

    # 结果保留
    result_expires=24 * 3600,

    # 路由
    task_routes={
        "app.tasks.indexing.*": {"queue": "indexing"},
        "app.tasks.scoring.*": {"queue": "scoring"},
    },
    task_default_queue="default",
)
