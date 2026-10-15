from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ExerciseType
from app.modules.dialogs.models import Dialog, DialogMessage
from app.modules.learning import checking
from app.modules.learning.models import Attempt, ErrorType, Exercise, ExerciseAnswer, Mistake, Topic
from app.modules.learning.schemas import (
    AttemptCreate,
    AttemptResult,
    ErrorTypeRead,
    ExerciseRead,
    TopicDetail,
    TopicSummary,
    WeakSpot,
)


async def list_topics(session: AsyncSession, user_id: int) -> list[TopicSummary]:
    """Темы курса по порядку + прогресс пользователя (вычисляется, а не хранится — 3НФ)."""
    solved = (
        select(Attempt.exercise_id)
        .where(Attempt.user_id == user_id, Attempt.is_correct)
        .distinct()
        .subquery()
    )
    stmt = (
        select(
            Topic,
            func.count(Exercise.id).label("total"),
            func.count(solved.c.exercise_id).label("solved"),
        )
        .outerjoin(Exercise, Exercise.topic_id == Topic.id)
        .outerjoin(solved, solved.c.exercise_id == Exercise.id)
        .group_by(Topic.id)
        .order_by(Topic.position)
    )
    rows = await session.execute(stmt)
    return [
        TopicSummary(
            id=topic.id,
            title=topic.title,
            cefr_level=topic.cefr_level,
            position=topic.position,
            exercises_total=total,
            exercises_solved=solved_count,
        )
        for topic, total, solved_count in rows
    ]


async def get_topic(session: AsyncSession, topic_id: int, user_id: int) -> TopicDetail | None:
    topic = await session.get(Topic, topic_id)
    if topic is None:
        return None

    exercises = (
        await session.scalars(
            select(Exercise).where(Exercise.topic_id == topic_id).order_by(Exercise.id)
        )
    ).all()
    answers = await _answers_by_exercise(session, [e.id for e in exercises])
    solved = set(
        await session.scalars(
            select(Attempt.exercise_id)
            .join(Exercise, Exercise.id == Attempt.exercise_id)
            .where(Exercise.topic_id == topic_id, Attempt.user_id == user_id, Attempt.is_correct)
            .distinct()
        )
    )

    return TopicDetail(
        id=topic.id,
        title=topic.title,
        cefr_level=topic.cefr_level,
        theory=topic.theory,
        exercises=[_to_read(e, answers.get(e.id, []), e.id in solved) for e in exercises],
    )


async def submit_attempt(
    session: AsyncSession, user_id: int, exercise_id: int, data: AttemptCreate
) -> AttemptResult | None:
    """Проверяет ответ, сохраняет попытку, а при ошибке — запись в mistakes для адаптивности."""
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        return None

    answers = (await _answers_by_exercise(session, [exercise_id])).get(exercise_id, [])
    correct = [a.text for a in answers if a.is_correct]
    ok = checking.is_correct(data.answer, correct)

    attempt = Attempt(
        user_id=user_id,
        exercise_id=exercise_id,
        answer=data.answer,
        is_correct=ok,
        source=data.source,
    )
    session.add(attempt)

    error_type = None
    if not ok and exercise.error_type_id is not None:
        error_type = await session.get(ErrorType, exercise.error_type_id)
        await session.flush()  # нужен attempt.id
        session.add(
            Mistake(
                attempt_id=attempt.id,
                error_type_id=exercise.error_type_id,
                fragment=data.answer,
                correction=correct[0],
            )
        )
    await session.commit()

    return AttemptResult(
        is_correct=ok,
        correct_answers=correct,
        explanation=exercise.explanation,
        error_type=ErrorTypeRead(code=error_type.code, name=error_type.name)
        if error_type
        else None,
    )


async def _answers_by_exercise(
    session: AsyncSession, exercise_ids: list[int]
) -> dict[int, list[ExerciseAnswer]]:
    rows = await session.scalars(
        select(ExerciseAnswer)
        .where(ExerciseAnswer.exercise_id.in_(exercise_ids))
        .order_by(ExerciseAnswer.id)
    )
    result: dict[int, list[ExerciseAnswer]] = {}
    for answer in rows:
        result.setdefault(answer.exercise_id, []).append(answer)
    return result


def _to_read(exercise: Exercise, answers: list[ExerciseAnswer], solved: bool) -> ExerciseRead:
    read = ExerciseRead(id=exercise.id, type=exercise.type, prompt=exercise.prompt, solved=solved)
    if exercise.type == ExerciseType.MULTIPLE_CHOICE:
        read.options = [a.text for a in answers]
    elif exercise.type == ExerciseType.WORD_ORDER:
        first_correct = next(a.text for a in answers if a.is_correct)
        read.words = checking.shuffled_words(first_correct, seed=exercise.id)
    return read


async def list_error_types(session: AsyncSession) -> list[ErrorType]:
    return list(await session.scalars(select(ErrorType).order_by(ErrorType.code)))


async def weak_spots(
    session: AsyncSession, user_id: int, days: int = 14, limit: int = 5
) -> list[WeakSpot]:
    """Навыки, в которых ученик чаще всего ошибался — и в упражнениях, и в диалогах."""
    since = datetime.now(UTC) - timedelta(days=days)
    owner = func.coalesce(Attempt.user_id, Dialog.user_id)
    happened_at = func.coalesce(Attempt.created_at, DialogMessage.created_at)
    base = (
        select(Mistake)
        .outerjoin(Attempt, Attempt.id == Mistake.attempt_id)
        .outerjoin(DialogMessage, DialogMessage.id == Mistake.dialog_message_id)
        .outerjoin(Dialog, Dialog.id == DialogMessage.dialog_id)
        .where(owner == user_id, happened_at > since)
    )
    counts = (
        base.with_only_columns(Mistake.error_type_id, func.count().label("n"))
        .group_by(Mistake.error_type_id)
        .subquery()
    )
    rows = await session.execute(
        select(ErrorType, Topic.title, counts.c.n)
        .join(counts, ErrorType.id == counts.c.error_type_id)
        .outerjoin(Topic, Topic.id == ErrorType.topic_id)
        .order_by(counts.c.n.desc(), ErrorType.code)
        .limit(limit)
    )
    spots = []
    for error_type, topic_title, n in rows:
        examples = await session.execute(
            base.with_only_columns(Mistake.fragment, Mistake.correction)
            .where(Mistake.error_type_id == error_type.id)
            .order_by(happened_at.desc())
            .limit(3)
        )
        spots.append(
            WeakSpot(
                code=error_type.code,
                name=error_type.name,
                topic_id=error_type.topic_id,
                topic_title=topic_title,
                mistakes=n,
                examples=[f"{fragment} → {correction}" for fragment, correction in examples],
            )
        )
    return spots
