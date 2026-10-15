import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dialogs.schemas import SpeakerCorrection, SpeakerTurn
from app.modules.recommendations.schemas import MentorPlan, MentorStep
from app.seed import Course, seed

COURSE = Course.model_validate(
    {
        "error_types": [
            {"code": "articles", "name": "Артикли", "topic": "Articles"},
            {"code": "vocabulary", "name": "Лексика", "topic": None},
        ],
        "topics": [
            {
                "title": "Articles",
                "cefr_level": "A1",
                "position": 1,
                "theory": "...",
                "words": [{"text": "apple", "part_of_speech": "noun", "translation": "яблоко"}],
                "exercises": [
                    {
                        "type": "multiple_choice",
                        "prompt": "I saw ___ elephant.",
                        "options": ["a", "an"],
                        "correct": ["an"],
                    }
                ],
            },
            {"title": "Past Simple", "cefr_level": "A2", "position": 2, "theory": "..."},
        ],
    }
)


@pytest.fixture
async def course(db: AsyncSession) -> None:
    await seed(db, COURSE)


def plan(*steps: MentorStep) -> MentorPlan:
    return MentorPlan(summary_ru="Сегодня — артикли.", steps=list(steps))


async def test_no_plan_yet(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/recommendations/plan", headers=auth_headers)
    assert response.status_code == 200 and response.json() is None


async def test_mentor_sees_mistakes_from_exercises_and_dialogs(
    client: AsyncClient, auth_headers: dict, fake_llm, course: None
) -> None:
    # Ошибка в упражнении, ошибка в диалоге и слово к повторению.
    await client.post("/exercises/1/attempts", json={"answer": "a"}, headers=auth_headers)
    dialog = (await client.post("/dialogs", json={"scenario": "free"}, headers=auth_headers)).json()
    fake_llm.parse_replies[SpeakerTurn] = SpeakerTurn(
        corrections=[
            SpeakerCorrection(
                fragment="a apple", correction="an apple", explanation_ru="-", error_type="articles"
            )
        ],
        reply="Nice!",
    )
    await client.post(
        f"/dialogs/{dialog['id']}/messages", json={"content": "I ate a apple"}, headers=auth_headers
    )
    await client.post("/vocabulary/topics/1", headers=auth_headers)
    fake_llm.parse_replies[MentorPlan] = plan(
        MentorStep(type="dialog", topic_id=None, reason_ru="-")
    )

    await client.post("/recommendations/plan", headers=auth_headers)

    sent = fake_llm.calls[-1]["messages"][0].content
    context = json.loads(sent.split("\n", 1)[1])
    weak = context["weak_spots_last_14_days"][0]
    assert (weak["skill"], weak["mistakes"], weak["topic_id"]) == ("Артикли", 2, 1)
    assert "a apple → an apple" in weak["examples"]
    assert context["words_due_today"] == 1
    assert context["topics"][0]["solved"] == "0/1"


async def test_plan_keeps_only_valid_steps(
    client: AsyncClient, auth_headers: dict, fake_llm, course: None
) -> None:
    fake_llm.parse_replies[MentorPlan] = plan(
        MentorStep(type="topic", topic_id=1, reason_ru="Ошибки в артиклях."),
        MentorStep(type="topic", topic_id=999, reason_ru="Несуществующая тема."),
        MentorStep(type="word_review", topic_id=None, reason_ru="5 слов ждут."),
        MentorStep(type="topic", topic_id=1, reason_ru="Повтор."),
        MentorStep(type="dialog", topic_id=None, reason_ru="Практика."),
    )

    response = await client.post("/recommendations/plan", headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["summary"] == "Сегодня — артикли."
    assert [(i["position"], i["type"], i["title"]) for i in body["items"]] == [
        (1, "topic", "Articles"),
        (2, "word_review", "Повторить слова"),
        (3, "dialog", "Поговорить с собеседником"),
    ]
    assert body["items"][0]["reason"] == "Ошибки в артиклях."
    assert (await client.get("/recommendations/plan", headers=auth_headers)).json() == body


async def test_plan_without_valid_steps_is_503(
    client: AsyncClient, auth_headers: dict, fake_llm, course: None
) -> None:
    fake_llm.parse_replies[MentorPlan] = plan(MentorStep(type="topic", topic_id=42, reason_ru="-"))

    response = await client.post("/recommendations/plan", headers=auth_headers)

    assert response.status_code == 503
    assert (await client.get("/recommendations/plan", headers=auth_headers)).json() is None


async def test_mark_step_done(
    client: AsyncClient, auth_headers: dict, fake_llm, course: None
) -> None:
    fake_llm.parse_replies[MentorPlan] = plan(
        MentorStep(type="dialog", topic_id=None, reason_ru="-")
    )
    item_id = (await client.post("/recommendations/plan", headers=auth_headers)).json()["items"][0][
        "id"
    ]

    done = await client.post(f"/recommendations/plan/items/{item_id}/done", headers=auth_headers)

    assert done.json()["done"] is True
    plan_now = (await client.get("/recommendations/plan", headers=auth_headers)).json()
    assert plan_now["items"][0]["done"] is True
    missing = await client.post("/recommendations/plan/items/999/done", headers=auth_headers)
    assert missing.status_code == 404
