import asyncio
from collections import Counter

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.placement import service
from app.modules.placement.content import load_content
from app.modules.placement.models import PlacementAnswer


async def start(client: AsyncClient, headers: dict) -> dict:
    response = await client.post("/placement/attempts", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def answer_payload(state: dict, counts: dict[str, int] | None = None) -> dict:
    """Use the private bank only in tests, never in API question responses."""
    bank = {question.prompt: question for question in load_content().questions}
    remaining = dict(counts or {"A1": 8, "A2": 8, "B1": 8})
    answers = []
    for question in state["questions"]:
        correct = bank[question["prompt"]].correct_option_index
        take_correct = remaining[question["level"]] > 0
        remaining[question["level"]] -= 1
        answers.append(
            {
                "question_id": question["id"],
                "option_index": correct if take_correct else (correct + 1) % 4,
            }
        )
    return {"answers": answers}


async def submit(client: AsyncClient, headers: dict, state: dict, payload: dict | None = None):
    return await client.post(
        f"/placement/attempts/{state['id']}/submit",
        headers=headers,
        json=payload or answer_payload(state),
    )


async def other_user(client: AsyncClient) -> dict:
    account = {
        "email": "placement-other@example.com",
        "password": "another-long-password",
        "display_name": "Other learner",
    }
    assert (await client.post("/auth/register", json=account)).status_code == 201
    login = await client.post(
        "/auth/login", data={"username": account["email"], "password": account["password"]}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def assert_public_questions(state: dict) -> None:
    allowed = {"id", "position", "level", "skill", "prompt", "passage", "options"}
    assert state["result"] is None
    for question in state["questions"]:
        assert set(question) == allowed
        assert len(question["options"]) == 4
        assert all(isinstance(option, str) for option in question["options"])


def test_bank_has_balanced_levels_and_meaningful_reading() -> None:
    content = load_content()
    assert len(content.questions) == 24
    assert Counter(q.level for q in content.questions) == {"A1": 8, "A2": 8, "B1": 8}
    for level in ("A1", "A2", "B1"):
        assert Counter(q.skill for q in content.questions if q.level == level) == {
            "grammar": 4,
            "vocabulary": 2,
            "reading": 2,
        }
    assert all(q.passage and len(q.passage) > 80 for q in content.questions if q.skill == "reading")


async def test_all_placement_routes_require_authentication(client: AsyncClient) -> None:
    for path in ("/placement/history", "/placement/attempts/1"):
        assert (await client.get(path)).status_code == 401
    assert (await client.post("/placement/attempts")).status_code == 401
    assert (await client.post("/placement/attempts/1/apply")).status_code == 401
    payload = {"answers": [{"question_id": str(i), "option_index": 0} for i in range(1, 25)]}
    assert (await client.post("/placement/attempts/1/submit", json=payload)).status_code == 401


async def test_start_get_and_history_hide_answers(client: AsyncClient, auth_headers: dict) -> None:
    state = await start(client, auth_headers)
    assert state["total"] == 24 and state["status"] == "in_progress"
    assert state["submitted_at"] is None and state["applied_at"] is None
    assert_public_questions(state)
    fetched = (await client.get(f"/placement/attempts/{state['id']}", headers=auth_headers)).json()
    assert fetched == state
    assert_public_questions(fetched)
    history = (await client.get("/placement/history", headers=auth_headers)).json()
    assert len(history) == 1 and history[0]["questions"] == []
    assert history[0]["result"] is None


@pytest.mark.parametrize(
    ("counts", "level"),
    [
        ({"A1": 0, "A2": 0, "B1": 0}, "A1"),
        ({"A1": 8, "A2": 5, "B1": 8}, "A1"),
        ({"A1": 5, "A2": 8, "B1": 8}, "A1"),
        ({"A1": 6, "A2": 6, "B1": 5}, "A2"),
        ({"A1": 6, "A2": 6, "B1": 6}, "B1"),
        ({"A1": 8, "A2": 8, "B1": 8}, "B1"),
    ],
)
async def test_server_scores_each_block_and_applies_sequential_thresholds(
    client: AsyncClient, auth_headers: dict, counts: dict, level: str
) -> None:
    state = await start(client, auth_headers)
    response = await submit(client, auth_headers, state, answer_payload(state, counts))
    assert response.status_code == 200, response.text
    completed = response.json()
    result = completed["result"]
    assert completed["status"] == "completed" and completed["submitted_at"]
    assert result["recommended_level"] == level
    assert result["correct"] == sum(counts.values()) and result["total"] == 24
    assert result["scores"] == [
        {"level": level, "correct": counts[level], "total": 8} for level in ("A1", "A2", "B1")
    ]
    assert sum(a["is_correct"] for a in result["answers"]) == sum(counts.values())
    assert all(a["explanation"] for a in result["answers"])
    assert "не сертификация CEFR" in result["limitations"]
    assert "говорение, аудирование" in result["limitations"]
    assert completed["applied_at"] is None
    profile = (await client.get("/users/me", headers=auth_headers)).json()
    assert profile["cefr_level"] == "A1"  # Submission alone never changes the profile.


@pytest.mark.parametrize("variant", ["missing", "extra", "duplicate", "unknown", "forged"])
async def test_invalid_answer_sets_are_rejected_atomically(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, variant: str
) -> None:
    state = await start(client, auth_headers)
    payload = answer_payload(state)
    if variant == "missing":
        payload["answers"].pop()
    elif variant == "extra":
        payload["answers"].append(payload["answers"][0].copy())
    elif variant == "duplicate":
        payload["answers"][1] = payload["answers"][0].copy()
    elif variant == "unknown":
        payload["answers"][0]["question_id"] = "not-assigned"
    else:
        payload["answers"][0]["is_correct"] = True
        payload["recommended_level"] = "B1"
    response = await submit(client, auth_headers, state, payload)
    assert response.status_code == 422
    assert await db.scalar(select(func.count()).select_from(PlacementAnswer)) == 0
    unchanged = (
        await client.get(f"/placement/attempts/{state['id']}", headers=auth_headers)
    ).json()
    assert unchanged["submitted_at"] is None and unchanged["result"] is None


@pytest.mark.parametrize("option", [-1, 4, True, 1.5, "1"])
async def test_option_index_is_a_strict_valid_integer(
    client: AsyncClient, auth_headers: dict, option: object
) -> None:
    state = await start(client, auth_headers)
    payload = answer_payload(state)
    payload["answers"][0]["option_index"] = option
    assert (await submit(client, auth_headers, state, payload)).status_code == 422


async def test_questions_from_another_attempt_are_not_accepted(
    client: AsyncClient, auth_headers: dict
) -> None:
    first = await start(client, auth_headers)
    second = await start(client, auth_headers)
    assert not {q["id"] for q in first["questions"]} & {q["id"] for q in second["questions"]}
    assert (await submit(client, auth_headers, first, answer_payload(second))).status_code == 422


async def test_foreign_attempts_are_inaccessible_and_history_is_private(
    client: AsyncClient, auth_headers: dict
) -> None:
    state = await start(client, auth_headers)
    assert (await submit(client, auth_headers, state)).status_code == 200
    foreign_headers = await other_user(client)
    assert (
        await client.get(f"/placement/attempts/{state['id']}", headers=foreign_headers)
    ).status_code == 404
    assert (await submit(client, foreign_headers, state)).status_code == 404
    assert (
        await client.post(f"/placement/attempts/{state['id']}/apply", headers=foreign_headers)
    ).status_code == 404
    assert (await client.get("/placement/history", headers=foreign_headers)).json() == []
    assert (await client.get("/placement/attempts/999999", headers=auth_headers)).status_code == 404


async def test_repeated_submit_is_idempotent_and_changed_answers_cannot_overwrite(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
) -> None:
    state = await start(client, auth_headers)
    payload = answer_payload(state)
    first = (await submit(client, auth_headers, state, payload)).json()
    payload["answers"].reverse()
    assert (await submit(client, auth_headers, state, payload)).json() == first
    payload["answers"][0]["option_index"] = (payload["answers"][0]["option_index"] + 1) % 4
    assert (await submit(client, auth_headers, state, payload)).status_code == 409
    assert await db.scalar(select(func.count()).select_from(PlacementAnswer)) == 24
    current = (await client.get(f"/placement/attempts/{state['id']}", headers=auth_headers)).json()
    assert current == first


async def test_concurrent_retries_save_one_answer_set(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
) -> None:
    state = await start(client, auth_headers)
    payload = answer_payload(state)
    first, second = await asyncio.gather(
        submit(client, auth_headers, state, payload), submit(client, auth_headers, state, payload)
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await db.scalar(select(func.count()).select_from(PlacementAnswer)) == 24


async def test_explicit_apply_updates_profile_once_and_requires_completion(
    client: AsyncClient, auth_headers: dict
) -> None:
    state = await start(client, auth_headers)
    path = f"/placement/attempts/{state['id']}/apply"
    assert (await client.post(path, headers=auth_headers)).status_code == 409
    assert (await submit(client, auth_headers, state)).status_code == 200
    response = await client.post(path, headers=auth_headers)
    assert response.status_code == 200 and response.json()["applied_at"]
    assert (await client.get("/users/me", headers=auth_headers)).json()["cefr_level"] == "B1"
    await client.patch("/practice/level", headers=auth_headers, json={"level": "A2"})
    again = await client.post(path, headers=auth_headers)
    assert again.json()["applied_at"] == response.json()["applied_at"]
    assert (await client.get("/users/me", headers=auth_headers)).json()["cefr_level"] == "A2"


async def test_apply_rolls_back_profile_if_the_transaction_fails(
    client: AsyncClient, auth_headers: dict, monkeypatch
) -> None:
    state = await start(client, auth_headers)
    await submit(client, auth_headers, state)
    original = service.users.set_level

    async def fail_after_update(session, user_id, level, *, commit=True):
        assert commit is False
        await original(session, user_id, level, commit=False)
        await session.flush()
        raise RuntimeError("transaction interrupted")

    monkeypatch.setattr(service.users, "set_level", fail_after_update)
    with pytest.raises(RuntimeError, match="transaction interrupted"):
        await client.post(f"/placement/attempts/{state['id']}/apply", headers=auth_headers)
    assert (await client.get("/users/me", headers=auth_headers)).json()["cefr_level"] == "A1"
    current = (await client.get(f"/placement/attempts/{state['id']}", headers=auth_headers)).json()
    assert current["applied_at"] is None


async def test_history_uses_saved_content_and_is_ordered_and_bounded(
    client: AsyncClient, auth_headers: dict, monkeypatch
) -> None:
    first = await start(client, auth_headers)
    finished = (await submit(client, auth_headers, first)).json()
    second = await start(client, auth_headers)

    def unavailable_bank():
        raise RuntimeError("The current bank must not be needed to read old attempts")

    monkeypatch.setattr(service, "load_content", unavailable_bank)
    history = (await client.get("/placement/history", headers=auth_headers)).json()
    assert [attempt["id"] for attempt in history] == [second["id"], first["id"]]
    assert history[1]["result"] == finished["result"]
    assert all(attempt["questions"] == [] for attempt in history)
    limited = (await client.get("/placement/history?limit=1", headers=auth_headers)).json()
    assert len(limited) == 1 and limited[0]["id"] == second["id"]
    read = (await client.get(f"/placement/attempts/{first['id']}", headers=auth_headers)).json()
    assert read == finished
