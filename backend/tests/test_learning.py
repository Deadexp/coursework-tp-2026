import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import Attempt, Mistake
from app.seed import Course, seed

COURSE = Course.model_validate(
    {
        "error_types": [{"code": "articles", "name": "Артикли", "topic": "Articles"}],
        "topics": [
            {
                "title": "Articles",
                "cefr_level": "A1",
                "position": 1,
                "theory": "# Articles",
                "exercises": [
                    {
                        "type": "multiple_choice",
                        "prompt": "I saw ___ elephant.",
                        "options": ["a", "an", "the"],
                        "correct": ["an"],
                        "explanation": "Гласный звук — an.",
                    },
                    {
                        "type": "word_order",
                        "prompt": "Собери предложение",
                        "correct": ["I have a cat"],
                    },
                    {
                        "type": "fill_gap",
                        "prompt": "He ___ like tea.",
                        "correct": ["doesn't", "does not"],
                    },
                ],
            },
            {"title": "Empty topic", "cefr_level": "A2", "position": 2, "theory": "..."},
        ],
    }
)


@pytest.fixture
async def course(db: AsyncSession) -> None:
    await seed(db, COURSE)


async def test_learning_endpoints_require_login(client: AsyncClient) -> None:
    assert (await client.get("/topics")).status_code == 401
    assert (await client.post("/exercises/1/attempts", json={"answer": "a"})).status_code == 401


async def test_list_topics_in_course_order(
    client: AsyncClient, auth_headers: dict, course: None
) -> None:
    topics = (await client.get("/topics", headers=auth_headers)).json()

    assert [t["title"] for t in topics] == ["Articles", "Empty topic"]
    assert topics[0]["exercises_total"] == 3
    assert topics[0]["exercises_solved"] == 0
    assert topics[1]["exercises_total"] == 0


async def test_topic_detail_hides_correct_answers(
    client: AsyncClient, auth_headers: dict, course: None
) -> None:
    topic = (await client.get("/topics/1", headers=auth_headers)).json()
    mc, word_order, fill_gap = topic["exercises"]

    assert mc["options"] == ["a", "an", "the"]
    assert sorted(word_order["words"]) == sorted(["I", "have", "a", "cat"])
    assert fill_gap["options"] is None and fill_gap["words"] is None
    assert "correct" not in str(topic)


async def test_unknown_topic_and_exercise_are_404(
    client: AsyncClient, auth_headers: dict, course: None
) -> None:
    assert (await client.get("/topics/999", headers=auth_headers)).status_code == 404
    response = await client.post(
        "/exercises/999/attempts", json={"answer": "a"}, headers=auth_headers
    )
    assert response.status_code == 404


async def test_correct_answer_counts_towards_progress(
    client: AsyncClient, auth_headers: dict, course: None, db: AsyncSession
) -> None:
    response = await client.post(
        "/exercises/3/attempts", json={"answer": "Does Not."}, headers=auth_headers
    )

    assert response.status_code == 201
    assert response.json()["is_correct"] is True
    assert response.json()["error_type"] is None
    topics = (await client.get("/topics", headers=auth_headers)).json()
    assert topics[0]["exercises_solved"] == 1
    assert await db.scalar(select(Mistake.id)) is None


async def test_wrong_answer_records_mistake_with_error_type(
    client: AsyncClient, auth_headers: dict, course: None, db: AsyncSession
) -> None:
    response = await client.post(
        "/exercises/1/attempts", json={"answer": "a", "source": "bot"}, headers=auth_headers
    )

    body = response.json()
    assert body["is_correct"] is False
    assert body["correct_answers"] == ["an"]
    assert body["explanation"] == "Гласный звук — an."
    assert body["error_type"] == {"code": "articles", "name": "Артикли"}

    attempt = await db.scalar(select(Attempt))
    mistake = await db.scalar(select(Mistake))
    assert attempt.source == "bot" and attempt.is_correct is False
    assert (mistake.attempt_id, mistake.fragment, mistake.correction) == (attempt.id, "a", "an")


async def test_solving_same_exercise_twice_counts_once(
    client: AsyncClient, auth_headers: dict, course: None
) -> None:
    for _ in range(2):
        await client.post("/exercises/1/attempts", json={"answer": "an"}, headers=auth_headers)

    topics = (await client.get("/topics", headers=auth_headers)).json()
    assert topics[0]["exercises_solved"] == 1
