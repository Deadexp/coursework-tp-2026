import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import LLMError, LLMRefusalError
from app.modules.dialogs.models import DialogMessage
from app.modules.dialogs.prompts import OPENING_TRIGGER
from app.modules.dialogs.schemas import DialogFeedback, SpeakerCorrection, SpeakerTurn
from app.modules.learning.models import Mistake
from app.seed import Course, seed

COURSE = Course.model_validate(
    {
        "error_types": [
            {"code": "present_simple", "name": "Present Simple", "topic": "Present Simple"},
            {"code": "vocabulary", "name": "Лексика", "topic": None},
        ],
        "topics": [{"title": "Present Simple", "cefr_level": "A1", "position": 1, "theory": "..."}],
    }
)


@pytest.fixture
async def error_types(db: AsyncSession) -> None:
    await seed(db, COURSE)


async def start(client: AsyncClient, headers: dict, scenario: str = "cafe") -> dict:
    response = await client.post("/dialogs", json={"scenario": scenario}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_scenarios_list(client: AsyncClient, auth_headers: dict) -> None:
    scenarios = (await client.get("/dialogs/scenarios", headers=auth_headers)).json()
    assert {"intro", "cafe", "airport", "interview", "free"} == {s["code"] for s in scenarios}


async def test_start_dialog_with_opening_line(
    client: AsyncClient, auth_headers: dict, fake_llm, error_types: None
) -> None:
    dialog = await start(client, auth_headers)

    assert dialog["title"] == "В кафе"
    assert [(m["role"], m["content"]) for m in dialog["messages"]] == [
        ("assistant", "Hi! I'm Emma. Nice to meet you!")
    ]
    call = fake_llm.calls[0]
    assert call["schema"] is SpeakerTurn and call["fast"] is True
    assert "barista" in call["system"] and "level is A1" in call["system"]
    assert "present_simple: Present Simple" in call["system"]
    assert call["messages"][0].content == OPENING_TRIGGER


async def test_unknown_scenario(client: AsyncClient, auth_headers: dict, fake_llm) -> None:
    response = await client.post("/dialogs", json={"scenario": "moon"}, headers=auth_headers)
    assert response.status_code == 422


async def test_message_saves_reply_and_typed_mistakes(
    client: AsyncClient, auth_headers: dict, fake_llm, error_types: None, db: AsyncSession
) -> None:
    dialog = await start(client, auth_headers)
    fake_llm.parse_replies[SpeakerTurn] = SpeakerTurn(
        corrections=[
            SpeakerCorrection(
                fragment="she like",
                correction="she likes",
                explanation_ru="С she глагол получает -s.",
                error_type="present_simple",
            ),
            SpeakerCorrection(
                fragment="cofee", correction="coffee", explanation_ru="Опечатка.", error_type="??"
            ),
            SpeakerCorrection(fragment=" ", correction="x", explanation_ru="-", error_type="x"),
        ],
        reply="Great choice! Anything else?",
    )

    response = await client.post(
        f"/dialogs/{dialog['id']}/messages",
        json={"content": "My friend she like cofee"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["reply"]["content"] == "Great choice! Anything else?"
    corrections = body["user_message"]["corrections"]
    assert [(c["fragment"], c["error_type"]["code"]) for c in corrections] == [
        ("she like", "present_simple"),
        ("cofee", "vocabulary"),  # неизвестный код модели → запасной тип
    ]
    mistakes = (await db.scalars(select(Mistake))).all()
    assert len(mistakes) == 2 and all(m.dialog_message_id is not None for m in mistakes)

    # Модели отправлена вся история: открывающий триггер, реплика Emma, реплика ученика.
    sent = fake_llm.calls[-1]["messages"]
    assert [m.role for m in sent] == ["user", "assistant", "user"]
    assert fake_llm.calls[-1]["fast"] is True  # живой диалог — быстрый режим

    full = (await client.get(f"/dialogs/{dialog['id']}", headers=auth_headers)).json()
    assert [m["role"] for m in full["messages"]] == ["assistant", "user", "assistant"]
    assert len(full["messages"][1]["corrections"]) == 2


async def test_llm_failure_writes_nothing(
    client: AsyncClient, auth_headers: dict, fake_llm, error_types: None, db: AsyncSession
) -> None:
    dialog = await start(client, auth_headers)
    fake_llm.error = LLMError("Языковая модель временно недоступна")

    response = await client.post(
        f"/dialogs/{dialog['id']}/messages", json={"content": "Hello"}, headers=auth_headers
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Языковая модель временно недоступна"
    assert await db.scalar(select(func.count()).select_from(DialogMessage)) == 1


async def test_refusal_is_422(
    client: AsyncClient, auth_headers: dict, fake_llm, error_types: None
) -> None:
    dialog = await start(client, auth_headers)
    fake_llm.error = LLMRefusalError("Модель отказалась отвечать на этот запрос")

    response = await client.post(
        f"/dialogs/{dialog['id']}/messages", json={"content": "..."}, headers=auth_headers
    )
    assert response.status_code == 422


async def test_finish_saves_feedback_once(
    client: AsyncClient, auth_headers: dict, fake_llm, error_types: None
) -> None:
    dialog = await start(client, auth_headers)
    fake_llm.parse_replies[SpeakerTurn] = SpeakerTurn(corrections=[], reply="Sure!")
    fake_llm.parse_replies[DialogFeedback] = DialogFeedback(
        summary_ru="Хороший разговор.", strengths_ru=["Вежливость"], to_improve_ru=["Артикли"]
    )
    await client.post(
        f"/dialogs/{dialog['id']}/messages",
        json={"content": "A coffee, please"},
        headers=auth_headers,
    )

    finished = (await client.post(f"/dialogs/{dialog['id']}/finish", headers=auth_headers)).json()
    again = await client.post(f"/dialogs/{dialog['id']}/finish", headers=auth_headers)

    assert finished["ended_at"] is not None
    assert finished["summary"].startswith("Хороший разговор.")
    assert "• Артикли" in finished["summary"]
    assert again.status_code == 200
    assert sum(c["schema"] is DialogFeedback for c in fake_llm.calls) == 1
    assert next(c for c in fake_llm.calls if c["schema"] is DialogFeedback)["fast"] is False
    transcript = next(c for c in fake_llm.calls if c["schema"] is DialogFeedback)["messages"][0]
    assert "Learner: A coffee, please" in transcript.content

    closed = await client.post(
        f"/dialogs/{dialog['id']}/messages", json={"content": "Hi"}, headers=auth_headers
    )
    assert closed.status_code == 409


async def test_other_users_dialog_is_hidden(
    client: AsyncClient, auth_headers: dict, fake_llm, error_types: None
) -> None:
    dialog = await start(client, auth_headers)
    await client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "other-pass", "display_name": "Other"},
    )
    token = (
        await client.post(
            "/auth/login", data={"username": "other@example.com", "password": "other-pass"}
        )
    ).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}

    assert (await client.get(f"/dialogs/{dialog['id']}", headers=other)).status_code == 404
    assert (await client.get("/dialogs", headers=other)).json() == []
    assert len((await client.get("/dialogs", headers=auth_headers)).json()) == 1


async def test_without_api_key_ai_endpoints_answer_503(
    client: AsyncClient, auth_headers: dict, monkeypatch
) -> None:
    from app.core.config import settings
    from app.llm import get_llm

    get_llm.cache_clear()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    response = await client.post("/dialogs", json={"scenario": "cafe"}, headers=auth_headers)

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]
    get_llm.cache_clear()
