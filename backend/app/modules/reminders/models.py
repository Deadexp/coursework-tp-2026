from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, IntPK


class ReminderSettings(Base):
    __tablename__ = "reminder_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(server_default="false")
    delivery_time: Mapped[time] = mapped_column(Time(), server_default="19:00:00")
    timezone: Mapped[str] = mapped_column(server_default="Europe/Moscow")


class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date"),
        CheckConstraint(
            "status IN ('pending', 'claimed', 'sent', 'failed', 'cancelled')",
            name="reminder_delivery_status",
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="reminder_attempts"),
        CheckConstraint(
            "(status = 'claimed' AND claim_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (status <> 'claimed' AND lease_until IS NULL)",
            name="reminder_claim_lease",
        ),
        Index("ix_reminder_deliveries_status_not_before", "status", "not_before"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    local_date: Mapped[date]
    scheduled_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    claim_token: Mapped[UUID | None] = mapped_column(Uuid())
    lease_until: Mapped[datetime | None]
    not_before: Mapped[datetime]
    sent_at: Mapped[datetime | None]
    telegram_message_id: Mapped[int | None]
    last_outcome: Mapped[str | None]
    created_at: Mapped[CreatedAt]
