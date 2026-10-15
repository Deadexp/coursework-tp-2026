from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str


class LLMError(Exception):
    """Языковая модель не настроена или временно недоступна — сервер отвечает 503."""


class LLMRefusalError(LLMError):
    """Модель отказалась отвечать по соображениям безопасности."""


class LLMClient(Protocol):
    async def chat(self, system: str, messages: list[Message]) -> str:
        """Свободный текстовый ответ (например, реплика собеседника)."""
        ...

    async def parse(self, system: str, messages: list[Message], schema: type[T]) -> T:
        """Ответ строго по Pydantic-схеме (разбор ошибок, план занятия)."""
        ...
