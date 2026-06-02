from __future__ import annotations

import importlib
import sys


def test_settings_treats_release_debug_env_as_false(monkeypatch):
    monkeypatch.setenv("DEBUG", "release")
    sys.modules.pop("app.core.config", None)

    config = importlib.import_module("app.core.config")

    assert config.settings.DEBUG is False
