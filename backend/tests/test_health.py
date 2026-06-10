from __future__ import annotations

from app.core.health import ComponentHealth, get_readiness


def test_readiness_is_ready_when_all_components_are_healthy():
    payload = get_readiness(
        checks=[
            lambda: ComponentHealth(name="database", status="ok", latency_ms=1.2),
            lambda: ComponentHealth(name="redis", status="ok", latency_ms=2.3),
        ]
    )

    assert payload["status"] == "ready"
    assert payload["components"]["database"]["status"] == "ok"
    assert payload["components"]["redis"]["status"] == "ok"


def test_readiness_is_not_ready_when_any_component_fails():
    payload = get_readiness(
        checks=[
            lambda: ComponentHealth(name="database", status="ok", latency_ms=1.2),
            lambda: ComponentHealth(name="redis", status="error", detail="connection refused"),
        ]
    )

    assert payload["status"] == "not_ready"
    assert payload["components"]["redis"]["status"] == "error"
    assert payload["components"]["redis"]["detail"] == "connection refused"


def test_readyz_endpoint_returns_503_when_dependency_is_down(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main,
        "get_readiness",
        lambda: {
            "status": "not_ready",
            "version": "test",
            "environment": "test",
            "components": {"database": {"status": "error", "detail": "boom"}},
        },
        raising=False,
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["components"]["database"]["status"] == "error"
