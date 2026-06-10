from __future__ import annotations

import sys
from types import SimpleNamespace

from app.models.ai_config import AIProvider, AIRuntime, AIWireAPI
from app.services import ai_provider


def _active_deepseek_config(
    *,
    model: str = "grok-4.3-high",
    base_url: str = "https://www.sailcode.store/compatible-mode/v1",
    wire_api: AIWireAPI = AIWireAPI.CHAT_COMPLETIONS,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        runtime=AIRuntime.DEEPSEEK,
        provider=AIProvider.DEEPSEEK,
        base_url=base_url,
        api_key="sk-test",
        model=model,
        wire_api=wire_api,
        temperature=0.35,
        max_tokens=4096,
        timeout=45.0,
        max_retries=2,
    )


def test_ai_provider_uses_active_admin_model_config(monkeypatch) -> None:
    captured_request: dict = {}
    captured_client: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured_request.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"ok": true}')
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=7,
                    completion_tokens=3,
                    total_tokens=10,
                ),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_client.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(ai_provider, "get_effective_config", _active_deepseek_config, raising=False)
    monkeypatch.setattr(ai_provider.settings, "AI_RUNTIME", "mock")
    ai_provider.reset_ai_provider()

    parsed, meta = ai_provider.get_ai_provider().chat_json("system", "user")

    assert parsed == {"ok": True}
    assert meta.model == "grok-4.3-high"
    assert captured_client["base_url"] == "https://www.sailcode.store/compatible-mode/v1"
    assert captured_client["default_headers"]["User-Agent"] == "Mozilla/5.0"
    assert captured_request["model"] == "grok-4.3-high"
    assert captured_request["temperature"] == 0.35
    assert captured_request["max_tokens"] == 4096
    assert "extra_body" not in captured_request


def test_ai_provider_normalizes_chat_completions_endpoint_base_url(monkeypatch) -> None:
    captured_client: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_client.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    config = _active_deepseek_config(
        base_url="https://www.sailcode.store/compatible-mode/v1/chat/completions"
    )

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(ai_provider, "get_effective_config", lambda: config, raising=False)
    ai_provider.reset_ai_provider()

    parsed, _ = ai_provider.get_ai_provider().chat_json("system", "user")

    assert parsed == {"ok": True}
    assert captured_client["base_url"] == "https://www.sailcode.store/compatible-mode/v1"


def test_ai_provider_uses_real_responses_wire_api_endpoint(monkeypatch) -> None:
    captured_post: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            raise AssertionError("responses wire api must not call chat.completions")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": '{"ok": true}'},
                        ],
                    },
                ],
                "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
            }

    class FakeHttpClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def post(self, url, **kwargs):
            captured_post["url"] = url
            captured_post.update(kwargs)
            return FakeResponse()

    config = _active_deepseek_config(
        base_url="https://www.sailcode.store/compatible-mode/v1/chat/completions",
        wire_api=AIWireAPI.RESPONSES,
    )

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(Timeout=lambda **kwargs: kwargs, Client=FakeHttpClient),
    )
    monkeypatch.setattr(ai_provider, "get_effective_config", lambda: config, raising=False)
    ai_provider.reset_ai_provider()

    parsed, meta = ai_provider.get_ai_provider().chat_json("system", "user")

    assert parsed == {"ok": True}
    assert captured_post["url"] == "https://www.sailcode.store/compatible-mode/v1/responses"
    assert captured_post["json"]["model"] == "grok-4.3-high"
    assert captured_post["json"]["input"][0]["role"] == "system"
    assert captured_post["json"]["input"][1]["role"] == "user"
    assert captured_post["json"]["max_output_tokens"] == 4096
    assert meta.usage.total_tokens == 8


def test_ai_provider_rebuilds_when_active_admin_config_changes(monkeypatch) -> None:
    created_clients: list[str] = []

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
                usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created_clients.append(kwargs["base_url"])
            self.chat = SimpleNamespace(completions=FakeCompletions())

    current_config = _active_deepseek_config(model="first-model")

    def fake_effective_config():
        return current_config

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(ai_provider, "get_effective_config", fake_effective_config, raising=False)
    ai_provider.reset_ai_provider()

    first = ai_provider.get_ai_provider()
    current_config = _active_deepseek_config(model="second-model")
    second = ai_provider.get_ai_provider()

    assert first is not second
    assert getattr(first, "model") == "first-model"
    assert getattr(second, "model") == "second-model"
    assert created_clients == [
        "https://www.sailcode.store/compatible-mode/v1",
        "https://www.sailcode.store/compatible-mode/v1",
    ]


def test_ai_provider_zero_retries_still_sends_one_request(monkeypatch) -> None:
    calls = 0

    class FakeCompletions:
        def create(self, **kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
                usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    config = _active_deepseek_config()
    config.max_retries = 0

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(ai_provider, "get_effective_config", lambda: config, raising=False)
    ai_provider.reset_ai_provider()

    ai_provider.get_ai_provider().chat_json("system", "user")

    assert calls == 1


def test_ai_provider_accepts_raw_string_gateway_response(monkeypatch) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            return '{"name":"李雷","years":3,"skills":["Python"],"projects":[],"highlights":[],"summary":"后端开发","risk_flags":[]}'

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(ai_provider, "get_effective_config", _active_deepseek_config, raising=False)
    ai_provider.reset_ai_provider()

    parsed, meta = ai_provider.get_ai_provider().chat_json("system", "user")

    assert parsed["name"] == "李雷"
    assert parsed["skills"] == ["Python"]
    assert meta.content.startswith('{"name"')
    assert meta.usage.total_tokens == 0
