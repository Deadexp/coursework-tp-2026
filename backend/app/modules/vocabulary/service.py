import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import Topic
from app.modules.vocabulary import sm2
from app.modules.vocabulary.models import TopicWord, UserWord, Word, WordReview
from app.modules.vocabulary.schemas import (
    ProblemWord,
    ReviewCard,
    ReviewCreate,
    ReviewResult,
    UserWordRead,
    VocabularyAdd,
    WordRead,
    WordSearchResult,
)

CHOICES_PER_CARD = 4


class WordNotFoundError(Exception):
    pass


class AlreadyInVocabularyError(Exception):
    pass


async def search_words(
    session: AsyncSession, user_id: int, query: str, limit: int
) -> list[WordSearchResult]:
    pattern = f"%{query.strip()}%"
    in_vocabulary = exists().where(UserWord.user_id == user_id, UserWord.word_id == Word.id)
    rows = await session.execute(
        select(Word, in_vocabulary.label("in_vocabulary"))
        .where(or_(Word.text.ilike(pattern), Word.translation.ilike(pattern)))
        .order_by(Word.text)
        .limit(limit)
    )
    return [
        WordSearchResult(**WordRead.model_validate(word).model_dump(), in_vocabulary=flag)
        for word, flag in rows
    ]


async def list_vocabulary(session: AsyncSession, user_id: int) -> list[UserWordRead]:
    rows = await session.execute(
        select(UserWord, Word)
        .join(Word, Word.id == UserWord.word_id)
        .where(UserWord.user_id == user_id)
        .order_by(UserWord.added_at.desc(), Word.text)
    )
    return [_user_word_read(uw, w) for uw, w in rows]


async def add_word(session: AsyncSession, user_id: int, data: VocabularyAdd) -> UserWordRead:
    if data.word_id is not None:
        word = await session.get(Word, data.word_id)
        if word is None:
            raise WordNotFoundError
    else:
        word = await _get_or_create_word(session, data)

    user_word = UserWord(user_id=user_id, word_id=word.id)
    session.add(user_word)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AlreadyInVocabularyError from None
    await session.refresh(user_word)
    return _user_word_read(user_word, word)


async def add_topic_words(session: AsyncSession, user_id: int, topic_id: int) -> int | None:
    """Добавляет все слова темы; уже добавленные пропускает. None — если темы нет."""
    if await session.get(Topic, topic_id) is None:
        return None
    result = await session.execute(
        insert(UserWord)
        .from_select(
            ["user_id", "word_id"],
            select(literal(user_id), TopicWord.word_id).where(TopicWord.topic_id == topic_id),
        )
        .on_conflict_do_nothing()
    )
    await session.commit()
    return result.rowcount


async def remove_word(session: AsyncSession, user_id: int, word_id: int) -> bool:
    result = await session.execute(
        delete(UserWord).where(UserWord.user_id == user_id, UserWord.word_id == word_id)
    )
    await session.commit()
    return result.rowcount > 0


async def due_cards(session: AsyncSession, user_id: int, limit: int) -> list[ReviewCard]:
    """Слова, которые пора повторить (сначала самые «просроченные»), с вариантами ответа."""
    words = (
        await session.scalars(
            select(Word)
            .join(UserWord, UserWord.word_id == Word.id)
            .where(UserWord.user_id == user_id, UserWord.next_review_at <= func.now())
            .order_by(UserWord.next_review_at)
            .limit(limit)
        )
    ).all()
    if not words:
        return []

    # Неправильные варианты берём из общего словаря одним запросом на всю пачку карточек.
    translations = select(Word.translation).distinct().subquery()
    pool = (
        await session.scalars(
            select(translations.c.translation).order_by(func.random()).limit(limit * 3 + 10)
        )
    ).all()
    cards = []
    for word in words:
        distractors = [t for t in pool if t != word.translation]
        choices = random.sample(distractors, min(CHOICES_PER_CARD - 1, len(distractors)))
        choices.append(word.translation)
        random.shuffle(choices)
        cards.append(ReviewCard(word=WordRead.model_validate(word), choices=choices))
    return cards


async def record_review(
    session: AsyncSession, user_id: int, word_id: int, data: ReviewCreate
) -> ReviewResult | None:
    user_word = await session.get(UserWord, (user_id, word_id))
    if user_word is None:
        return None

    state = sm2.review(
        sm2.Sm2State(user_word.ease_factor, user_word.interval_days, user_word.repetitions),
        data.quality,
    )
    now = datetime.now(UTC)
    user_word.ease_factor = state.ease_factor
    user_word.interval_days = state.interval_days
    user_word.repetitions = state.repetitions
    user_word.next_review_at = sm2.next_review_at(state, now)
    session.add(
        WordReview(
            user_id=user_id,
            word_id=word_id,
            quality=data.quality,
            source=data.source,
            reviewed_at=now,
        )
    )
    await session.commit()
    return ReviewResult(
        next_review_at=user_word.next_review_at,
        interval_days=state.interval_days,
        repetitions=state.repetitions,
        ease_factor=state.ease_factor,
    )


async def problem_words(
    session: AsyncSession, user_id: int, days: int, limit: int
) -> list[ProblemWord]:
    """Слова, которые пользователь чаще всего не вспоминал за последние `days` дней."""
    failed = WordReview.quality < 3
    failures = func.count().filter(failed).label("failures")
    last_failed_at = func.max(WordReview.reviewed_at).filter(failed).label("last_failed_at")
    rows = await session.execute(
        select(Word, failures, last_failed_at)
        .join(WordReview, WordReview.word_id == Word.id)
        .where(
            WordReview.user_id == user_id,
            WordReview.reviewed_at > datetime.now(UTC) - timedelta(days=days),
        )
        .group_by(Word.id)
        .having(func.count().filter(failed) > 0)
        .order_by(failures.desc(), last_failed_at.desc())
        .limit(limit)
    )
    return [
        ProblemWord(word=WordRead.model_validate(w), failures=n, last_failed_at=last)
        for w, n, last in rows
    ]


async def _get_or_create_word(session: AsyncSession, data: VocabularyAdd) -> Word:
    text, translation = data.text.strip(), data.translation.strip()
    word = await session.scalar(
        select(Word).where(
            func.lower(Word.text) == text.lower(),
            Word.part_of_speech == data.part_of_speech,
            func.lower(Word.translation) == translation.lower(),
        )
    )
    if word is None:
        word = Word(
            text=text,
            part_of_speech=data.part_of_speech,
            translation=translation,
            example=data.example,
        )
        session.add(word)
        await session.flush()
    return word


def _user_word_read(user_word: UserWord, word: Word) -> UserWordRead:
    return UserWordRead(
        word=WordRead.model_validate(word),
        added_at=user_word.added_at,
        next_review_at=user_word.next_review_at,
        interval_days=user_word.interval_days,
        repetitions=user_word.repetitions,
        ease_factor=user_word.ease_factor,
    )
