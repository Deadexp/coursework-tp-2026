import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import TelegramLinkCode, User


class InvalidLinkCode(Exception):
    pass


class TelegramLinkConflict(Exception):
    pass


async def issue_link_code(session: AsyncSession, user_id: int) -> tuple[str, datetime]:
    # Issuance and redemption lock the user first, avoiding opposite lock ordering.
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user.telegram_id is not None:
        raise TelegramLinkConflict
    await session.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id == user_id))
    code = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(minutes=10)
    session.add(
        TelegramLinkCode(
            code=hashlib.sha256(code.encode()).hexdigest(),
            user_id=user_id,
            expires_at=expires,
        )
    )
    await session.commit()
    return code, expires


async def redeem_link_code(session: AsyncSession, code: str, telegram_id: int) -> User:
    digest = hashlib.sha256(code.encode()).hexdigest()
    owner_id = await session.scalar(
        select(TelegramLinkCode.user_id).where(TelegramLinkCode.code == digest)
    )
    if owner_id is None:
        raise InvalidLinkCode
    user = await session.scalar(select(User).where(User.id == owner_id).with_for_update())
    if user is None:
        raise InvalidLinkCode
    # DELETE RETURNING is atomic: a concurrent request cannot consume the same code twice.
    consumed = await session.scalar(
        delete(TelegramLinkCode)
        .where(
            TelegramLinkCode.code == digest,
            TelegramLinkCode.expires_at > datetime.now(UTC),
        )
        .returning(TelegramLinkCode.user_id)
    )
    if consumed is None:
        raise InvalidLinkCode
    if user.telegram_id is not None and user.telegram_id != telegram_id:
        await session.rollback()
        raise TelegramLinkConflict
    user.telegram_id = telegram_id
    try:
        # The existing UNIQUE(users.telegram_id) also protects races across accounts.
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise TelegramLinkConflict from None
    return user
