from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vocabulary.models import UserWord, WordReview
from app.seed import Course, seed

COURSE = Course.model_validate(
    {
        "error_types": [],
        "topics": [
            {
                "title": "Animals",
                "cefr_level": "A1",
                "position": 1,
                "theory": "...",
                "words": [
                    {"text": "cat", "part_of_speech": "noun", "translation": "кошка"},
                    {"text": "dog", "part_of_speech": "noun", "translation": "собака"},
                    {"text": "bird", "part_of_speech": "noun", "translation": "птица"},
                    {"text": "fish", "part_of_speech": "noun", "translation": "рыба"},
                    {"text": "horse", "part_of_speech": "noun", "translation": "лошадь"},
                ],
            }
        ],
    }
)


@pytest.fixture
async def words(db: AsyncSession) -> None:
    await seed(db, COURSE)  # слова получают id 1..5 в порядке объявления


async def add(client: AsyncClient, headers: dict, **body) -> int:
    response = await client.post("/vocabulary", json=body, headers=headers)
    return response.status_code


async def test_vocabulary_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/vocabulary")).status_code == 401
    assert (await client.get("/vocabulary/review")).status_code == 401


async def test_search_marks_words_already_in_vocabulary(
    client: AsyncClient, auth_headers: dict, words: None
) -> None:
    await add(client, auth_headers, word_id=1)

    found = (await client.get("/words", params={"q": "ка"}, headers=auth_headers)).json()

    assert {(w["text"], w["in_vocabulary"]) for w in found} == {("cat", True), ("dog", False)}


async def test_add_existing_word_then_duplicate_then_unknown(
    client: AsyncClient, auth_headers: dict, words: None
) -> None:
    assert await add(client, auth_headers, word_id=1) == 201
    assert await add(client, auth_headers, word_id=1) == 409
    assert await add(client, auth_headers, word_id=999) == 404


async def test_add_own_word_reuses_identical_dictionary_entry(
    client: AsyncClient, auth_headers: dict, words: None
) -> None:
    response = await client.post(
        "/vocabulary",
        json={"text": "Cat", "translation": "Кошка", "part_of_speech": "noun"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["word"]["id"] == 1  # не создали дубль «cat — кошка»

    response = await client.post(
        "/vocabulary", json={"text": "wolf", "translation": "волк"}, headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json()["word"]["id"] == 6


async def test_add_requires_word_id_or_own_word(client: AsyncClient, auth_headers: dict) -> None:
    assert await add(client, auth_headers) == 422
    assert await add(client, auth_headers, word_id=1, text="x", translation="y") == 422
    assert await add(client, auth_headers, text="only text") == 422


async def test_add_topic_words_skips_already_added(
    client: AsyncClient, auth_headers: dict, words: None
) -> None:
    await add(client, auth_headers, word_id=2)

    response = await client.post("/vocabulary/topics/1", headers=auth_headers)

    assert response.json() == {"added": 4}
    assert len((await client.get("/vocabulary", headers=auth_headers)).json()) == 5
    assert (await client.post("/vocabulary/topics/999", headers=auth_headers)).status_code == 404


async def test_remove_word(client: AsyncClient, auth_headers: dict, words: None) -> None:
    await add(client, auth_headers, word_id=1)

    assert (await client.delete("/vocabulary/1", headers=auth_headers)).status_code == 204
    assert (await client.delete("/vocabulary/1", headers=auth_headers)).status_code == 404
    assert (await client.get("/vocabulary", headers=auth_headers)).json() == []


async def test_new_words_are_due_with_four_choices(
    client: AsyncClient, auth_headers: dict, words: None
) -> None:
    await client.post("/vocabulary/topics/1", headers=auth_headers)

    cards = (await client.get("/vocabulary/review", headers=auth_headers)).json()

    assert len(cards) == 5
    for card in cards:
        assert len(card["choices"]) == 4
        assert len(set(card["choices"])) == 4
        assert card["word"]["translation"] in card["choices"]


async def test_review_schedules_word_and_removes_it_from_due(
    client: AsyncClient, auth_headers: dict, words: None, db: AsyncSession
) -> None:
    await add(client, auth_headers, word_id=1)

    response = await client.post(
        "/vocabulary/1/reviews", json={"quality": 5, "source": "bot"}, headers=auth_headers
    )

    result = response.json()
    assert (result["interval_days"], result["repetitions"]) == (1, 1)
    assert result["ease_factor"] == pytest.approx(2.6)
    assert (await client.get("/vocabulary/review", headers=auth_headers)).json() == []
    review = await db.scalar(select(WordReview))
    assert (review.quality, review.source) == (5, "bot")


async def test_word_becomes_due_again_when_its_time_comes(
    client: AsyncClient, auth_headers: dict, words: None, db: AsyncSession
) -> None:
    await add(client, auth_headers, word_id=1)
    await client.post("/vocabulary/1/reviews", json={"quality": 5}, headers=auth_headers)

    await db.execute(
        update(UserWord).values(next_review_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db.commit()

    cards = (await client.get("/vocabulary/review", headers=auth_headers)).json()
    assert [c["word"]["text"] for c in cards] == ["cat"]


async def test_review_validation(client: AsyncClient, auth_headers: dict, words: None) -> None:
    await add(client, auth_headers, word_id=1)
    url = "/vocabulary/1/reviews"

    assert (await client.post(url, json={"quality": 6}, headers=auth_headers)).status_code == 422
    not_added = await client.post(
        "/vocabulary/2/reviews", json={"quality": 5}, headers=auth_headers
    )
    assert not_added.status_code == 404


async def test_problem_words_ranked_by_failures(
    client: AsyncClient, auth_headers: dict, words: None
) -> None:
    await client.post("/vocabulary/topics/1", headers=auth_headers)
    for word_id, qualities in {1: [1, 2, 5], 2: [0], 3: [5, 4]}.items():
        for quality in qualities:
            await client.post(
                f"/vocabulary/{word_id}/reviews", json={"quality": quality}, headers=auth_headers
            )

    problems = (await client.get("/vocabulary/problem-words", headers=auth_headers)).json()

    assert [(p["word"]["text"], p["failures"]) for p in problems] == [("cat", 2), ("dog", 1)]
