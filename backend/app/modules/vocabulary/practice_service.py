import random
import re
from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Source
from app.modules.learning.checking import normalize
from app.modules.learning.service import attempt_counts
from app.modules.users import service as users
from app.modules.users.models import User
from app.modules.vocabulary import service as vocabulary
from app.modules.vocabulary.models import UserWord, Word, WordReview
from app.modules.vocabulary.practice_models import (
    PracticeAnswer,
    PracticeChoice,
    PracticeQuestion,
    PracticeSession,
)
from app.modules.vocabulary.practice_schemas import (
    AnswerInput,
    AnswerResult,
    PracticeState,
    ProgressRead,
    QuestionView,
)
from app.modules.vocabulary.schemas import ReviewCreate


def today() -> date:
    return datetime.now(UTC).date()


async def owned_session(db: AsyncSession, user_id: int, session_id: int, *, lock=False):
    query = select(PracticeSession).where(
        PracticeSession.id == session_id,
        PracticeSession.user_id == user_id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    result = await db.scalar(query)
    if result is None:
        raise HTTPException(404, "Practice session not found")
    if result.cancelled_at is not None:
        raise HTTPException(409, "Practice changed; start this mode again")
    return result


async def questions(db: AsyncSession, session_id: int):
    return list(
        (
            await db.scalars(
                select(PracticeQuestion)
                .where(PracticeQuestion.session_id == session_id)
                .order_by(PracticeQuestion.position)
            )
        ).all()
    )


async def answers(db: AsyncSession, session_id: int):
    return list(
        (
            await db.scalars(
                select(PracticeAnswer)
                .where(PracticeAnswer.session_id == session_id)
                .order_by(PracticeAnswer.position)
            )
        ).all()
    )


async def state(db: AsyncSession, user_id: int, session_id: int) -> PracticeState:
    session = await owned_session(db, user_id, session_id)
    qs, given = await questions(db, session_id), await answers(db, session_id)
    done = {a.position for a in given}
    current = next((q for q in qs if q.position not in done), None)
    view = None
    if current is not None:
        word = await db.get(Word, current.word_id)
        choices = []
        if current.kind == "choice":
            choices = list(
                (
                    await db.scalars(
                        select(Word.translation)
                        .join(PracticeChoice, PracticeChoice.word_id == Word.id)
                        .where(
                            PracticeChoice.session_id == session_id,
                            PracticeChoice.position == current.position,
                        )
                        .order_by(PracticeChoice.choice_index)
                    )
                ).all()
            )
        if current.kind == "card":
            prompt = word.text
        elif current.kind == "choice":
            prompt = f"Выбери перевод: {word.text}"
        else:
            prompt = (
                current.gap_prompt + f"\nПодсказка: «{word.translation}»."
                if current.gap_prompt
                else f"Напиши по-английски: «{word.translation}»."
            )
        view = QuestionView(
            position=current.position,
            kind=current.kind,
            prompt=prompt,
            choices=choices,
            revealed=current.revealed_at is not None,
            translation=word.translation if current.revealed_at is not None else None,
        )
    return PracticeState(
        session_id=session.id,
        mode=session.mode,
        practice_date=session.practice_date,
        completed=session.completed_at is not None,
        total=len(qs),
        answered=len(given),
        cards_reviewed=sum(a.quality is not None for a in given),
        attempted=sum(a.is_correct is not None for a in given),
        correct=sum(a.is_correct is True for a in given),
        question=view,
    )


def gap_prompt(word: Word) -> str | None:
    if not word.example or len(word.example) > 1500 or "___" in word.example:
        return None
    pattern = r"(?<!\w)" + re.escape(word.text) + r"(?!\w)"
    if len(re.findall(pattern, word.example, flags=re.IGNORECASE)) != 1:
        return None
    return re.sub(pattern, "___", word.example, count=1, flags=re.IGNORECASE)


async def start(db: AsyncSession, user_id: int, mode: str) -> PracticeState:
    # Serialize starts per account, including starts from different clients.
    await db.scalar(select(User).where(User.id == user_id).with_for_update())
    query = select(PracticeSession).where(
        PracticeSession.user_id == user_id,
        PracticeSession.mode == mode,
        PracticeSession.cancelled_at.is_(None),
    )
    if mode == "daily":
        query = query.where(PracticeSession.practice_date == today())
    else:
        query = query.where(PracticeSession.completed_at.is_(None))
    existing = await db.scalar(query.order_by(PracticeSession.id.desc()).limit(1))
    if existing is not None:
        qs, given = await questions(db, existing.id), await answers(db, existing.id)
        completed = {a.position for a in given}
        remaining = {q.word_id for q in qs if q.position not in completed}
        owned = (
            set(
                (
                    await db.scalars(
                        select(UserWord.word_id).where(
                            UserWord.user_id == user_id,
                            UserWord.word_id.in_(remaining),
                        )
                    )
                ).all()
            )
            if remaining
            else set()
        )
        if remaining.issubset(owned):
            await db.commit()
            return await state(db, user_id, existing.id)
        # A removed word must not trap an account in an unanswerable old session.
        existing.cancelled_at = datetime.now(UTC)
        await db.flush()

    pool = list(
        (
            await db.scalars(
                select(Word)
                .join(UserWord, UserWord.word_id == Word.id)
                .where(UserWord.user_id == user_id)
                .order_by(UserWord.next_review_at, Word.id)
            )
        ).all()
    )
    if not pool:
        raise HTTPException(412, "Add words to your personal vocabulary first")
    difficult = await vocabulary.problem_words(db, user_id, days=30, limit=50)
    priority = {item.word.id: i for i, item in enumerate(difficult)}
    # Start with problem words, then due words. Each word appears at most once.
    pool.sort(key=lambda w: (w.id not in priority, priority.get(w.id, 0)))
    selected = pool[:5]
    session = PracticeSession(
        user_id=user_id,
        mode=mode,
        practice_date=today() if mode == "daily" else None,
    )
    db.add(session)
    await db.flush()
    global_words = list((await db.scalars(select(Word).order_by(func.random()).limit(100))).all())
    card_count = min(3, max(0, len(selected) - 2)) if mode == "daily" else 0
    for i, word in enumerate(selected):
        kind = "card" if mode == "daily" and i < card_count else "recall"
        options = []
        if mode == "quiz":
            distinct = {
                normalize(w.translation): w
                for w in global_words
                if normalize(w.translation) != normalize(word.translation)
            }
            distractors = random.sample(list(distinct.values()), min(3, len(distinct)))
            if distractors:
                kind = "choice"
                options = [word, *distractors]
                random.shuffle(options)
        db.add(
            PracticeQuestion(
                session_id=session.id,
                position=i,
                word_id=word.id,
                kind=kind,
                gap_prompt=gap_prompt(word) if kind == "recall" else None,
            )
        )
        await db.flush()
        for index, option in enumerate(options):
            db.add(
                PracticeChoice(
                    session_id=session.id,
                    position=i,
                    choice_index=index,
                    word_id=option.id,
                )
            )
    await db.commit()
    return await state(db, user_id, session.id)


async def active_question(db, user_id, session_id, position):
    session = await owned_session(db, user_id, session_id, lock=True)
    if session.mode == "daily" and session.practice_date != today():
        raise HTTPException(409, "A new UTC day has started; reopen daily practice")
    qs, given = await questions(db, session_id), await answers(db, session_id)
    question = next((q for q in qs if q.position == position), None)
    if question is None:
        raise HTTPException(404, "Question not found")
    previous = next((a for a in given if a.position == position), None)
    if previous is None:
        current = next((q for q in qs if q.position not in {a.position for a in given}), None)
        if session.completed_at is not None or current is None or current.position != position:
            raise HTTPException(409, "Answer the current question first")
    return session, question, previous, qs, given


async def reveal(db: AsyncSession, user_id: int, session_id: int, position: int) -> PracticeState:
    session, question, previous, _, _ = await active_question(db, user_id, session_id, position)
    if question.kind != "card" or previous is not None:
        raise HTTPException(409, "This card has already been answered")
    question.revealed_at = question.revealed_at or datetime.now(UTC)
    await db.commit()
    return await state(db, user_id, session.id)


async def answer(
    db: AsyncSession,
    user_id: int,
    session_id: int,
    data: AnswerInput,
    source: Source,
) -> AnswerResult:
    session, question, previous, qs, given = await active_question(
        db,
        user_id,
        session_id,
        data.position,
    )
    word = await db.get(Word, question.word_id)
    if previous is not None:
        if (previous.answer, previous.option_index, previous.quality) != (
            data.answer,
            data.option_index,
            data.quality,
        ):
            raise HTTPException(409, "This question already has a different answer")
        # A replay is a receipt lookup, with no second SM-2 update or new score.
        return AnswerResult(
            is_correct=previous.is_correct,
            word=word.text,
            translation=word.translation,
            next_review_at=previous.next_review_at,
            state=await state(db, user_id, session_id),
        )
    if question.kind == "card":
        if data.quality is None or question.revealed_at is None:
            raise HTTPException(422, "Reveal the card and send its self-rating")
        correct, quality = None, data.quality
    elif question.kind == "choice":
        if data.option_index is None:
            raise HTTPException(422, "Choose an offered option")
        choice = await db.get(PracticeChoice, (session_id, data.position, data.option_index))
        if choice is None:
            raise HTTPException(422, "Unknown option")
        correct = choice.word_id == question.word_id
        quality = 4 if correct else 1
    else:
        if data.answer is None:
            raise HTTPException(422, "Type the missing word")
        correct = normalize(data.answer) == normalize(word.text)
        quality = 4 if correct else 1
    result = await vocabulary.record_review(
        db,
        user_id,
        word.id,
        ReviewCreate(quality=quality, source=source),
        commit=False,
    )
    if result is None:
        raise HTTPException(409, "Word removed from your vocabulary; reopen this mode")
    db.add(
        PracticeAnswer(
            session_id=session_id,
            position=data.position,
            answer=data.answer,
            option_index=data.option_index,
            quality=data.quality,
            is_correct=correct,
            next_review_at=result.next_review_at,
        )
    )
    if len(given) + 1 == len(qs):
        session.completed_at = datetime.now(UTC)
    await db.commit()
    return AnswerResult(
        is_correct=correct,
        word=word.text,
        translation=word.translation,
        next_review_at=result.next_review_at,
        state=await state(db, user_id, session_id),
    )


async def progress(db: AsyncSession, user_id: int) -> ProgressRead:
    user = await users.get_user(db, user_id)
    words = await db.scalar(
        select(func.count()).select_from(UserWord).where(UserWord.user_id == user_id)
    )
    reviews = await db.scalar(
        select(func.count()).select_from(WordReview).where(WordReview.user_id == user_id)
    )
    attempted, correct = (
        await db.execute(
            select(
                func.count().filter(PracticeAnswer.is_correct.is_not(None)),
                func.count().filter(PracticeAnswer.is_correct.is_(True)),
            )
            .select_from(PracticeAnswer)
            .join(PracticeSession, PracticeSession.id == PracticeAnswer.session_id)
            .where(PracticeSession.user_id == user_id)
        )
    ).one()
    quizzes, dailies, last = (
        await db.execute(
            select(
                func.count().filter(PracticeSession.mode == "quiz"),
                func.count().filter(PracticeSession.mode == "daily"),
                func.max(PracticeSession.practice_date).filter(PracticeSession.mode == "daily"),
            ).where(PracticeSession.user_id == user_id, PracticeSession.completed_at.is_not(None))
        )
    ).one()
    grammar_attempted, grammar_correct = await attempt_counts(db, user_id)
    return ProgressRead(
        grammar_attempted=grammar_attempted,
        grammar_correct=grammar_correct,
        level=user.cefr_level,
        words=words,
        due=await vocabulary.count_due(db, user_id),
        reviews=reviews,
        attempted=attempted,
        correct=correct,
        quizzes_completed=quizzes,
        daily_completed=dailies,
        last_daily_date=last,
    )
