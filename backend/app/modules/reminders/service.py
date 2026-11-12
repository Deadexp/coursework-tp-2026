from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reminders.models import ReminderDelivery, ReminderSettings
from app.modules.reminders.schemas import Acknowledge, ClaimRead, SettingsPatch, SettingsRead
from app.modules.users.models import User

CATCH_UP = timedelta(hours=1)
LEASE = timedelta(minutes=3)
MAX_ATTEMPTS = 3
DEFAULT_TIME = time(19, 0)
DEFAULT_TIMEZONE = "Europe/Moscow"


def utcnow() -> datetime:
    return datetime.now(UTC)


def scheduled_at(day: date, at: time, timezone: str) -> datetime | None:
    """First occurrence at a DST fold; skip nonexistent local times at a spring gap."""
    zone = ZoneInfo(timezone)
    wall = datetime.combine(day, at)
    instant = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
    if instant.astimezone(zone).replace(tzinfo=None) != wall:
        return None
    return instant


def settings_read(value: ReminderSettings | None) -> SettingsRead:
    return SettingsRead(
        enabled=value.enabled if value else False,
        time=(value.delivery_time if value else DEFAULT_TIME).strftime("%H:%M"),
        timezone=value.timezone if value else DEFAULT_TIMEZONE,
    )


async def get_settings(db: AsyncSession, user_id: int) -> SettingsRead:
    return settings_read(await db.get(ReminderSettings, user_id))


async def patch_settings(db: AsyncSession, user_id: int, data: SettingsPatch) -> SettingsRead:
    # Serialize creation for this user. All other operations lock settings before deliveries.
    account = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if account is None:
        raise HTTPException(404, "Account not found")
    value = await db.scalar(
        select(ReminderSettings).where(ReminderSettings.user_id == user_id).with_for_update()
    )
    if value is None:
        value = ReminderSettings(
            user_id=user_id,
            enabled=False,
            delivery_time=DEFAULT_TIME,
            timezone=DEFAULT_TIMEZONE,
        )
        db.add(value)
    if data.enabled is True and account.telegram_id is None:
        raise HTTPException(409, "Сначала подключите Telegram к аккаунту")
    changed = False
    for name in data.model_fields_set:
        attribute = "delivery_time" if name == "time" else name
        incoming = time.fromisoformat(data.time) if name == "time" else getattr(data, name)
        changed = changed or getattr(value, attribute) != incoming
        setattr(value, attribute, incoming)
    if changed:
        # Revoke queued leases; an already in-flight Telegram request can still complete.
        await db.execute(
            update(ReminderDelivery)
            .where(
                ReminderDelivery.user_id == user_id,
                ReminderDelivery.status.in_(("pending", "claimed")),
            )
            .values(status="cancelled", lease_until=None, last_outcome="settings_changed")
        )
    await db.commit()
    return settings_read(value)


async def claim_due(db: AsyncSession, limit: int = 1) -> list[ClaimRead]:
    now = utcnow()
    # SKIP LOCKED makes concurrent workers disjoint. A unique user/day constraint is a
    # second guard; claim tokens prevent a late worker from acknowledging a newer lease.
    candidates = (
        await db.execute(
            select(ReminderSettings, User.telegram_id)
            .join(User, User.id == ReminderSettings.user_id)
            .where(ReminderSettings.enabled.is_(True), User.telegram_id.is_not(None))
            .order_by(ReminderSettings.user_id)
            .with_for_update(of=ReminderSettings, skip_locked=True)
        )
    ).all()
    claimed: list[ClaimRead] = []
    for config, telegram_id in candidates:
        await db.execute(
            update(ReminderDelivery)
            .where(
                ReminderDelivery.user_id == config.user_id,
                ReminderDelivery.status.in_(("pending", "claimed")),
                ReminderDelivery.scheduled_at < now - CATCH_UP,
            )
            .values(status="failed", lease_until=None, last_outcome="expired")
        )
        today = now.astimezone(ZoneInfo(config.timezone)).date()
        window = [
            (day, scheduled_at(day, config.delivery_time, config.timezone))
            for day in (today, today - timedelta(days=1))
        ]
        current = next(
            ((day, due) for day, due in window if due is not None and due <= now <= due + CATCH_UP),
            None,
        )
        if current is None:
            continue
        local_day, due = current
        delivery = await db.scalar(
            select(ReminderDelivery)
            .where(
                ReminderDelivery.user_id == config.user_id,
                ReminderDelivery.local_date == local_day,
            )
            .with_for_update()
        )
        if delivery is not None:
            if delivery.status not in ("pending", "claimed"):
                continue
            if delivery.status == "claimed" and delivery.lease_until > now:
                continue
            if delivery.not_before > now:
                continue
            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status, delivery.lease_until = "failed", None
                delivery.last_outcome = "attempts_exhausted"
                continue
        else:
            delivery = ReminderDelivery(
                user_id=config.user_id,
                local_date=local_day,
                scheduled_at=due,
                status="pending",
                attempts=0,
                not_before=now,
            )
            db.add(delivery)
        delivery.status = "claimed"
        delivery.claim_token = uuid4()
        delivery.lease_until = now + LEASE
        delivery.attempts += 1
        delivery.last_outcome = None
        await db.flush()
        claimed.append(
            ClaimRead(
                delivery_id=delivery.id,
                claim_token=delivery.claim_token,
                telegram_id=telegram_id,
                local_date=delivery.local_date,
                scheduled_at=delivery.scheduled_at,
            )
        )
        if len(claimed) == limit:
            break
    await db.commit()
    return claimed


async def acknowledge(db: AsyncSession, delivery_id: int, data: Acknowledge) -> str:
    user_id = await db.scalar(
        select(ReminderDelivery.user_id).where(ReminderDelivery.id == delivery_id)
    )
    if user_id is None:
        raise HTTPException(404, "Reminder delivery not found")
    config = await db.scalar(
        select(ReminderSettings).where(ReminderSettings.user_id == user_id).with_for_update()
    )
    delivery = await db.scalar(
        select(ReminderDelivery)
        .where(ReminderDelivery.id == delivery_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if delivery.claim_token != data.claim_token:
        raise HTTPException(409, "Reminder lease was replaced")
    if delivery.last_outcome == data.outcome:
        return delivery.status
    if delivery.status == "sent":
        raise HTTPException(409, "Reminder was already delivered")
    if delivery.status == "cancelled" and data.outcome not in ("sent", "forbidden"):
        return delivery.status
    now = utcnow()
    delivery.lease_until = None
    delivery.last_outcome = data.outcome
    if data.outcome == "sent":
        delivery.status = "sent"
        delivery.sent_at = now
        delivery.telegram_message_id = data.telegram_message_id
    elif data.outcome == "forbidden":
        delivery.status = "failed"
        if config is not None:
            config.enabled = False
    elif data.outcome == "failed":
        delivery.status = "failed"
    else:
        delay = max(60 * 3 ** (delivery.attempts - 1), data.retry_after_seconds)
        retry_at = now + timedelta(seconds=delay)
        if (
            config is None
            or not config.enabled
            or delivery.attempts >= MAX_ATTEMPTS
            or retry_at > delivery.scheduled_at + CATCH_UP
        ):
            delivery.status = "failed"
        else:
            delivery.status = "pending"
            delivery.not_before = retry_at
    await db.commit()
    return delivery.status
