from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, IntPK
from app.core.enums import MessageRole, pg_enum


class Dialog(Base):
    __tablename__ = "dialogs"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ended_after_started"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scenario: Mapped[str]
    summary: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]


class DialogMessage(Base):
    __tablename__ = "dialog_messages"
    __table_args__ = (Index("ix_dialog_messages_dialog_id_created_at", "dialog_id", "created_at"),)

    id: Mapped[IntPK]
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(pg_enum(MessageRole, "msg_role"))
    content: Mapped[str]
    created_at: Mapped[CreatedAt]
