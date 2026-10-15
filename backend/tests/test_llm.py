from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.core.config import Settings, settings
from app.llm import LLMError, LLMRefusalError, Message, get_llm
from app.llm.anthropic_client import AnthropicLLM
from app.llm.stub import StubLLM


@pytest.fixture(autouse=True)
def fresh_llm():
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()


def test_empty_env_values_fall_back_to_defaults(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("LLM_EFFORT", "")
    s = Settings(_env_file=None)
    assert (s.llm_model, s.llm_effort) == ("claude-sonnet-5-5", "low")


def test_provider_selection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "stub")
    assert isinstance(get_llm(), StubLLM)

    get_llm.cache_clear()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        get_llm()

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    assert isinstance(get_llm(), AnthropicLLM)


class FakeMessages:
    """Подменяет client.beta.messages: запоминает запрос и возвращает заданный ответ."""

    def __init__(self, response):
        self.response = response
        self.request = None

    async def create(self, **kwargs):
        self.request = kwargs
        return self.response

    async def parse(self, **kwargs):
        self.request = kwargs
        return self.response


def llm_with(response) -> tuple[AnthropicLLM, FakeMessages]:
    llm = AnthropicLLM(api_key="sk-ant-test", model="claude-sonnet-5-5", effort="low")
    fake = FakeMessages(response)
    llm._client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    return llm, fake


def response(stop_reason="end_turn", content=(), parsed=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        content=list(content),
        parsed_output=parsed,
        _request_id="req_test",
    )


async def test_chat_sends_model_effort_fallback_and_joins_text() -> None:
    text = [SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="Hello!")]
    llm, fake = llm_with(response(content=text))

    reply = await llm.chat("system prompt", [Message("user", "Hi")])

    assert reply == "Hello!"
    assert fake.request["model"] == "claude-sonnet-5-5"
    assert fake.request["output_config"] == {"effort": "low"}
    assert fake.request["fallbacks"] == "default"
    assert fake.request["betas"] == ["server-side-fallback-2026-07-01"]
    assert fake.request["messages"] == [{"role": "user", "content": "Hi"}]


async def test_parse_returns_validated_model() -> None:
    class Fix(BaseModel):
        corrected: str

    llm, fake = llm_with(response(parsed=Fix(corrected="She doesn't")))

    result = await llm.parse("sys", [Message("user", "She don't")], Fix)

    assert result.corrected == "She doesn't"
    assert fake.request["output_format"] is Fix


async def test_refusal_becomes_llm_refusal_error() -> None:
    llm, _ = llm_with(response(stop_reason="refusal"))

    with pytest.raises(LLMRefusalError):
        await llm.chat("sys", [Message("user", "...")])


def test_workspace_header_is_sent_only_when_configured() -> None:
    plain = AnthropicLLM(api_key="sk-ant-test", model="m", effort="low")
    scoped = AnthropicLLM(api_key="sk-ant-test", model="m", effort="low", workspace_id="wrkspc_1")

    assert "anthropic-workspace-id" not in plain._client.default_headers
    assert scoped._client.default_headers["anthropic-workspace-id"] == "wrkspc_1"


async def test_fast_mode_disables_thinking_only_on_sonnet_5_5() -> None:
    llm, fake = llm_with(response(content=[SimpleNamespace(type="text", text="ok")]))
    await llm.chat("sys", [Message("user", "Hi")], fast=True)
    assert fake.request["thinking"] == {"type": "between_tools"}

    await llm.chat("sys", [Message("user", "Hi")])
    assert "thinking" not in fake.request

    other, other_fake = llm_with(response(content=[SimpleNamespace(type="text", text="ok")]))
    other._model = "claude-opus-5-5"
    await other.chat("sys", [Message("user", "Hi")], fast=True)
    assert "thinking" not in other_fake.request
