import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.users.models import TelegramLinkCode, User
from app.modules.vocabulary.models import Word, WordReview

TEST_SERVICE = "integration-test-service-" + "x" * 40
TELEGRAM_ID = 9000000001


@pytest.fixture(autouse=True)
def telegram_settings(monkeypatch):
    monkeypatch.setattr(settings, "bot_service_token", TEST_SERVICE)
    monkeypatch.setattr(settings, "bot_username", "course_test_bot")


def bot_headers(sender=TELEGRAM_ID):
    return {"X-Service-Token": TEST_SERVICE, "X-Telegram-ID": str(sender)}


async def new_code(client, headers):
    result = await client.post("/telegram/link-code", headers=headers)
    assert result.status_code == 201
    assert result.headers["cache-control"] == "no-store"
    return parse_qs(urlparse(result.json()["url"]).query)["start"][0]


async def redeem(client, code, sender=TELEGRAM_ID):
    return await client.post(
        "/telegram/link", headers=bot_headers(sender), json={"code": code, "telegram_id": sender}
    )


async def connect(client, headers, sender=TELEGRAM_ID):
    assert (await redeem(client, await new_code(client, headers), sender)).status_code == 200


async def other_user(client):
    await client.post(
        "/auth/register",
        json={
            "email": "second@example.com",
            "password": "second-password",
            "display_name": "Second",
        },
    )
    login = await client.post(
        "/auth/login",
        data={
            "username": "second@example.com",
            "password": "second-password",
        },
    )
    return {"Authorization": "Bearer " + login.json()["access_token"]}


async def test_link_status_expiry_and_single_use(
    client: AsyncClient, auth_headers, db: AsyncSession
):
    assert (await client.get("/telegram/status", headers=auth_headers)).json() == {"linked": False}
    response = await client.post("/telegram/link-code", headers=auth_headers)
    body = response.json()
    expires = datetime.fromisoformat(body["expires_at"])
    assert 590 < (expires - datetime.now(UTC)).total_seconds() <= 600
    code = parse_qs(urlparse(body["url"]).query)["start"][0]
    stored = await db.scalar(select(TelegramLinkCode))
    assert stored.code != code
    assert (await redeem(client, code)).status_code == 200
    assert (await redeem(client, code)).status_code == 400
    assert (await client.get("/telegram/status", headers=auth_headers)).json() == {"linked": True}
    assert (await client.post("/telegram/link-code", headers=auth_headers)).status_code == 409


async def test_expired_and_replaced_code(client: AsyncClient, auth_headers, db: AsyncSession):
    old = await new_code(client, auth_headers)
    code = await new_code(client, auth_headers)
    assert (await redeem(client, old)).status_code == 400
    await db.execute(
        update(TelegramLinkCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    assert (await redeem(client, code)).status_code == 400
    assert (await client.get("/telegram/status", headers=auth_headers)).json() == {"linked": False}


async def test_concurrent_redemption_is_single_use(client: AsyncClient, auth_headers):
    code = await new_code(client, auth_headers)
    results = await asyncio.gather(redeem(client, code), redeem(client, code))
    assert sorted(r.status_code for r in results) == [200, 400]


async def test_concurrent_conflicting_accounts_do_not_replace_links(
    client: AsyncClient,
    auth_headers,
    db: AsyncSession,
):
    second = await other_user(client)
    codes = [await new_code(client, h) for h in (auth_headers, second)]
    results = await asyncio.gather(*(redeem(client, code) for code in codes))
    assert sorted(r.status_code for r in results) == [200, 409]
    users = (await db.scalars(select(User).where(User.telegram_id == TELEGRAM_ID))).all()
    assert len(users) == 1
    winner = users[0].id
    loser_code = codes[next(i for i, r in enumerate(results) if r.status_code == 409)]
    assert (await redeem(client, loser_code)).status_code == 409
    assert (await db.scalar(select(User.id).where(User.telegram_id == TELEGRAM_ID))) == winner


@pytest.mark.parametrize(
    "headers", [{}, {"X-Service-Token": "wrong"}, {"X-Telegram-ID": "9000000001"}]
)
async def test_link_requires_service_auth(client: AsyncClient, auth_headers, headers):
    code = await new_code(client, auth_headers)
    response = await client.post(
        "/telegram/link", headers=headers, json={"code": code, "telegram_id": TELEGRAM_ID}
    )
    assert response.status_code == 401
    assert (await client.get("/telegram/status", headers=auth_headers)).json() == {"linked": False}


@pytest.mark.parametrize(
    "token", ["", "change-me", "changeme", "replace-with-a-random-service-token"]
)
async def test_empty_or_default_server_key_denies_access(client: AsyncClient, monkeypatch, token):
    monkeypatch.setattr(settings, "bot_service_token", token)
    assert (
        await client.get(
            "/vocabulary",
            headers={
                "X-Service-Token": token,
                "X-Telegram-ID": str(TELEGRAM_ID),
            },
        )
    ).status_code == 503


async def test_internal_user_id_and_username_are_not_authentication(
    client: AsyncClient, auth_headers
):
    for path in ("/vocabulary?user_id=1&username=learner", "/vocabulary/page"):
        assert (
            await client.get(path, headers={"X-Telegram-ID": str(TELEGRAM_ID)})
        ).status_code == 401
        assert (await client.get(path, headers=bot_headers())).status_code == 403
    code = await new_code(client, auth_headers)
    assert (
        await client.post(
            "/telegram/link",
            headers=bot_headers(),
            json={
                "code": code,
                "telegram_id": TELEGRAM_ID,
                "user_id": 1,
            },
        )
    ).status_code == 422
    assert (await client.get("/users/me", headers=bot_headers())).status_code == 401
    assert (await client.post("/telegram/link-code", headers=bot_headers())).status_code == 401


async def test_web_to_bot_and_bot_to_web_share_dictionary(client: AsyncClient, auth_headers):
    await connect(client, auth_headers)
    added = await client.post(
        "/vocabulary", headers=auth_headers, json={"text": "bridge", "translation": "мост"}
    )
    assert added.status_code == 201
    page = (await client.get("/vocabulary/page", headers=bot_headers())).json()
    assert [(x["word"]["text"], x["word"]["translation"]) for x in page["items"]] == [
        ("bridge", "мост")
    ]
    assert (
        await client.post(
            "/vocabulary",
            headers=bot_headers(),
            json={
                "text": "shared",
                "translation": "общий",
            },
        )
    ).status_code == 201
    words = (await client.get("/vocabulary", headers=auth_headers)).json()
    assert {w["word"]["text"] for w in words} == {"bridge", "shared"}
    assert (
        await client.post(
            "/vocabulary",
            headers=bot_headers(),
            json={
                "text": " Bridge ",
                "translation": " МОСТ ",
            },
        )
    ).status_code == 409


async def test_real_bot_http_client_uses_shared_backend(client: AsyncClient, auth_headers):
    # Import exactly the client used by the Telegram router; no Telegram credentials or network.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bot"))
    from bot.api_client import BackendClient

    await connect(client, auth_headers)
    bot = BackendClient("http://test", TEST_SERVICE, http=client)
    assert (await bot.dictionary(TELEGRAM_ID)).total == 0
    await bot.add_word(TELEGRAM_ID, "bridge", "мост")
    web = (await client.get("/vocabulary", headers=auth_headers)).json()
    assert web[0]["word"]["text"] == "bridge"
    await client.post(
        "/vocabulary", headers=auth_headers, json={"text": "shared", "translation": "общий"}
    )
    assert (await bot.dictionary(TELEGRAM_ID)).total == 2
    cards = await bot.cards(TELEGRAM_ID)
    result = await bot.review(TELEGRAM_ID, cards[0].id, 1)
    web = (await client.get("/vocabulary", headers=auth_headers)).json()
    reviewed = next(w for w in web if w["word"]["id"] == cards[0].id)
    assert datetime.fromisoformat(reviewed["next_review_at"]) == result.next_review_at


async def test_privacy_deletion_and_pagination(client: AsyncClient, auth_headers, db: AsyncSession):
    second = await other_user(client)
    await connect(client, auth_headers)
    await connect(client, second, TELEGRAM_ID + 1)
    for i in range(10):
        response = await client.post(
            "/vocabulary",
            headers=auth_headers,
            json={"text": f"word{i}", "translation": f"перевод{i}"},
        )
        assert response.status_code == 201
    page1 = (await client.get("/vocabulary/page", headers=bot_headers())).json()
    page2 = (await client.get("/vocabulary/page?page=1", headers=bot_headers())).json()
    ids1, ids2 = [{x["word"]["id"] for x in p["items"]} for p in (page1, page2)]
    assert len(ids1) == 8 and len(ids2) == 2 and not ids1.intersection(ids2)
    assert (await client.get("/vocabulary/page", headers=bot_headers(TELEGRAM_ID + 1))).json()[
        "total"
    ] == 0
    word_id = next(iter(ids1))
    assert (
        await client.delete(f"/vocabulary/{word_id}", headers=bot_headers(TELEGRAM_ID + 1))
    ).status_code == 404
    assert (
        await client.post("/vocabulary", headers=second, json={"word_id": word_id})
    ).status_code == 201
    assert (await client.delete(f"/vocabulary/{word_id}", headers=bot_headers())).status_code == 204
    assert await db.get(Word, word_id) is not None
    assert len((await client.get("/vocabulary", headers=second)).json()) == 1
    assert (await client.get("/vocabulary/page?page=-1", headers=bot_headers())).status_code == 422


async def test_bot_review_uses_common_sm2_and_forces_source_bot(
    client: AsyncClient,
    auth_headers,
    db: AsyncSession,
):
    await connect(client, auth_headers)
    word = (
        await client.post(
            "/vocabulary", headers=auth_headers, json={"text": "bridge", "translation": "мост"}
        )
    ).json()["word"]
    url = f"/vocabulary/{word['id']}/reviews"
    result = (
        await client.post(url, headers=bot_headers(), json={"quality": 1, "source": "web"})
    ).json()
    assert result["interval_days"] == 1
    web = (await client.get("/vocabulary", headers=auth_headers)).json()[0]
    assert web["next_review_at"] == result["next_review_at"]
    review = await db.scalar(select(WordReview))
    assert review.source == "bot"
    problems = (await client.get("/vocabulary/problem-words", headers=bot_headers())).json()
    assert problems[0]["word"]["id"] == word["id"]


async def test_concurrent_web_and_bot_reviews_are_serialized(client: AsyncClient, auth_headers):
    await connect(client, auth_headers)
    word = (
        await client.post(
            "/vocabulary", headers=auth_headers, json={"text": "bridge", "translation": "мост"}
        )
    ).json()["word"]
    url = f"/vocabulary/{word['id']}/reviews"
    results = await asyncio.gather(
        *(client.post(url, headers=h, json={"quality": 5}) for h in (auth_headers, bot_headers()))
    )
    assert all(r.status_code == 200 for r in results)
    state = (await client.get("/vocabulary", headers=auth_headers)).json()[0]
    assert state["repetitions"] == 2
    assert state["interval_days"] == 6


@pytest.mark.parametrize(
    "body",
    [
        {"text": "  ", "translation": "мост"},
        {"text": "bridge", "translation": "  "},
        {"word_id": -1},
        {"text": "a" * 101, "translation": "мост"},
    ],
)
async def test_blank_and_invalid_words_rejected(client: AsyncClient, auth_headers, body):
    assert (await client.post("/vocabulary", headers=auth_headers, json=body)).status_code == 422
