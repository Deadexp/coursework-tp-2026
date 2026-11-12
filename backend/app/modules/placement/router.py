from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.db import SessionDep
from app.modules.placement import service
from app.modules.placement.schemas import AttemptRead, SubmitInput
from app.modules.users.deps import CurrentUser

router = APIRouter(prefix="/placement", tags=["placement"])


@router.post("/attempts", status_code=status.HTTP_201_CREATED)
async def start(user: CurrentUser, session: SessionDep) -> AttemptRead:
    return await service.start(session, user.id)


@router.get("/history")
async def history(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[AttemptRead]:
    return await service.history(session, user.id, limit)


@router.get("/attempts/{attempt_id}")
async def read(attempt_id: int, user: CurrentUser, session: SessionDep) -> AttemptRead:
    return await service.read(session, user.id, attempt_id)


@router.post("/attempts/{attempt_id}/submit")
async def submit(
    attempt_id: int, data: SubmitInput, user: CurrentUser, session: SessionDep
) -> AttemptRead:
    return await service.submit(session, user.id, attempt_id, data)


@router.post("/attempts/{attempt_id}/apply")
async def apply(attempt_id: int, user: CurrentUser, session: SessionDep) -> AttemptRead:
    """Explicitly apply this result once; submitting answers does not change the profile."""
    return await service.apply(session, user.id, attempt_id)
