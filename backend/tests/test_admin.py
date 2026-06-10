"""管理员后台 API 测试：用户管理 / 岗位 CRUD / RAG 写入。"""
from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_admin_user_stats(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/admin/users/stats", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_users"] >= 1
    assert payload["admins"] >= 1


def test_admin_create_and_toggle_job(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    payload = {
        "code": "test_job_" + "x" * 4,
        "title": "临时岗位",
        "description": "用于测试的岗位",
        "required_skills": ["Python"],
        "competency_model": {"core": 1.0},
    }
    create = client.post("/api/v1/admin/jobs", headers=admin_headers, json=payload)
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]

    toggle = client.patch(
        f"/api/v1/admin/jobs/{job_id}/toggle?is_active=false", headers=admin_headers
    )
    assert toggle.status_code == 200
    assert toggle.json()["is_active"] is False

    delete = client.delete(f"/api/v1/admin/jobs/{job_id}", headers=admin_headers)
    assert delete.status_code == 200


def test_admin_rag_document_upsert_and_search(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    create = client.post(
        "/api/v1/admin/rag/documents",
        headers=admin_headers,
        json={
            "rag_type": "question_bank",
            "title": "管理员新增题",
            "content": "请设计一个 FastAPI + Celery 异步任务的幂等机制，要求覆盖重试、超时、回滚。",
            "metadata": {"source": "admin-test"},
        },
    )
    assert create.status_code == 201
    document = create.json()
    assert document["chunk_count"] >= 1

    search = client.post(
        "/api/v1/admin/rag/test-retrieve",
        headers=admin_headers,
        json={"rag_type": "question_bank", "query": "FastAPI 异步任务", "top_k": 3},
    )
    assert search.status_code == 200
    assert search.json()


def test_admin_can_view_rag_document_chunks(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    create = client.post(
        "/api/v1/admin/rag/documents",
        headers=admin_headers,
        json={
            "rag_type": "knowledge_base",
            "title": "LangChain 文档",
            "content": "LangChain Agent 可以组合工具、记忆和检索能力。\n\n文档分块后需要能在后台查看每个 chunk 的内容、序号和 token 数。",
            "metadata": {"source": "chunk-test"},
        },
    )
    assert create.status_code == 201, create.text
    document_id = create.json()["id"]

    chunks = client.get(
        f"/api/v1/admin/rag/documents/{document_id}/chunks",
        headers=admin_headers,
    )
    assert chunks.status_code == 200, chunks.text
    payload = chunks.json()
    assert payload["total"] >= 1
    first = payload["items"][0]
    assert first["document_id"] == document_id
    assert first["chunk_index"] == 0
    assert "LangChain Agent" in first["content"]
    assert first["token_count"] >= 1


def test_admin_can_manage_ai_model_config(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    initial = client.get("/api/v1/admin/ai/config", headers=admin_headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["runtime"] == "mock"

    update = client.put(
        "/api/v1/admin/ai/config",
        headers=admin_headers,
        json={
            "name": "DeepSeek Production",
            "runtime": "deepseek",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-test-1234567890",
            "model": "deepseek-chat",
            "wire_api": "responses",
            "temperature": 0.35,
            "max_tokens": 4096,
            "timeout": 45.0,
            "max_retries": 2,
        },
    )
    assert update.status_code == 200, update.text
    payload = update.json()
    assert payload["name"] == "DeepSeek Production"
    assert payload["runtime"] == "deepseek"
    assert payload["provider"] == "deepseek"
    assert payload["wire_api"] == "responses"
    assert payload["has_api_key"] is True
    assert payload["api_key_masked"] == "sk-t...7890"
    assert "api_key" not in payload

    fetched = client.get("/api/v1/admin/ai/config", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["model"] == "deepseek-chat"
    assert fetched.json()["wire_api"] == "responses"
    assert fetched.json()["temperature"] == 0.35


def test_admin_ai_config_reads_lowercase_wire_api_from_database(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    from sqlalchemy import text

    from app.db.session import SessionLocal
    from app.models.ai_config import AIModelConfig, AIWireAPI

    with SessionLocal() as db:
        db.execute(text("delete from ai_model_configs"))
        db.execute(
            text(
                """
                insert into ai_model_configs
                    (name, runtime, provider, base_url, api_key, model, wire_api)
                values
                    ('Gateway', 'DEEPSEEK', 'DEEPSEEK', 'https://www.sailcode.store',
                     'sk-test', 'grok-4.3-high', 'chat_completions')
                """
            )
        )
        db.commit()

    with SessionLocal() as db:
        config = db.query(AIModelConfig).one()
        assert config.wire_api == AIWireAPI.CHAT_COMPLETIONS

    response = client.get("/api/v1/admin/ai/config", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["wire_api"] == "chat_completions"


def test_admin_can_test_mock_ai_model_config(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    update = client.put(
        "/api/v1/admin/ai/config",
        headers=admin_headers,
        json={
            "name": "Local Mock",
            "runtime": "mock",
            "provider": "mock",
            "base_url": "",
            "api_key": "",
            "model": "mock-interview",
            "wire_api": "chat_completions",
            "temperature": 0.2,
            "max_tokens": 2048,
            "timeout": 10.0,
            "max_retries": 1,
        },
    )
    assert update.status_code == 200, update.text

    tested = client.post("/api/v1/admin/ai/config/test", headers=admin_headers)
    assert tested.status_code == 200, tested.text
    payload = tested.json()
    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["runtime"] == "mock"
    assert payload["model"] == "mock-interview"
    assert payload["latency_ms"] >= 0


def test_admin_model_test_forwards_responses_wire_api_to_openai_gateway(
    monkeypatch,
) -> None:
    from app.models.ai_config import AIProvider, AIRuntime
    from app.services import ai_config_service

    captured: dict = {}
    client_kwargs: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            client_kwargs.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    ai_config_service._test_openai_compatible(
        SimpleNamespace(
            runtime=AIRuntime.DEEPSEEK,
            provider=AIProvider.DEEPSEEK,
            base_url="https://www.sailcode.store",
            api_key="sk-test",
            model="grok-4.3-high",
            wire_api="responses",
            temperature=0.2,
            max_tokens=2048,
            timeout=60,
            max_retries=3,
        )
    )

    assert captured["extra_body"] == {"wire_api": "responses"}
    assert client_kwargs["default_headers"]["User-Agent"] == "Mozilla/5.0"


def test_admin_can_view_ai_usage_after_model_test(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    update = client.put(
        "/api/v1/admin/ai/config",
        headers=admin_headers,
        json={
            "name": "Observable Mock",
            "runtime": "mock",
            "provider": "mock",
            "base_url": "",
            "api_key": "",
            "model": "mock-observable",
            "wire_api": "chat_completions",
            "temperature": 0.2,
            "max_tokens": 2048,
            "timeout": 10.0,
            "max_retries": 1,
        },
    )
    assert update.status_code == 200, update.text

    tested = client.post("/api/v1/admin/ai/config/test", headers=admin_headers)
    assert tested.status_code == 200, tested.text

    summary = client.get("/api/v1/admin/ai/usage/summary", headers=admin_headers)
    assert summary.status_code == 200, summary.text
    totals = summary.json()
    assert totals["total_calls"] >= 1
    assert totals["success_calls"] >= 1
    assert totals["failed_calls"] == 0
    assert totals["total_tokens"] == 0
    assert totals["avg_latency_ms"] >= 0
    assert totals["by_model"][0]["model"] == "mock-observable"

    logs = client.get(
        "/api/v1/admin/ai/usage",
        headers=admin_headers,
        params={"feature": "config_test"},
    )
    assert logs.status_code == 200, logs.text
    payload = logs.json()
    assert payload["total"] >= 1
    first = payload["items"][0]
    assert first["feature"] == "config_test"
    assert first["runtime"] == "mock"
    assert first["provider"] == "mock"
    assert first["model"] == "mock-observable"
    assert first["status"] == "ok"
    assert first["latency_ms"] >= 0
    assert first["total_tokens"] == 0


def test_admin_can_monitor_ai_failures_and_failed_interviews(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    from app.db.session import SessionLocal
    from app.models.ai_config import AIProvider, AIRuntime
    from app.models.ai_usage import AIUsageStatus
    from app.models.interview import Interview, InterviewStatus
    from app.services import ai_usage_service

    with SessionLocal() as db:
        ai_usage_service.record_ai_usage(
            db,
            feature="interview_agent",
            runtime=AIRuntime.DEEPSEEK,
            provider=AIProvider.DEEPSEEK,
            model="deepseek-chat",
            status=AIUsageStatus.FAILED,
            latency_ms=1530,
            error="upstream timeout",
            request_id="req-failed-001",
        )
        failed = Interview(
            user_id=1,
            resume_id=1,
            job_code="python_backend",
            job_title="Python 后端工程师",
            status=InterviewStatus.FAILED,
            question_count=3,
            status_reason="出题失败：upstream timeout",
        )
        db.add(failed)
        db.commit()

    response = client.get(
        "/api/v1/admin/ai/failures/overview",
        headers=admin_headers,
        params={"days": 30},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["failed_ai_calls"] >= 1
    assert payload["failed_interviews"] >= 1
    assert payload["recent_ai_failures"][0]["status"] == "failed"
    assert payload["recent_ai_failures"][0]["error"] == "upstream timeout"
    assert payload["recent_failed_interviews"][0]["status"] == "failed"
    assert "upstream timeout" in payload["recent_failed_interviews"][0]["status_reason"]
    assert payload["failure_rate"] >= 0


def test_non_admin_cannot_access_ai_usage(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/admin/ai/usage/summary", headers=auth_headers)
    assert response.status_code == 403


def test_non_admin_cannot_access_ai_model_config(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/admin/ai/config", headers=auth_headers)
    assert response.status_code == 403


def test_non_admin_cannot_access_admin(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/admin/users/stats", headers=auth_headers)
    assert response.status_code == 403
