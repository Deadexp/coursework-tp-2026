from fastapi import APIRouter

from app.core.db import SessionDep
from app.modules.reminders import service
from app.modules.reminders.schemas import (
    Acknowledge,
    ClaimRead,
    ClaimRequest,
    DeliveryRead,
    SettingsPatch,
    SettingsRead,
)
from app.modules.users.telegram_auth import BotService, VocabularyUser

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/settings")
async def settings(user: VocabularyUser, session: SessionDep) -> SettingsRead:
    return await service.get_settings(session, user.id)


@router.patch("/settings")
async def change_settings(
    data: SettingsPatch, user: VocabularyUser, session: SessionDep
) -> SettingsRead:
    return await service.patch_settings(session, user.id, data)


@router.post("/claims")
async def claims(_: BotService, data: ClaimRequest, session: SessionDep) -> list[ClaimRead]:
    """Internal worker endpoint: atomically find and lease due reminders."""
    return await service.claim_due(session, data.limit)


@router.post("/deliveries/{delivery_id}/ack")
async def acknowledge(
    _: BotService, delivery_id: int, data: Acknowledge, session: SessionDep
) -> DeliveryRead:
    return DeliveryRead(status=await service.acknowledge(session, delivery_id, data))
