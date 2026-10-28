from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import settings
from app.modules.users.telegram_auth import get_vocabulary_identity, require_bot_service
from app.modules.users.telegram_router import LinkRequest
from app.modules.vocabulary.schemas import VocabularyAdd


@pytest.mark.parametrize("configured", ["", "change-me", "replace-with-a-random-service-token"])
def test_service_auth_rejects_unconfigured_key(monkeypatch, configured):
    monkeypatch.setattr(settings, "bot_service_token", configured)
    with pytest.raises(HTTPException) as error:
        require_bot_service(configured)
    assert error.value.status_code == 503


def test_service_auth_checks_secret_without_echoing_it(monkeypatch):
    secret = "unit-test-" + "a" * 40
    monkeypatch.setattr(settings, "bot_service_token", secret)
    require_bot_service(secret)
    for supplied in (None, "", "wrong", "несекрет"):
        with pytest.raises(HTTPException) as error:
            require_bot_service(supplied)
        assert error.value.status_code == 401
        assert secret not in str(error.value)


@pytest.mark.parametrize("telegram_id", [None, "", "-1", "0", "１", "x", "9" * 5000])
async def test_invalid_sender_never_reaches_database(monkeypatch, telegram_id):
    token = "unit-test-" + "a" * 40
    monkeypatch.setattr(settings, "bot_service_token", token)
    session = AsyncMock()
    with pytest.raises(HTTPException):
        await get_vocabulary_identity(session, None, telegram_id, token)
    session.scalar.assert_not_called()
    session.get.assert_not_called()


def test_link_request_does_not_accept_username_or_user_id():
    for extra in ({"username": "someone"}, {"user_id": 1}):
        with pytest.raises(ValidationError):
            LinkRequest.model_validate({"code": "a" * 43, "telegram_id": 9000000001, **extra})
    with pytest.raises(ValidationError):
        LinkRequest.model_validate({"code": "a" * 43, "telegram_id": True})


@pytest.mark.parametrize(
    "data", [{"text": " ", "translation": "x"}, {"text": "x", "translation": " "}]
)
def test_word_whitespace_is_rejected(data):
    with pytest.raises(ValidationError):
        VocabularyAdd.model_validate(data)
