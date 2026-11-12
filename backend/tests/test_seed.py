import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ExerciseType
from app.modules.learning.models import Attempt, ErrorType, Exercise, ExerciseAnswer, Mistake, Topic
from app.modules.vocabulary.models import TopicWord, Word
from app.seed import Course, ExerciseIn, load_course, load_vocabulary_modules, seed


async def count(db: AsyncSession, model: type) -> int:
    return await db.scalar(select(func.count()).select_from(model))


def test_real_course_file_is_valid() -> None:
    course = load_course()
    assert len(course.topics) == 15
    assert sum(len(t.exercises) for t in course.topics) == 90
    assert all(len(t.exercises) == 6 for t in course.topics)
    assert {t.cefr_level for t in course.topics} == {"A1", "A2", "B1"}
    for topic in course.topics[5:]:
        assert {ex.type for ex in topic.exercises} == set(ExerciseType)
        assert len(topic.theory) > 1500
        assert "Типичные ошибки" in topic.theory


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


async def test_course_expansion_keeps_ids_attempts_mistakes_and_solved_progress(
    client, auth_headers, db: AsyncSession
) -> None:
    course = load_course()
    original_titles = {topic.title for topic in course.topics[:5]}
    original = Course(
        topics=[
            topic.model_copy(update={"theory": "Previous edition"}) for topic in course.topics[:5]
        ],
        error_types=[et for et in course.error_types if et.topic in original_titles],
    )
    await seed(db, original)
    identity_queries = [
        select(Topic.id, Topic.title),
        select(ErrorType.id, ErrorType.code),
        select(Exercise.id, Exercise.topic_id, Exercise.prompt, Exercise.error_type_id),
        select(Word.id, Word.text, Word.part_of_speech, Word.translation),
    ]
    original_ids = [set((await db.execute(query)).all()) for query in identity_queries]
    exercise = await db.scalar(select(Exercise).order_by(Exercise.id).limit(1))
    exercise_id, topic_id = exercise.id, exercise.topic_id
    answer = original.topics[0].exercises[0].correct[0]
    for submitted, expected in (("definitely wrong", False), (answer, True)):
        result = await client.post(
            f"/exercises/{exercise_id}/attempts",
            headers=auth_headers,
            json={"answer": submitted},
        )
        assert result.status_code == 201
        assert result.json()["is_correct"] is expected
    attempt_query = select(
        Attempt.id, Attempt.exercise_id, Attempt.answer, Attempt.is_correct, Attempt.created_at
    ).order_by(Attempt.id)
    mistake_query = select(
        Mistake.id, Mistake.attempt_id, Mistake.error_type_id, Mistake.fragment, Mistake.correction
    ).order_by(Mistake.id)
    attempts_before = (await db.execute(attempt_query)).all()
    mistakes_before = (await db.execute(mistake_query)).all()

    await seed(db, course, load_vocabulary_modules())

    for query, expected_ids in zip(identity_queries, original_ids, strict=True):
        assert expected_ids <= set((await db.execute(query)).all())
    assert (await db.execute(attempt_query)).all() == attempts_before
    assert (await db.execute(mistake_query)).all() == mistakes_before
    assert len(attempts_before) == 2 and len(mistakes_before) == 1
    topics = (await client.get("/topics", headers=auth_headers)).json()
    assert len(topics) == 15
    assert sum(topic["exercises_total"] for topic in topics) == 90
    assert sum(topic["exercises_solved"] for topic in topics) == 1
    detail = (await client.get(f"/topics/{topic_id}", headers=auth_headers)).json()
    assert detail["theory"] == course.topics[0].theory
    assert next(ex for ex in detail["exercises"] if ex["id"] == exercise_id)["solved"] is True


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
