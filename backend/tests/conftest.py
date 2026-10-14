from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

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

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
