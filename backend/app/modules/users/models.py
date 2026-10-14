from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, IntPK
from app.core.enums import CefrLevel, pg_enum


class User(Base):
    __tablename__ = "users"

    id: Mapped[IntPK]
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    display_name: Mapped[str]
    cefr_level: Mapped[CefrLevel] = mapped_column(
        pg_enum(CefrLevel, "cefr_level"), server_default=CefrLevel.A1.value
    )
    telegram_id: Mapped[int | None] = mapped_column(unique=True)
    created_at: Mapped[CreatedAt]


class TelegramLinkCode(Base):
    """Одноразовый код для привязки Telegram: t.me/<bot>?start=<code>."""

    __tablename__ = "telegram_link_codes"

    code: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime]
