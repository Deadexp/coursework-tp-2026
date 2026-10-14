from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate

# Хэш для проверки, когда пользователя нет: время ответа не выдаёт, зарегистрирован ли email.
_DUMMY_HASH = hash_password("dummy-password")


class EmailAlreadyRegisteredError(Exception):
    pass


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        display_name=data.display_name,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise EmailAlreadyRegisteredError from None
    await session.refresh(user)
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)
