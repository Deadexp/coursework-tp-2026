from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.db import SessionDep
from app.core.security import create_access_token
from app.modules.users import service
from app.modules.users.deps import CurrentUser
from app.modules.users.models import User
from app.modules.users.schemas import Token, UserCreate, UserRead

router = APIRouter()


@router.post(
    "/auth/register",
    tags=["auth"],
    status_code=status.HTTP_201_CREATED,
    response_model=UserRead,
)
async def register(data: UserCreate, session: SessionDep) -> User:
    try:
        return await service.create_user(session, data)
    except service.EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None


@router.post("/auth/login", tags=["auth"])
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    """Форма OAuth2: в поле `username` передаётся email. Так работает кнопка Authorize в Swagger."""
    user = await service.authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/users/me", tags=["users"], response_model=UserRead)
async def read_me(user: CurrentUser) -> User:
    return user
