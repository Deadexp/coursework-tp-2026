from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.enums import Source
from app.modules.users import service as users
from app.modules.users.telegram_auth import VocabularyUser
from app.modules.vocabulary import practice_service as service
from app.modules.vocabulary.practice_schemas import (
    AnswerInput,
    AnswerResult,
    LevelRead,
    PracticeState,
    ProgressRead,
    QuestionPosition,
    StartPractice,
)

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post("/sessions")
async def start_session(
    data: StartPractice, user: VocabularyUser, session: SessionDep
) -> PracticeState:
    return await service.start(session, user.id, data.mode)


@router.get("/sessions/{session_id}")
async def read_session(session_id: int, user: VocabularyUser, session: SessionDep) -> PracticeState:
    return await service.state(session, user.id, session_id)


@router.post("/sessions/{session_id}/reveal")
async def reveal(
    session_id: int,
    data: QuestionPosition,
    user: VocabularyUser,
    session: SessionDep,
) -> PracticeState:
    return await service.reveal(session, user.id, session_id, data.position)


@router.post("/sessions/{session_id}/answers")
async def answer(
    session_id: int,
    data: AnswerInput,
    user: VocabularyUser,
    session: SessionDep,
) -> AnswerResult:
    return await service.answer(
        session,
        user.id,
        session_id,
        data,
        Source.BOT if user.is_bot else Source.WEB,
    )


@router.get("/progress")
async def progress(user: VocabularyUser, session: SessionDep) -> ProgressRead:
    return await service.progress(session, user.id)


@router.get("/level")
async def level(user: VocabularyUser, session: SessionDep) -> LevelRead:
    account = await users.get_user(session, user.id)
    return LevelRead(level=account.cefr_level)


@router.patch("/level")
async def change_level(data: LevelRead, user: VocabularyUser, session: SessionDep) -> LevelRead:
    return LevelRead(level=await users.set_level(session, user.id, data.level))
