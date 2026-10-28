from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.enums import Source
from app.modules.learning import grammar_service, service
from app.modules.learning.grammar_schemas import (
    GrammarFeedback,
    GrammarState,
    QuizAnswer,
    QuizStart,
)
from app.modules.learning.schemas import TopicSummary
from app.modules.users.telegram_auth import VocabularyUser as LearningUser

router = APIRouter(prefix="/grammar", tags=["grammar"])


@router.get("/topics")
async def topics(user: LearningUser, session: SessionDep) -> list[TopicSummary]:
    return [t for t in await service.list_topics(session, user.id) if t.exercises_total]


@router.post("/quizzes")
async def start(data: QuizStart, user: LearningUser, session: SessionDep) -> GrammarState:
    return await grammar_service.start(session, user.id, data)


@router.post("/quizzes/answers")
async def answer(data: QuizAnswer, user: LearningUser, session: SessionDep) -> GrammarFeedback:
    return await grammar_service.answer(
        session,
        user.id,
        data,
        Source.BOT if user.is_bot else Source.WEB,
    )
