import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.modules.vocabulary import practice_service
from app.modules.vocabulary.models import WordReview
from app.modules.vocabulary.practice_models import PracticeAnswer, PracticeSession
from tests.test_telegram import TEST_SERVICE, bot_headers, connect, other_user

WORDS = [{"text": f"word{i}", "translation": f"перевод{i}"} for i in range(5)]


@pytest.fixture(autouse=True)
def practice_settings(monkeypatch):
    monkeypatch.setattr(settings, "bot_service_token", TEST_SERVICE)
    monkeypatch.setattr(settings, "bot_username", "course_test_bot")


async def prepare(client, auth_headers, count=5):
    await connect(client, auth_headers)
    for word in WORDS[:count]:
        assert (
            await client.post("/vocabulary", headers=auth_headers, json=word)
        ).status_code == 201


async def start(client, mode="quiz"):
    return await client.post("/practice/sessions", headers=bot_headers(), json={"mode": mode})


async def submit(client, state, **payload):
    return await client.post(
        f"/practice/sessions/{state['session_id']}/answers",
        headers=bot_headers(),
        json={"position": state["question"]["position"], **payload},
    )


def correct_payload(question):
    if question["kind"] == "choice":
        word = next(w for w in WORDS if question["prompt"].endswith(w["text"]))
        return {"option_index": question["choices"].index(word["translation"])}
    word = next(w for w in WORDS if w["translation"] in question["prompt"])
    return {"answer": "  " + word["text"].upper() + ".  "}


async def test_empty_personal_dictionary_and_auth(client, auth_headers):
    await connect(client, auth_headers)
    assert (await start(client)).status_code == 412
    assert (await client.get("/practice/progress")).status_code == 401
    assert (
        await client.get("/practice/progress", headers=bot_headers(9000000002))
    ).status_code == 403
    result = (await client.get("/practice/progress", headers=bot_headers())).json()
    assert result["words"] == result["attempted"] == result["correct"] == 0


async def test_quiz_real_words_shared_scores_and_retry_receipt(client, auth_headers, db):
    await prepare(client, auth_headers)
    state = (await start(client)).json()
    assert state["total"] == 5
    assert state["cards_reviewed"] == 0
    first, first_payload, first_receipt = None, None, None
    while not state["completed"]:
        assert state["question"]["translation"] is None
        assert len(state["question"]["choices"]) == 4
        payload = correct_payload(state["question"])
        response = await submit(client, state, **payload)
        assert response.status_code == 200
        if first is None:
            first, first_payload, first_receipt = state, payload, response.json()
        state = response.json()["state"]
    assert (state["attempted"], state["correct"], state["cards_reviewed"]) == (5, 5, 0)
    replay = (await submit(client, first, **first_payload)).json()
    assert replay["next_review_at"] == first_receipt["next_review_at"]
    assert await db.scalar(select(func.count()).select_from(WordReview)) == 5
    assert await db.scalar(select(func.count()).select_from(PracticeAnswer)) == 5
    assert set((await db.scalars(select(WordReview.source))).all()) == {"bot"}
    progress = (await client.get("/practice/progress", headers=auth_headers)).json()
    assert (progress["attempted"], progress["correct"], progress["quizzes_completed"]) == (5, 5, 1)
    assert all(
        w["repetitions"] == 1
        for w in (await client.get("/vocabulary", headers=auth_headers)).json()
    )


async def test_single_word_uses_recall_without_invented_options(client, auth_headers):
    await prepare(client, auth_headers, count=1)
    state = (await start(client)).json()
    assert state["total"] == 1
    assert state["question"]["kind"] == "recall"
    assert state["question"]["choices"] == []
    assert "word0" not in state["question"]["prompt"]
    result = (await submit(client, state, **correct_payload(state["question"]))).json()
    assert result["is_correct"] is True
    assert result["state"]["completed"] is True


async def test_daily_three_cards_two_recalls_and_persistent_completion(client, auth_headers):
    await prepare(client, auth_headers)
    state = (await start(client, "daily")).json()
    for _ in range(3):
        assert state["question"]["kind"] == "card"
        # Self-rating before revealing is rejected without recording an answer.
        assert (await submit(client, state, quality=5)).status_code == 422
        response = await client.post(
            f"/practice/sessions/{state['session_id']}/reveal",
            headers=bot_headers(),
            json={"position": state["question"]["position"]},
        )
        state = response.json()
        assert state["question"]["translation"]
        state = (await submit(client, state, quality=5)).json()["state"]
    progress = (await client.get("/practice/progress", headers=auth_headers)).json()
    assert progress["attempted"] == progress["correct"] == 0
    assert progress["reviews"] == 3
    resumed = (await start(client, "daily")).json()
    assert resumed["session_id"] == state["session_id"]
    assert resumed["answered"] == 3 and not resumed["completed"]
    state = (await submit(client, state, **correct_payload(state["question"]))).json()["state"]
    result = (await submit(client, state, answer="definitely wrong")).json()
    state = result["state"]
    assert state["completed"] is True
    assert (state["cards_reviewed"], state["attempted"], state["correct"]) == (3, 2, 1)
    repeated = (await start(client, "daily")).json()
    assert repeated == state
    progress = (await client.get("/practice/progress", headers=bot_headers())).json()
    assert progress["daily_completed"] == 1
    assert progress["last_daily_date"] is not None
    assert len((await client.get("/vocabulary/problem-words", headers=bot_headers())).json()) == 1


async def test_partial_quiz_resumes_and_single_concurrent_start(client, auth_headers, db):
    await prepare(client, auth_headers)
    responses = await asyncio.gather(start(client), start(client))
    assert all(r.status_code == 200 for r in responses)
    states = [r.json() for r in responses]
    assert states[0]["session_id"] == states[1]["session_id"]
    first = states[0]
    result = (await submit(client, first, **correct_payload(first["question"]))).json()
    resumed = (await start(client)).json()
    assert resumed == result["state"]
    assert await db.scalar(select(func.count()).select_from(PracticeSession)) == 1


async def test_concurrent_answers_are_idempotent_and_cannot_skip(client, auth_headers, db):
    await prepare(client, auth_headers)
    state = (await start(client)).json()
    assert (
        await client.post(
            f"/practice/sessions/{state['session_id']}/answers",
            headers=bot_headers(),
            json={"position": 2, "option_index": 0},
        )
    ).status_code == 409
    payload = correct_payload(state["question"])
    results = await asyncio.gather(
        submit(client, state, **payload), submit(client, state, **payload)
    )
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json()["next_review_at"] == results[1].json()["next_review_at"]
    assert await db.scalar(select(func.count()).select_from(WordReview)) == 1
    wrong = {"option_index": (payload["option_index"] + 1) % 4}
    assert (await submit(client, state, **wrong)).status_code == 409


async def test_other_accounts_cannot_read_reveal_or_answer(client, auth_headers):
    await prepare(client, auth_headers)
    state = (await start(client, "daily")).json()
    second = await other_user(client)
    url = f"/practice/sessions/{state['session_id']}"
    assert (await client.get(url, headers=second)).status_code == 404
    assert (
        await client.post(url + "/reveal", headers=second, json={"position": 0})
    ).status_code == 404
    assert (
        await client.post(url + "/answers", headers=second, json={"position": 0, "quality": 5})
    ).status_code == 404
    assert (await client.get("/practice/progress", headers=second)).json()["reviews"] == 0


async def test_level_is_shared_profile_and_validated(client, auth_headers):
    await prepare(client, auth_headers, count=1)
    second = await other_user(client)
    assert (
        await client.patch("/practice/level", headers=bot_headers(), json={"level": "B2"})
    ).json() == {"level": "B2"}
    assert (await client.get("/users/me", headers=auth_headers)).json()["cefr_level"] == "B2"
    assert (await client.get("/users/me", headers=second)).json()["cefr_level"] == "A1"
    assert (
        await client.patch("/practice/level", headers=bot_headers(), json={"level": "A0"})
    ).status_code == 422
    assert (
        await client.patch(
            "/practice/level", headers=bot_headers(), json={"level": "A1", "user_id": 2}
        )
    ).status_code == 422


async def test_new_utc_day_has_new_daily_session(client, auth_headers, monkeypatch):
    await prepare(client, auth_headers, count=1)
    old = (await start(client, "daily")).json()
    next_day = practice_service.today() + timedelta(days=1)
    monkeypatch.setattr(practice_service, "today", lambda: next_day)
    assert (await submit(client, old, **correct_payload(old["question"]))).status_code == 409
    new = (await start(client, "daily")).json()
    assert new["session_id"] != old["session_id"]
    assert new["answered"] == 0


async def test_removed_word_does_not_trap_a_session(client, auth_headers):
    await prepare(client, auth_headers)
    state = (await start(client)).json()
    rows = (await client.get("/vocabulary", headers=auth_headers)).json()
    word = next(w["word"] for w in rows if state["question"]["prompt"].endswith(w["word"]["text"]))
    assert (
        await client.delete(f"/vocabulary/{word['id']}", headers=auth_headers)
    ).status_code == 204
    assert (await submit(client, state, **correct_payload(state["question"]))).status_code == 409
    new = (await start(client)).json()
    assert new["session_id"] != state["session_id"] and new["total"] == 4


async def test_existing_example_is_used_for_gap(client, auth_headers):
    await connect(client, auth_headers)
    await client.post(
        "/vocabulary",
        headers=auth_headers,
        json={
            "text": "bridge",
            "translation": "мост",
            "example": "We crossed the bridge.",
        },
    )
    state = (await start(client, "daily")).json()
    assert state["question"]["prompt"].startswith("We crossed the ___.")
    assert "bridge" not in state["question"]["prompt"]
    result = (await submit(client, state, answer="  BRIDGE. ")).json()
    assert result["is_correct"] is True


async def test_actual_bot_client_contract_for_daily_and_shared_level(client, auth_headers):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bot"))
    from bot.api_client import BackendClient

    await prepare(client, auth_headers)
    api = BackendClient("http://test", TEST_SERVICE, http=client)
    state = await api.start_practice(9000000001, "daily")
    while not state.completed:
        q = state.question
        if q.kind == "card":
            state = await api.reveal_practice(9000000001, state.session_id, q.position)
            payload = {"quality": 4}
        else:
            payload = correct_payload(q.model_dump())
        state = (
            await api.answer_practice(
                9000000001,
                state.session_id,
                state.question.position,
                **payload,
            )
        ).state
    progress = await api.progress(9000000001)
    assert (progress.daily_completed, progress.attempted, progress.correct) == (1, 2, 2)
    assert await api.level(9000000001, "B1") == "B1"
    assert (await client.get("/users/me", headers=auth_headers)).json()["cefr_level"] == "B1"
