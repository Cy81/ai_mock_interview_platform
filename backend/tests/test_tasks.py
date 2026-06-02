"""Celery 任务可调用性测试：不启动 broker，直接调用底层函数。"""
from __future__ import annotations


def test_index_rag_document_task(client) -> None:
    from app.tasks.indexing import index_rag_document

    # bind=True 任务可以用 .run() 跑同步逻辑
    result = index_rag_document.run("knowledge_base", "任务测试", "Celery 任务应支持重试、幂等、监控。", {"source": "test"})
    assert result["chunks"] >= 1
    assert result["status"] in {"ready", "indexing"}
