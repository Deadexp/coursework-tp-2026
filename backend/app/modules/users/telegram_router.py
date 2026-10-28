import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.db import SessionDep
from app.modules.users.deps import CurrentUser
from app.modules.users.models import User
from app.modules.users.telegram_auth import BotService, VocabularyUser, service_token_configured
from app.modules.users.telegram_service import (
    InvalidLinkCode,
    TelegramLinkConflict,
    issue_link_code,
    redeem_link_code,
)

router = APIRouter(prefix="/telegram", tags=["telegram"])


class LinkCodeRead(BaseModel):
    url: str
    expires_at: datetime


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{32,64}$")
    telegram_id: int = Field(gt=0, lt=2**63, strict=True)


class LinkStatus(BaseModel):
    linked: bool


class LinkedUser(BaseModel):
    display_name: str


@router.get("/status")
async def link_status(user: CurrentUser, response: Response) -> LinkStatus:
    response.headers["Cache-Control"] = "no-store"
    return LinkStatus(linked=user.telegram_id is not None)


@router.post("/link-code", status_code=201)
async def link_code(user: CurrentUser, session: SessionDep, response: Response) -> LinkCodeRead:
    username = settings.bot_username.removeprefix("@")
    if not service_token_configured() or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        raise HTTPException(503, "Telegram connection is not configured")
    try:
        code, expires = await issue_link_code(session, user.id)
    except TelegramLinkConflict:
        raise HTTPException(409, "Telegram is already linked") from None
    response.headers["Cache-Control"] = "no-store"
    return LinkCodeRead(url=f"https://t.me/{username}?start={code}", expires_at=expires)


@router.post("/link")
async def link(data: LinkRequest, session: SessionDep, service: BotService) -> LinkedUser:
    try:
        user = await redeem_link_code(session, data.code, data.telegram_id)
    except InvalidLinkCode:
        raise HTTPException(
            400, "Link expired or already used; create a new link on the website"
        ) from None
    except TelegramLinkConflict:
        raise HTTPException(
            409, "An account is already linked; existing links were not changed"
        ) from None
    return LinkedUser(display_name=user.display_name)


@router.get("/me")
async def linked_me(user: VocabularyUser, session: SessionDep) -> LinkedUser:
    # Both modes resolve the identity on the server, never from a supplied internal user_id.
    account = await session.get(User, user.id)
    return LinkedUser(display_name=account.display_name)
