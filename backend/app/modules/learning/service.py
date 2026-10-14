from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ExerciseType
from app.modules.learning import checking
from app.modules.learning.models import Attempt, ErrorType, Exercise, ExerciseAnswer, Mistake, Topic
from app.modules.learning.schemas import (
    AttemptCreate,
    AttemptResult,
    ErrorTypeRead,
    ExerciseRead,
    TopicDetail,
    TopicSummary,
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


async def get_topic(session: AsyncSession, topic_id: int) -> TopicDetail | None:
    topic = await session.get(Topic, topic_id)
    if topic is None:
        return None

    exercises = (
        await session.scalars(
            select(Exercise).where(Exercise.topic_id == topic_id).order_by(Exercise.id)
        )
    ).all()
    answers = await _answers_by_exercise(session, [e.id for e in exercises])

    return TopicDetail(
        id=topic.id,
        title=topic.title,
        cefr_level=topic.cefr_level,
        theory=topic.theory,
        exercises=[_to_read(e, answers.get(e.id, [])) for e in exercises],
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


def _to_read(exercise: Exercise, answers: list[ExerciseAnswer]) -> ExerciseRead:
    read = ExerciseRead(id=exercise.id, type=exercise.type, prompt=exercise.prompt)
    if exercise.type == ExerciseType.MULTIPLE_CHOICE:
        read.options = [a.text for a in answers]
    elif exercise.type == ExerciseType.WORD_ORDER:
        first_correct = next(a.text for a in answers if a.is_correct)
        read.words = checking.shuffled_words(first_correct, seed=exercise.id)
    return read
