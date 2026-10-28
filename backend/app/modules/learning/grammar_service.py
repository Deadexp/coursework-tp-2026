"""Grammar quizzes over the existing exercise bank and Attempt/Mistake logic."""

import hashlib
import hmac
import random
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

import jwt
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ExerciseType, Source
from app.modules.learning import checking, service
from app.modules.learning.grammar_schemas import (
    GrammarFeedback,
    GrammarQuestion,
    GrammarState,
    QuizAnswer,
    QuizStart,
)
from app.modules.learning.models import Attempt, Exercise, Topic
from app.modules.learning.schemas import AttemptCreate


def signing_key() -> bytes:
    # A quiz token must never be usable as a website login JWT.
    return hmac.digest(settings.jwt_secret.encode(), b"grammar-quiz-v1", "sha256")


def decode(token: str, user_id: int) -> dict:
    try:
        payload = jwt.decode(
            token,
            signing_key(),
            algorithms=["HS256"],
            audience="grammar-quiz",
            options={"require": ["exp", "sub", "nonce", "ids", "kind"]},
        )
        if payload["kind"] != "grammar-quiz":
            raise ValueError
        if payload["sub"] != str(user_id):
            raise HTTPException(404, "Quiz not found")
        ids = payload["ids"]
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 5
            or any(type(i) is not int or i <= 0 for i in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError
        UUID(payload["nonce"])
        return payload
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(409, "Quiz expired or invalid; start a new quiz") from None


def request_id(payload: dict, position: int) -> UUID:
    return uuid5(UUID(payload["nonce"]), f"{position}:{payload['ids'][position]}")


async def selected_attempts(
    db: AsyncSession,
    payload: dict,
    user_id: int,
) -> dict[int, Attempt]:
    expected = {request_id(payload, i): i for i in range(len(payload["ids"]))}
    rows = (
        await db.scalars(
            select(Attempt).where(
                Attempt.user_id == user_id,
                Attempt.quiz_request_id.in_(expected),
            )
        )
    ).all()
    return {expected[a.quiz_request_id]: a for a in rows}


async def question(
    db: AsyncSession,
    payload: dict,
    position: int,
) -> GrammarQuestion:
    exercise_id = payload["ids"][position]
    exercise = await db.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(409, "Exercise changed; start a new quiz")
    topic = await db.get(Topic, exercise.topic_id)
    read = await service.read_exercise(db, exercise_id)
    options = list(read.options or [])
    # Stable within a signed quiz, including an exact retry after a network interruption.
    random.Random(f"{payload['nonce']}:{exercise_id}").shuffle(options)
    return GrammarQuestion(
        position=position,
        topic=topic.title,
        type=read.type,
        prompt=read.prompt,
        options=options,
        words=read.words or [],
    )


async def state(
    db: AsyncSession,
    token: str,
    user_id: int,
    payload: dict | None = None,
) -> GrammarState:
    payload = payload or decode(token, user_id)
    given = await selected_attempts(db, payload, user_id)
    current = next((i for i in range(len(payload["ids"])) if i not in given), None)
    errors = [a.exercise_id for a in given.values() if not a.is_correct]
    mistake_topics = (
        list(
            (
                await db.scalars(
                    select(Topic.title)
                    .join(Exercise, Exercise.topic_id == Topic.id)
                    .where(Exercise.id.in_(errors))
                    .distinct()
                    .order_by(Topic.title)
                )
            ).all()
        )
        if errors
        else []
    )
    return GrammarState(
        session_token=token,
        topic_id=payload.get("topic_id"),
        total=len(payload["ids"]),
        answered=len(given),
        correct=sum(a.is_correct for a in given.values()),
        completed=current is None,
        mistake_topics=mistake_topics,
        question=await question(db, payload, current) if current is not None else None,
    )


async def start(db: AsyncSession, user_id: int, data: QuizStart) -> GrammarState:
    previous = decode(data.previous_token, user_id)["ids"] if data.previous_token else []
    rows = list(
        (
            await db.execute(
                select(Exercise.id, Exercise.topic_id)
                .join(Topic, Topic.id == Exercise.topic_id)
                .where(Exercise.topic_id == data.topic_id if data.topic_id is not None else True)
                .order_by(Topic.position, Exercise.id)
            )
        ).all()
    )
    if data.topic_id is not None and await db.get(Topic, data.topic_id) is None:
        raise HTTPException(404, "Topic not found")
    if not rows:
        raise HTTPException(412, "Course exercises are not loaded")
    rng = random.SystemRandom()
    ids = []
    if data.topic_id is None:
        groups: dict[int, list[int]] = {}
        for ex_id, topic_id in rows:
            groups.setdefault(topic_id, []).append(ex_id)
        topic_ids = list(groups)
        rng.shuffle(topic_ids)
        for topic_id in topic_ids[:5]:
            candidates = [i for i in groups[topic_id] if i not in previous] or groups[topic_id]
            ids.append(rng.choice(candidates))
    remaining = [ex_id for ex_id, _ in rows if ex_id not in ids]
    unseen = [i for i in remaining if i not in previous]
    seen = [i for i in remaining if i in previous]
    rng.shuffle(unseen)
    rng.shuffle(seen)
    ids = (ids + unseen + seen)[:5]
    rng.shuffle(ids)
    if ids == previous and len(ids) > 1:
        ids = ids[1:] + ids[:1]
    payload = {
        "kind": "grammar-quiz",
        "aud": "grammar-quiz",
        "sub": str(user_id),
        "nonce": str(uuid4()),
        "ids": ids,
        "topic_id": data.topic_id,
        "exp": datetime.now(UTC) + timedelta(hours=4),
    }
    token = jwt.encode(payload, signing_key(), algorithm="HS256")
    return await state(db, token, user_id, payload)


async def answer(
    db: AsyncSession,
    user_id: int,
    data: QuizAnswer,
    source: Source,
) -> GrammarFeedback:
    payload = decode(data.session_token, user_id)
    if data.position >= len(payload["ids"]):
        raise HTTPException(409, "Question is outside this quiz")
    lock = int.from_bytes(
        hashlib.sha256(f"{user_id}:{payload['nonce']}".encode()).digest()[:8], signed=True
    )
    # Shared across workers. submit_attempt commits this transaction and releases the lock.
    await db.execute(select(func.pg_advisory_xact_lock(lock)))
    given = await selected_attempts(db, payload, user_id)
    previous = given.get(data.position)
    if previous is None:
        current = next((i for i in range(len(payload["ids"])) if i not in given), None)
        if current != data.position:
            raise HTTPException(409, "Answer the current question first")
    view = await question(db, payload, data.position)
    if view.type == ExerciseType.MULTIPLE_CHOICE:
        if data.option_index is None or data.option_index >= len(view.options):
            raise HTTPException(422, "Choose an offered answer")
        text = view.options[data.option_index]
    else:
        if data.answer is None:
            raise HTTPException(422, "Type your answer")
        text = data.answer
    if previous is not None:
        if checking.normalize(previous.answer) != checking.normalize(text):
            raise HTTPException(409, "This question already has a different answer")
        result = await service.result_for_attempt(db, previous)
    else:
        result = await service.submit_attempt(
            db,
            user_id,
            payload["ids"][data.position],
            AttemptCreate(answer=text, source=source),
            quiz_request_id=request_id(payload, data.position),
        )
    return GrammarFeedback(
        is_correct=result.is_correct,
        correct_answers=result.correct_answers,
        explanation=result.explanation,
        state=await state(db, data.session_token, user_id, payload),
    )
