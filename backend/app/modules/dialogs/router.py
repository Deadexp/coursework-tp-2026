from fastapi import APIRouter, HTTPException, status

from app.core.db import SessionDep
from app.llm import LLMDep
from app.modules.dialogs import service
from app.modules.dialogs.scenarios import SCENARIOS
from app.modules.dialogs.schemas import (
    DialogCreate,
    DialogRead,
    DialogSummaryRead,
    ExchangeResult,
    MessageCreate,
    ScenarioRead,
)
from app.modules.users.deps import CurrentUser

router = APIRouter(prefix="/dialogs", tags=["dialogs"])

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Dialog not found")


@router.get("/scenarios")
async def list_scenarios(_: CurrentUser) -> list[ScenarioRead]:
    return [
        ScenarioRead(code=s.code, title=s.title, description=s.description)
        for s in SCENARIOS.values()
    ]


@router.get("")
async def list_dialogs(user: CurrentUser, session: SessionDep) -> list[DialogSummaryRead]:
    return await service.list_dialogs(session, user.id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_dialog(
    data: DialogCreate, user: CurrentUser, session: SessionDep, llm: LLMDep
) -> DialogRead:
    """Начинает разговор: собеседник здоровается и открывает сценарий."""
    try:
        return await service.create_dialog(session, llm, user, data.scenario)
    except service.ScenarioNotFoundError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown scenario") from None


@router.get("/{dialog_id}")
async def get_dialog(dialog_id: int, user: CurrentUser, session: SessionDep) -> DialogRead:
    dialog = await service.get_dialog(session, user.id, dialog_id)
    if dialog is None:
        raise NOT_FOUND
    return dialog


@router.post("/{dialog_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    dialog_id: int, data: MessageCreate, user: CurrentUser, session: SessionDep, llm: LLMDep
) -> ExchangeResult:
    """Реплика ученика: ответ собеседника и исправления ошибок (они попадают в mistakes)."""
    try:
        result = await service.send_message(session, llm, user, dialog_id, data.content)
    except service.DialogFinishedError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dialog is finished") from None
    except service.DialogTooLongError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Dialog is too long, finish it and start a new one"
        ) from None
    if result is None:
        raise NOT_FOUND
    return result


@router.post("/{dialog_id}/finish")
async def finish_dialog(
    dialog_id: int, user: CurrentUser, session: SessionDep, llm: LLMDep
) -> DialogRead:
    """Завершает разговор и возвращает отзыв наставника."""
    dialog = await service.finish_dialog(session, llm, user, dialog_id)
    if dialog is None:
        raise NOT_FOUND
    return dialog
