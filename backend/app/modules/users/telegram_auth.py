import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionDep
from app.core.security import decode_access_token
from app.modules.users.models import User

optional_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def service_token_configured() -> bool:
    token = settings.bot_service_token
    return len(token.strip()) >= 32 and token.strip().lower() not in {
        "change-me",
        "changeme",
        "replace-with-a-random-service-token",
    }


def require_bot_service(
    token: Annotated[str | None, Header(alias="X-Service-Token")] = None,
) -> None:
    # No database access is allowed until the service has authenticated.
    if not service_token_configured():
        raise HTTPException(503, "Telegram service is not configured")
    if token is None or not secrets.compare_digest(
        token.encode(), settings.bot_service_token.encode()
    ):
        raise HTTPException(401, "Invalid service credentials")


BotService = Annotated[None, Depends(require_bot_service)]


@dataclass(frozen=True)
class VocabularyIdentity:
    id: int
    is_bot: bool = False


async def get_vocabulary_identity(
    session: SessionDep,
    bearer: Annotated[str | None, Depends(optional_bearer)],
    telegram_id: Annotated[str | None, Header(alias="X-Telegram-ID")] = None,
    service_token: Annotated[str | None, Header(alias="X-Service-Token")] = None,
) -> VocabularyIdentity:
    if telegram_id is not None or service_token is not None:
        require_bot_service(service_token)
        if bearer is not None:
            raise HTTPException(400, "Use one authentication method")
        if (
            telegram_id is None
            or len(telegram_id) > 19
            or not telegram_id.isascii()
            or not telegram_id.isdigit()
            or not 0 < int(telegram_id) < 2**63
        ):
            raise HTTPException(401, "Telegram sender is required")
        user = await session.scalar(select(User).where(User.telegram_id == int(telegram_id)))
        if user is None:
            raise HTTPException(403, "Telegram account is not linked")
        return VocabularyIdentity(user.id, is_bot=True)
    user_id = decode_access_token(bearer) if bearer else None
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return VocabularyIdentity(user.id)


VocabularyUser = Annotated[VocabularyIdentity, Depends(get_vocabulary_identity)]
