from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Identity, MetaData, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column

from app.core.config import settings

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Предсказуемые имена ограничений нужны Alembic, чтобы миграции могли их удалять/менять.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

IntPK = Annotated[int, mapped_column(Identity(), primary_key=True)]
CreatedAt = Annotated[datetime, mapped_column(server_default=func.now())]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        int: BigInteger,
        str: Text,
        datetime: DateTime(timezone=True),
    }


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
