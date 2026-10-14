import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import ErrorType, Exercise, ExerciseAnswer, Topic
from app.modules.vocabulary.models import TopicWord, Word
from app.seed import ExerciseIn, load_course, seed


async def count(db: AsyncSession, model: type) -> int:
    return await db.scalar(select(func.count()).select_from(model))


def test_real_course_file_is_valid() -> None:
    course = load_course()
    assert len(course.topics) >= 5
    assert all(len(t.exercises) >= 5 for t in course.topics)


async def test_seed_is_idempotent(db: AsyncSession) -> None:
    course = load_course()
    await seed(db, course)
    counts = [
        await count(db, m) for m in (Topic, ErrorType, Exercise, ExerciseAnswer, Word, TopicWord)
    ]

    await seed(db, course)

    assert [
        await count(db, m) for m in (Topic, ErrorType, Exercise, ExerciseAnswer, Word, TopicWord)
    ] == counts
    assert counts[0] == len(course.topics)


async def test_every_seeded_exercise_has_error_type_and_correct_answer(db: AsyncSession) -> None:
    await seed(db, load_course())

    without_error_type = await db.scalar(
        select(func.count()).select_from(Exercise).where(Exercise.error_type_id.is_(None))
    )
    without_correct = await db.scalar(
        select(func.count())
        .select_from(Exercise)
        .where(
            ~select(ExerciseAnswer.id)
            .where(ExerciseAnswer.exercise_id == Exercise.id, ExerciseAnswer.is_correct)
            .exists()
        )
    )
    assert without_error_type == 0
    assert without_correct == 0


def test_multiple_choice_requires_correct_answer_among_options() -> None:
    with pytest.raises(ValidationError):
        ExerciseIn(type="multiple_choice", prompt="?", options=["a", "b"], correct=["c"])
