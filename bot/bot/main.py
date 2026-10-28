import argparse
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import (
    TelegramConflictError,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import BotCommand
from aiogram.utils.token import TokenValidationError
from pydantic import ValidationError


async def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram-бот курсового проекта")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--demo", action="store_true", help="Учебные слова без сайта и LLM")
    modes.add_argument(
        "--connected", action="store_true", help="Общий словарь через backend (по умолчанию)"
    )
    args = parser.parse_args()
    from bot.config import settings

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    backend = None
    if args.demo:
        from bot.demo import DemoClient
        from bot.demo_handlers import make_demo_router

        dispatcher.include_router(make_demo_router(DemoClient()))
    else:
        from bot.api_client import BackendClient
        from bot.connected_handlers import make_connected_router

        if (
            len(settings.bot_service_token.strip()) < 32
            or settings.bot_service_token == "replace-with-a-random-service-token"
        ):
            raise SystemExit(
                "Подключённому режиму нужен непустой случайный BOT_SERVICE_TOKEN (не менее 32 символов), одинаковый у сервера и бота. См. CONNECTED-WINDOWS.md."
            )
        backend = BackendClient(settings.api_base_url, settings.bot_service_token)
        dispatcher.include_router(make_connected_router(backend, settings.website_url))
    try:
        async with Bot(settings.bot_token) as bot:
            commands = [
                ("start", "Главное меню"),
                ("review", "Карточки: вспомнить перевод"),
                ("quiz", "Мини-тест"),
                ("difficult", "Сложные слова"),
                ("daily", "Практика дня: карточки и пропуски"),
                ("talk", "Разговор на английском (пока недоступен)"),
                ("level", "Уровень английского"),
                ("progress", "Мой прогресс"),
                ("stop", "Закончить занятие"),
                ("link", "О связи с сайтом"),
                ("help", "Помощь"),
            ]
            if not args.demo:
                commands = [
                    ("start", "Главное меню"),
                    ("dictionary", "Мой словарь"),
                    ("addword", "Добавить слово"),
                    ("review", "Карточки из личного словаря"),
                    ("difficult", "Сложные слова"),
                    ("link", "Как подключить аккаунт"),
                    ("cancel", "Отмена"),
                    ("stop", "Закончить занятие"),
                    ("help", "Помощь"),
                    ("quiz", "Мини-тест"),
                    ("wordquiz", "Тест по личным словам"),
                    ("daily", "Практика дня"),
                    ("progress", "Мой прогресс"),
                    ("level", "Уровень английского"),
                    ("talk", "О разговоре на английском"),
                ]
            await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in commands])
            await dispatcher.start_polling(bot)
    finally:
        if backend is not None:
            await backend.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (TokenValidationError, ValidationError):
        raise SystemExit(
            "Не удалось прочитать настройки бота\n\n"
            "Проверь BOT_TOKEN в файле .env: токен должен быть указан после знака =.\n"
            "Не присылай токен в чат. После проверки повтори запуск выбранного режима."
        ) from None
    except TelegramUnauthorizedError:
        raise SystemExit(
            "Telegram не принял токен\n\n"
            "Проверь токен в .env по данным BotFather и повтори запуск выбранного режима.\n"
            "Не присылай токен в чат."
        ) from None
    except TelegramConflictError:
        raise SystemExit(
            "Не удалось запустить получение сообщений\n\n"
            "Этот бот уже запущен в другом окне или подключён через webhook.\n"
            "Не запускай ещё одну копию. Перед остановкой прежнего запуска учти: "
            "его временный прогресс исчезнет. Если причина непонятна, попроси помочь."
        ) from None
    except TelegramNetworkError:
        raise SystemExit(
            "Не удалось подключиться к Telegram\n\n"
            "Проверь интернет и повтори запуск выбранного режима."
        ) from None
    except KeyboardInterrupt:
        pass
