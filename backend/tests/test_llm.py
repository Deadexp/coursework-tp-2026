import json

import httpx2
import pytest

from app.core.config import Settings, settings
from app.llm import LLMError, LLMRefusalError, Message, get_llm
from app.llm.openrouter_client import OpenRouterLLM
from app.llm.stub import StubLLM
from app.modules.dialogs.schemas import SpeakerTurn


def test_provider_selection(monkeypatch) -> None:
    for name in ("LLM_MODEL", "LLM_EFFORT", "LLM_PROVIDER"):
        monkeypatch.setenv(name, "")
    defaults = Settings(_env_file=None)
    assert defaults.llm_model == "deepseek/deepseek-v4.1-flash-1017"
    assert defaults.llm_effort == "low"
    assert defaults.llm_provider == "openrouter"

    get_llm.cache_clear()
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        get_llm()
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    assert isinstance(get_llm(), OpenRouterLLM)
    get_llm.cache_clear()
    monkeypatch.setattr(settings, "llm_provider", "stub")
    assert isinstance(get_llm(), StubLLM)
    get_llm.cache_clear()


@pytest.fixture
def openrouter(monkeypatch):
    def configure(content: str, *, finish: str = "stop", status: int = 200):
        requests = []

        async def send(client, request, **kwargs):
            requests.append(request)
            message = {"role": "assistant", "content": content}
            body = {
                "id": "gen-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            }
            if status != 200:
                body = {"error": {"code": status, "message": "request failed"}}
            return httpx2.Response(status, json=body, request=request)

        monkeypatch.setattr(httpx2.AsyncClient, "send", send)
        return OpenRouterLLM(api_key="test-key", model="test-model", effort="low"), requests

    return configure


async def test_chat_uses_openrouter(openrouter) -> None:
    llm, requests = openrouter("Hello!")
    assert await llm.chat("Tutor", [Message("user", "Hi")]) == "Hello!"
    (request,) = requests
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "test-model"
    assert body["messages"] == [
        {"role": "system", "content": "Tutor"},
        {"role": "user", "content": "Hi"},
    ]
    assert body["reasoning"] == {"effort": "low"}


async def test_parse_dialog_requests_nested_schema(openrouter) -> None:
    llm, requests = openrouter('{"corrections": [], "reply": "Hi!"}')
    result = await llm.parse("Tutor", [Message("user", "Hi")], SpeakerTurn, fast=True)
    assert result == SpeakerTurn(corrections=[], reply="Hi!")
    body = json.loads(requests[0].content)
    assert body["reasoning"] == {"effort": "none"}
    assert body["provider"]["require_parameters"]
    assert body["response_format"]["type"] == "json_schema"
    schema = body["response_format"]["json_schema"]
    assert schema["strict"]
    assert schema["schema"]["$defs"]["SpeakerCorrection"]["additionalProperties"] is False


@pytest.mark.parametrize(
    ("content", "finish", "status", "error", "match"),
    [
        ("{}", "stop", 200, LLMError, "схеме"),
        ("", "content_filter", 200, LLMRefusalError, "отказалась"),
        ("", "stop", 402, LLMError, "кредитов"),
    ],
)
async def test_provider_errors(openrouter, content, finish, status, error, match) -> None:
    llm, _ = openrouter(content, finish=finish, status=status)
    with pytest.raises(error, match=match):
        await llm.parse("Tutor", [Message("user", "Hi")], SpeakerTurn)
