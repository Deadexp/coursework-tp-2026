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
    async def chat(self, system: str, messages: list[Message], fast: bool = False) -> str:
        """Свободный текстовый ответ (например, реплика собеседника).

        fast=True — без размышлений модели: быстрее, для живого диалога.
        """
        ...

    async def parse(
        self, system: str, messages: list[Message], schema: type[T], fast: bool = False
    ) -> T:
        """Ответ строго по Pydantic-схеме (разбор ошибок, план занятия)."""
        ...
