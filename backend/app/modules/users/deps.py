from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.db import SessionDep
from app.core.security import decode_access_token
from app.modules.users import service
from app.modules.users.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
) -> User:
    user_id = decode_access_token(token)
    user = await service.get_user(session, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
