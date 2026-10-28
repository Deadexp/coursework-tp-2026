import asyncio

import jwt
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.modules.learning import service
from app.modules.learning.models import Attempt, Mistake
from app.seed import Course, TopicIn, load_course, seed
from tests.test_telegram import TEST_SERVICE, bot_headers, connect, other_user


@pytest.fixture(autouse=True)
def grammar_settings(monkeypatch):
    monkeypatch.setattr(settings, "bot_service_token", TEST_SERVICE)
    monkeypatch.setattr(settings, "bot_username", "course_test_bot")


async def prepare(client, auth_headers, db):
    course = load_course()
    await seed(db, course)
    await connect(client, auth_headers)
    return {(t.title, e.prompt): e for t in course.topics for e in t.exercises}


async def start(client, topic_id=None, previous_token=None, headers=None):
    return await client.post(
        "/grammar/quizzes",
        headers=headers or bot_headers(),
        json={
            "topic_id": topic_id,
            "previous_token": previous_token,
        },
    )


async def submit(client, state, payload, headers=None):
    return await client.post(
        "/grammar/quizzes/answers",
        headers=headers or bot_headers(),
        json={
            "session_token": state["session_token"],
            "position": state["question"]["position"],
            **payload,
        },
    )


def right(question, bank):
    exercise = bank[question["topic"], question["prompt"]]
    if question["type"] == "multiple_choice":
        return {"option_index": question["options"].index(exercise.correct[0])}
    return {"answer": exercise.correct[0]}


def wrong(question, bank):
    exercise = bank[question["topic"], question["prompt"]]
    if question["type"] == "multiple_choice":
        return {
            "option_index": next(
                i for i, x in enumerate(question["options"]) if x not in exercise.correct
            )
        }
    return {"answer": "definitely wrong"}


async def test_real_course_topics_and_no_answer_leak(client, auth_headers, db):
    bank = await prepare(client, auth_headers, db)
    topics = (await client.get("/grammar/topics", headers=bot_headers())).json()
    assert len(topics) == 5
    assert sum(t["exercises_total"] for t in topics) == 30
    for topic in topics:
        state = (await start(client, topic["id"])).json()
        payload = jwt.decode(state["session_token"], options={"verify_signature": False})
        assert state["total"] == 5
        assert len(set(payload["ids"])) == 5
        question = state["question"]
        assert (question["topic"], question["prompt"]) in bank
        assert question["topic"] == topic["title"]
        assert "correct_answers" not in question and "is_correct" not in question
        assert "explanation" not in question


async def test_mixed_quiz_varies_and_uses_different_topics(client, auth_headers, db):
    await prepare(client, auth_headers, db)
    first = (await start(client)).json()
    ids1 = jwt.decode(first["session_token"], options={"verify_signature": False})["ids"]
    from app.modules.learning.models import Exercise

    topic_ids = (await db.scalars(select(Exercise.topic_id).where(Exercise.id.in_(ids1)))).all()
    assert len(set(topic_ids)) == 5
    second = (await start(client, previous_token=first["session_token"])).json()
    ids2 = jwt.decode(second["session_token"], options={"verify_signature": False})["ids"]
    assert not set(ids1).intersection(ids2)


async def test_common_grading_bot_attempts_and_site_progress(client, auth_headers, db, monkeypatch):
    bank = await prepare(client, auth_headers, db)
    topics = (await client.get("/grammar/topics", headers=bot_headers())).json()
    state = (await start(client, topics[0]["id"])).json()
    calls = []
    original = service.submit_attempt

    async def track(*args, **kwargs):
        calls.append(kwargs.get("quiz_request_id"))
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, "submit_attempt", track)
    while not state["completed"]:
        response = await submit(client, state, right(state["question"], bank))
        assert response.status_code == 200
        state = response.json()["state"]
    assert (state["correct"], state["answered"], state["total"]) == (5, 5, 5)
    assert len(calls) == 5 and all(calls)
    attempts = (await db.scalars(select(Attempt))).all()
    assert len(attempts) == 5 and all(a.source == "bot" and a.is_correct for a in attempts)
    site = (await client.get("/topics", headers=auth_headers)).json()
    assert site[0]["exercises_solved"] == 5
    assert (await client.get("/practice/progress", headers=auth_headers)).json()[
        "grammar_correct"
    ] == 5


async def test_wrong_answers_explanation_and_mistake_topics(client, auth_headers, db):
    bank = await prepare(client, auth_headers, db)
    state = (await start(client)).json()
    first = state["question"]
    result = (await submit(client, state, wrong(first, bank))).json()
    assert result["is_correct"] is False
    assert result["correct_answers"] == bank[first["topic"], first["prompt"]].correct
    assert result["explanation"] == bank[first["topic"], first["prompt"]].explanation
    assert await db.scalar(select(func.count()).select_from(Mistake)) == 1
    state = result["state"]
    while not state["completed"]:
        state = (await submit(client, state, right(state["question"], bank))).json()["state"]
    assert state["correct"] == 4
    assert state["mistake_topics"] == [first["topic"]]


async def test_all_four_real_types_and_short_quiz(client, auth_headers, db):
    original = load_course()
    by_type = {}
    for topic in original.topics:
        for ex in topic.exercises:
            by_type.setdefault(ex.type, ex.model_copy(update={"error_type": None}))
    course = Course(
        error_types=[],
        topics=[
            TopicIn(
                title="All supported types",
                cefr_level="A1",
                position=1,
                theory="",
                exercises=list(by_type.values()),
            )
        ],
    )
    await seed(db, course)
    await connect(client, auth_headers)
    bank = {(course.topics[0].title, e.prompt): e for e in course.topics[0].exercises}
    state = (await start(client)).json()
    assert state["total"] == 4
    kinds = set()
    while not state["completed"]:
        q = state["question"]
        kinds.add(q["type"])
        if q["type"] == "word_order":
            assert q["words"] and not q["options"]
        response = await submit(client, state, right(q, bank))
        assert response.status_code == 200 and response.json()["is_correct"]
        state = response.json()["state"]
    assert kinds == {"multiple_choice", "fill_gap", "translate", "word_order"}


async def test_replay_concurrency_and_out_of_order(client, auth_headers, db):
    bank = await prepare(client, auth_headers, db)
    state = (await start(client)).json()
    forged = await client.post(
        "/grammar/quizzes/answers",
        headers=bot_headers(),
        json={
            "session_token": state["session_token"],
            "position": 3,
            "answer": "x",
        },
    )
    assert forged.status_code == 409
    payload = right(state["question"], bank)
    responses = await asyncio.gather(submit(client, state, payload), submit(client, state, payload))
    assert [r.status_code for r in responses] == [200, 200]
    assert await db.scalar(select(func.count()).select_from(Attempt)) == 1
    assert responses[0].json()["state"]["correct"] == responses[1].json()["state"]["correct"] == 1
    assert (await submit(client, state, wrong(state["question"], bank))).status_code == 409


async def test_two_users_are_independent_and_token_is_bound(client, auth_headers, db):
    bank = await prepare(client, auth_headers, db)
    second = await other_user(client)
    await connect(client, second, sender=9000000002)
    first_state = (await start(client)).json()
    second_state = (await start(client, headers=bot_headers(9000000002))).json()
    assert (
        await submit(
            client,
            first_state,
            right(first_state["question"], bank),
            headers=bot_headers(9000000002),
        )
    ).status_code == 404
    await submit(client, first_state, right(first_state["question"], bank))
    assert (await client.get("/topics", headers=second)).json()[0]["exercises_solved"] in (0,)
    result = await submit(
        client, second_state, right(second_state["question"], bank), headers=bot_headers(9000000002)
    )
    assert result.status_code == 200
    attempts = (await db.scalars(select(Attempt))).all()
    assert len(attempts) == 2 and len({a.user_id for a in attempts}) == 2


async def test_service_auth_and_no_arbitrary_user_or_source(client, auth_headers, db):
    await prepare(client, auth_headers, db)
    assert (await client.get("/grammar/topics")).status_code == 401
    assert (
        await client.get("/grammar/topics", headers={"X-Service-Token": TEST_SERVICE})
    ).status_code == 401
    assert (await client.get("/grammar/topics", headers=bot_headers(999999))).status_code == 403
    assert (
        await client.post("/grammar/quizzes", headers=bot_headers(), json={"user_id": 1})
    ).status_code == 422
    state = (await start(client)).json()
    assert (
        await client.post(
            "/grammar/quizzes/answers",
            headers=bot_headers(),
            json={
                "session_token": state["session_token"],
                "position": 0,
                "answer": "x",
                "source": "web",
            },
        )
    ).status_code == 422
    assert await db.scalar(select(func.count()).select_from(Attempt)) == 0


async def test_quiz_token_cannot_be_used_as_login_or_forged(client, auth_headers, db):
    bank = await prepare(client, auth_headers, db)
    state = (await start(client)).json()
    assert (
        await client.get(
            "/users/me",
            headers={
                "Authorization": "Bearer " + state["session_token"],
            },
        )
    ).status_code == 401
    token = state["session_token"]
    segments = token.split(".")
    segments[1] = segments[1][:-2] + "aa"
    altered = dict(state, session_token=".".join(segments))
    assert (await submit(client, altered, right(state["question"], bank))).status_code == 409
    login_token = auth_headers["Authorization"].split(" ", 1)[1]
    altered["session_token"] = login_token
    assert (await submit(client, altered, right(state["question"], bank))).status_code == 409
    assert await db.scalar(select(func.count()).select_from(Attempt)) == 0


async def test_no_exercises_no_fallback_and_unknown_topic(client, auth_headers):
    await connect(client, auth_headers)
    assert (await client.get("/grammar/topics", headers=bot_headers())).json() == []
    assert (await start(client)).status_code == 412
    assert (await start(client, 999999)).status_code == 404


async def test_seed_repetition_preserves_attempts_and_no_duplicates(client, auth_headers, db):
    bank = await prepare(client, auth_headers, db)
    state = (await start(client)).json()
    await submit(client, state, right(state["question"], bank))
    await seed(db, load_course())
    topics = (await client.get("/grammar/topics", headers=bot_headers())).json()
    assert len(topics) == 5 and sum(t["exercises_total"] for t in topics) == 30
    assert await db.scalar(select(func.count()).select_from(Attempt)) == 1


async def test_actual_bot_client_contract(client, auth_headers, db):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bot"))
    from bot.api_client import BackendClient

    bank = await prepare(client, auth_headers, db)
    api = BackendClient("http://test", TEST_SERVICE, http=client)
    topics = await api.grammar_topics(9000000001)
    state = await api.start_grammar(9000000001, topics[0].id)
    while not state.completed:
        feedback = await api.answer_grammar(
            9000000001,
            state.session_token,
            state.question.position,
            **right(state.question.model_dump(), bank),
        )
        state = feedback.state
    assert state.correct == state.total == 5
