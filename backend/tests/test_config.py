from __future__ import annotations

import importlib
import sys

import pytest


def _reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    sys.modules.pop("app.core.config", None)
    return importlib.import_module("app.core.config")


def test_settings_treats_release_debug_env_as_false(monkeypatch):
    monkeypatch.setenv("DEBUG", "release")
    sys.modules.pop("app.core.config", None)

    config = importlib.import_module("app.core.config")

    assert config.settings.DEBUG is False


def test_production_rejects_default_admin_password(monkeypatch):
    with pytest.raises(ValueError, match="DEFAULT_ADMIN_PASSWORD"):
        _reload_config(
            monkeypatch,
            ENVIRONMENT="production",
            DEBUG="false",
            DATABASE_URL="postgresql+psycopg://user:pass@db:5432/app",
            AUTO_CREATE_TABLES="false",
            SECRET_KEY="prod-secret-key-with-at-least-32-bytes",
            CORS_ORIGINS="https://interview.example.com",
            DEFAULT_ADMIN_PASSWORD="admin123",
        )


def test_production_rejects_placeholder_secret_key(monkeypatch):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _reload_config(
            monkeypatch,
            ENVIRONMENT="production",
            DEBUG="false",
            DATABASE_URL="postgresql+psycopg://user:pass@db:5432/app",
            AUTO_CREATE_TABLES="false",
            SECRET_KEY="please-rotate-this-in-production-32bytes-min",
            CORS_ORIGINS="https://interview.example.com",
            DEFAULT_ADMIN_PASSWORD="replace-admin-password-123",
        )


def test_production_requires_ai_key_when_deepseek_enabled(monkeypatch):
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        _reload_config(
            monkeypatch,
            ENVIRONMENT="production",
            DEBUG="false",
            DATABASE_URL="postgresql+psycopg://user:pass@db:5432/app",
            AUTO_CREATE_TABLES="false",
            SECRET_KEY="prod-secret-key-with-at-least-32-bytes",
            CORS_ORIGINS="https://interview.example.com",
            DEFAULT_ADMIN_PASSWORD="replace-admin-password-123",
            AI_RUNTIME="deepseek",
            DEEPSEEK_API_KEY="",
        )
