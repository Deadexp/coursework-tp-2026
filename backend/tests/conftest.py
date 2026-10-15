from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.db import get_session
from app.main import app
from app.models import Base

# Тесты работают в отдельной базе <имя>_test, чтобы не трогать данные разработки.
_DEV_URL = make_url(settings.database_url)
TEST_DB_URL = _DEV_URL.set(database=f"{_DEV_URL.database}_test")


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    admin = create_async_engine(_DEV_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_URL.database},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_URL.database}"'))
    await admin.dispose()

    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def _truncate_all(engine: AsyncEngine) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await _truncate_all(engine)


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Прямой доступ к тестовой БД — подготовить данные или проверить, что записалось."""
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await _truncate_all(engine)


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Заголовок авторизации зарегистрированного тестового пользователя."""
    credentials = {"email": "learner@example.com", "password": "learner-pass"}
    await client.post("/auth/register", json={**credentials, "display_name": "Learner"})
    response = await client.post(
        "/auth/login",
        data={"username": credentials["email"], "password": credentials["password"]},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class FakeLLM:
    """Подставная модель: отвечает заготовками и запоминает, что ей отправили."""

    def __init__(self) -> None:
        self.chat_reply = "Hi! I'm Emma. Nice to meet you!"
        self.parse_replies: dict[type, object] = {}
        self.error: Exception | None = None
        self.calls: list[dict] = []

    async def chat(self, system, messages, fast=False):
        self.calls.append({"system": system, "messages": messages, "schema": None, "fast": fast})
        if self.error:
            raise self.error
        return self.chat_reply

    async def parse(self, system, messages, schema, fast=False):
        self.calls.append({"system": system, "messages": messages, "schema": schema, "fast": fast})
        if self.error:
            raise self.error
        reply = self.parse_replies[schema]
        return reply(messages) if callable(reply) else reply


@pytest.fixture
def fake_llm(client: AsyncClient) -> FakeLLM:
    from app.llm import get_llm
    from app.modules.dialogs.schemas import SpeakerTurn

    fake = FakeLLM()
    # Приветствие собеседника по умолчанию; тесты переопределяют ответ на реплики.
    fake.parse_replies[SpeakerTurn] = SpeakerTurn(corrections=[], reply=fake.chat_reply)
    app.dependency_overrides[get_llm] = lambda: fake
    return fake
