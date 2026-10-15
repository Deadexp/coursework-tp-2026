from fastapi import APIRouter, HTTPException, status

from app.core.db import SessionDep
from app.llm import LLMDep
from app.modules.recommendations import service
from app.modules.recommendations.schemas import PlanItemRead, PlanRead
from app.modules.users.deps import CurrentUser

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/plan", status_code=status.HTTP_201_CREATED)
async def create_plan(user: CurrentUser, session: SessionDep, llm: LLMDep) -> PlanRead:
    """Адаптивный наставник составляет план занятия по ошибкам, прогрессу и словарю ученика."""
    return await service.create_plan(session, llm, user)


@router.get("/plan")
async def latest_plan(user: CurrentUser, session: SessionDep) -> PlanRead | None:
    """Последний составленный план или null, если планов ещё не было."""
    return await service.latest_plan(session, user.id)


@router.post("/plan/items/{item_id}/done")
async def mark_done(item_id: int, user: CurrentUser, session: SessionDep) -> PlanItemRead:
    item = await service.mark_done(session, user.id, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan item not found")
    return item
