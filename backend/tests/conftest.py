"""测试 fixtures：每个测试一个内存 SQLite + Mock Provider。

注意：
- 通过 monkeypatch 设置 ENVIRONMENT=test，避免 production 强校验阻塞测试；
- 用 sys.modules 清缓存以保证 settings 重新加载，这是测试期独有的合理 hack。
"""
from __future__ import annotations

import sys
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("AI_RUNTIME", "mock")
    monkeypatch.setenv("EMBEDDING_RUNTIME", "mock")
    monkeypatch.setenv("AUTO_CREATE_TABLES", "true")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "false")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-please-replace-32bytes")
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "1000/minute")
    monkeypatch.setenv("RATE_LIMIT_REGISTER", "1000/minute")
    for name in list(sys.modules):
        if name.startswith("app."):
            del sys.modules[name]

    from app.db.session import SessionLocal, init_db
    from app.main import app
    from app.services.bootstrap import bootstrap_data

    init_db()
    with SessionLocal() as db:
        bootstrap_data(db)

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    payload = {
        "email": "demo@example.com",
        "full_name": "Demo User",
        "password": "Demo12345",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ai-interview.com", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
