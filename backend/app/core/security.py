from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

_hasher = PasswordHash.recommended()  # argon2
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.jwt_secret, _ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """id пользователя из токена или None, если токен поддельный, просрочен или битый."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
