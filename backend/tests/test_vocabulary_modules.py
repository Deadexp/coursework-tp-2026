from pathlib import Path
from xml.etree import ElementTree

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vocabulary.models import UserWord, Word, WordReview
from app.modules.vocabulary.modules_models import ModuleWord, VocabularyModule
from app.seed import Course, WordIn, load_vocabulary_modules, seed

EMPTY_COURSE = Course(error_types=[], topics=[])


@pytest.fixture
async def modules(db: AsyncSession) -> None:
    await seed(db, EMPTY_COURSE, load_vocabulary_modules())


def test_catalog_has_six_complete_modules_with_local_distinct_illustrations() -> None:
    catalog = load_vocabulary_modules()
    assert len(catalog.modules) == 6
    words = [word for module in catalog.modules for word in module.words]
    assert all(len(module.words) == 6 for module in catalog.modules)
    assert len({word.image_url for word in words}) == 36
    public = Path(__file__).resolve().parents[2] / "frontend" / "public"
    for word in words:
        assert word.transcription and word.example and word.translation
        assert word.image_url
        path = public / word.image_url.removeprefix("/")
        root = ElementTree.fromstring(path.read_text())
        assert root.attrib["viewBox"] == "0 0 160 160"
        assert not root.findall(".//{http://www.w3.org/2000/svg}text")
        assert not root.findall(".//{http://www.w3.org/2000/svg}script")
        assert not root.findall(".//{http://www.w3.org/2000/svg}image")


@pytest.mark.parametrize(
    "image_url",
    [
        "https://example.com/cat.svg",
        "//example.com/cat.svg",
        "/images/vocabulary/../cat.svg",
        "/images/vocabulary/cat.svg?url=https://example.com",
        "data:image/svg+xml,cat",
    ],
)
def test_seed_rejects_remote_or_traversing_image_paths(image_url: str) -> None:
    with pytest.raises(ValidationError):
        WordIn(text="cat", part_of_speech="noun", translation="кошка", image_url=image_url)


async def test_module_endpoints_require_authorization(client: AsyncClient) -> None:
    assert (await client.get("/vocabulary/modules")).status_code == 401
    assert (await client.get("/vocabulary/modules/1")).status_code == 401
    assert (await client.post("/vocabulary/modules/1/add")).status_code == 401


async def test_catalog_detail_and_missing_module(
    client: AsyncClient, auth_headers: dict, modules: None
) -> None:
    response = await client.get("/vocabulary/modules", headers=auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert [item["slug"] for item in catalog] == [
        "food",
        "animals",
        "home",
        "travel",
        "study",
        "weather",
    ]
    assert all(item["word_count"] == 6 and item["in_vocabulary_count"] == 0 for item in catalog)
    detail = (
        await client.get(f"/vocabulary/modules/{catalog[0]['id']}", headers=auth_headers)
    ).json()
    assert [word["text"] for word in detail["words"]] == [
        "apple",
        "banana",
        "bread",
        "cheese",
        "carrot",
        "egg",
    ]
    assert all(word["image_url"].startswith("/images/vocabulary/") for word in detail["words"])
    assert not any(word["in_vocabulary"] for word in detail["words"])
    assert (await client.get("/vocabulary/modules/99999", headers=auth_headers)).status_code == 404
    assert (
        await client.post("/vocabulary/modules/99999/add", headers=auth_headers)
    ).status_code == 404


async def test_add_module_is_idempotent_and_preserves_review_schedule_and_history(
    client: AsyncClient, auth_headers: dict, modules: None, db: AsyncSession
) -> None:
    detail = (await client.get("/vocabulary/modules/1", headers=auth_headers)).json()
    first_word_id = detail["words"][0]["id"]
    await client.post("/vocabulary", json={"word_id": first_word_id}, headers=auth_headers)
    for _ in range(2):
        response = await client.post(
            f"/vocabulary/{first_word_id}/reviews", json={"quality": 5}, headers=auth_headers
        )
        assert response.status_code == 200
    user_word = await db.scalar(select(UserWord).where(UserWord.word_id == first_word_id))
    before = (
        user_word.added_at,
        user_word.next_review_at,
        user_word.interval_days,
        user_word.repetitions,
        user_word.ease_factor,
    )
    assert before[2:4] == (6, 2)

    first = await client.post("/vocabulary/modules/1/add", headers=auth_headers)
    second = await client.post("/vocabulary/modules/1/add", headers=auth_headers)
    assert first.json() == {"added": 5}
    assert second.json() == {"added": 0}
    await db.refresh(user_word)
    assert (
        user_word.added_at,
        user_word.next_review_at,
        user_word.interval_days,
        user_word.repetitions,
        user_word.ease_factor,
    ) == before
    assert await db.scalar(select(func.count()).select_from(WordReview)) == 2

    catalog = (await client.get("/vocabulary/modules", headers=auth_headers)).json()
    assert catalog[0]["in_vocabulary_count"] == 6
    cards = (await client.get("/vocabulary/review", headers=auth_headers)).json()
    assert len(cards) == 5  # reviewed word retains its future due date
    assert all(card["word"]["image_url"] for card in cards)
    for item in (await client.get("/vocabulary", headers=auth_headers)).json():
        if item["word"]["id"] != first_word_id:
            assert (item["interval_days"], item["repetitions"], item["ease_factor"]) == (0, 0, 2.5)


async def test_module_progress_belongs_to_current_user(
    client: AsyncClient, auth_headers: dict, modules: None
) -> None:
    await client.post("/vocabulary/modules/1/add", headers=auth_headers)
    await client.post(
        "/auth/register",
        json={"email": "second@example.com", "password": "second-pass", "display_name": "Second"},
    )
    login = await client.post(
        "/auth/login", data={"username": "second@example.com", "password": "second-pass"}
    )
    second_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    catalog = (await client.get("/vocabulary/modules", headers=second_headers)).json()
    assert all(item["in_vocabulary_count"] == 0 for item in catalog)
    detail = (await client.get("/vocabulary/modules/1", headers=second_headers)).json()
    assert not any(word["in_vocabulary"] for word in detail["words"])


async def test_reseed_updates_catalog_without_deleting_personal_words_or_reviews(
    client: AsyncClient, auth_headers: dict, modules: None, db: AsyncSession
) -> None:
    await client.post("/vocabulary/modules/1/add", headers=auth_headers)
    await client.post("/vocabulary/1/reviews", json={"quality": 4}, headers=auth_headers)
    catalog = load_vocabulary_modules()
    catalog.modules[0].title = "Продукты для завтрака"
    catalog.modules[0].words.reverse()
    await seed(db, EMPTY_COURSE, catalog)
    await seed(db, EMPTY_COURSE, catalog)
    assert await db.scalar(select(func.count()).select_from(VocabularyModule)) == 6
    assert await db.scalar(select(func.count()).select_from(ModuleWord)) == 36
    assert await db.scalar(select(func.count()).select_from(Word)) == 36
    assert await db.scalar(select(func.count()).select_from(UserWord)) == 6
    assert await db.scalar(select(func.count()).select_from(WordReview)) == 1
    detail = (await client.get("/vocabulary/modules/1", headers=auth_headers)).json()
    assert detail["title"] == "Продукты для завтрака"
    assert [word["text"] for word in detail["words"]] == [
        "egg",
        "carrot",
        "cheese",
        "bread",
        "banana",
        "apple",
    ]
    assert detail["in_vocabulary_count"] == 6


async def test_database_rejects_remote_image_url(db: AsyncSession) -> None:
    db.add(
        Word(text="test", part_of_speech="noun", translation="тест", image_url="https://x/y.svg")
    )
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
