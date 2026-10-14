from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.db import SessionDep
from app.modules.users.deps import CurrentUser
from app.modules.vocabulary import service
from app.modules.vocabulary.schemas import (
    AddedCount,
    ProblemWord,
    ReviewCard,
    ReviewCreate,
    ReviewResult,
    UserWordRead,
    VocabularyAdd,
    WordSearchResult,
)

router = APIRouter(tags=["vocabulary"])


@router.get("/words")
async def search_words(
    user: CurrentUser,
    session: SessionDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[WordSearchResult]:
    """Поиск по общему словарю (по слову или переводу)."""
    return await service.search_words(session, user.id, q, limit)


@router.get("/vocabulary")
async def list_vocabulary(user: CurrentUser, session: SessionDep) -> list[UserWordRead]:
    return await service.list_vocabulary(session, user.id)


@router.post("/vocabulary", status_code=status.HTTP_201_CREATED)
async def add_word(data: VocabularyAdd, user: CurrentUser, session: SessionDep) -> UserWordRead:
    try:
        return await service.add_word(session, user.id, data)
    except service.WordNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Word not found") from None
    except service.AlreadyInVocabularyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Word already in vocabulary") from None


@router.post("/vocabulary/topics/{topic_id}")
async def add_topic_words(topic_id: int, user: CurrentUser, session: SessionDep) -> AddedCount:
    """Добавляет в словарь все слова темы."""
    added = await service.add_topic_words(session, user.id, topic_id)
    if added is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topic not found")
    return AddedCount(added=added)


@router.delete("/vocabulary/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_word(word_id: int, user: CurrentUser, session: SessionDep) -> Response:
    if not await service.remove_word(session, user.id, word_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Word not in vocabulary")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/vocabulary/review")
async def due_cards(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[ReviewCard]:
    """Слова, которые пора повторить сегодня (для сайта и Telegram-бота)."""
    return await service.due_cards(session, user.id, limit)


@router.post("/vocabulary/{word_id}/reviews")
async def record_review(
    word_id: int, data: ReviewCreate, user: CurrentUser, session: SessionDep
) -> ReviewResult:
    """Результат повторения: пересчитывает интервал по SM-2."""
    result = await service.record_review(session, user.id, word_id, data)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Word not in vocabulary")
    return result


@router.get("/vocabulary/problem-words")
async def problem_words(
    user: CurrentUser,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[ProblemWord]:
    """Слова, которые чаще всего не удавалось вспомнить."""
    return await service.problem_words(session, user.id, days, limit)
