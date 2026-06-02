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


def test_non_admin_cannot_access_admin(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/admin/users/stats", headers=auth_headers)
    assert response.status_code == 403
