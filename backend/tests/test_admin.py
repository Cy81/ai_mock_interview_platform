"""管理员后台 API 测试：用户管理 / 岗位 CRUD / RAG 写入。"""
from __future__ import annotations

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
    assert payload["has_api_key"] is True
    assert payload["api_key_masked"] == "sk-t...7890"
    assert "api_key" not in payload

    fetched = client.get("/api/v1/admin/ai/config", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["model"] == "deepseek-chat"
    assert fetched.json()["temperature"] == 0.35


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
