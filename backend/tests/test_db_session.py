from sqlalchemy.pool import StaticPool

from app.db import session as db_session


def test_file_sqlite_does_not_use_static_pool(monkeypatch, tmp_path):
    monkeypatch.setattr(
        db_session.settings,
        "DATABASE_URL",
        f"sqlite:///{tmp_path / 'dev.db'}",
    )

    kwargs = db_session._build_engine_kwargs()

    assert kwargs["connect_args"] == {"check_same_thread": False}
    assert kwargs.get("poolclass") is not StaticPool


def test_memory_sqlite_keeps_static_pool(monkeypatch):
    monkeypatch.setattr(db_session.settings, "DATABASE_URL", "sqlite:///:memory:")

    kwargs = db_session._build_engine_kwargs()

    assert kwargs["poolclass"] is StaticPool
