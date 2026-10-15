"""Проверка подключения к языковой модели.

Запуск: docker compose run --rm api python -m app.llm.check
Отправляет один короткий запрос (стоит доли цента) и печатает ответ. Ключ не выводится.
"""

import asyncio

from pydantic import BaseModel

from app.core.config import settings
from app.llm import LLMError, Message, get_llm


class Correction(BaseModel):
    corrected: str
    explanation_ru: str


async def main() -> None:
    print(f"Провайдер: {settings.llm_provider}, модель: {settings.llm_model}")
    print(f"Effort: {settings.llm_effort}")
    try:
        llm = get_llm()
        reply = await llm.chat(
            "You are a friendly English tutor. Answer in one short sentence.",
            [Message("user", "Hi! Say hello to a new student.")],
        )
        print(f"Текстовый ответ: {reply}")
        fix = await llm.parse(
            "You correct English sentences written by Russian-speaking learners.",
            [Message("user", "She don't like coffee.")],
            Correction,
        )
        print(f"Структурированный ответ: {fix.corrected!r} — {fix.explanation_ru}")
        print("Подключение работает.")
    except LLMError as e:
        print(f"Ошибка: {e}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(main())
