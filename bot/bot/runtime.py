"""Retry transient Telegram startup failures and shut background workers down cleanly."""

import asyncio
import logging
from contextlib import suppress
from urllib.parse import quote

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.types import BotCommand

from bot.api_client import BackendClient
from bot.reminders import ReminderScheduler

log = logging.getLogger(__name__)


class SafeFormatter(logging.Formatter):
    def __init__(self, *secrets: str) -> None:
        super().__init__("%(levelname)s:%(name)s:%(message)s")
        self.secrets = tuple(
            variant for value in secrets if value for variant in (value, quote(value, safe=""))
        )

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)
        for secret in self.secrets:
            result = result.replace(secret, "[redacted]")
        return result


def configure_logging(bot_token: str, service_token: str) -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(SafeFormatter(bot_token, service_token))


async def prepare_telegram(bot: Bot, commands: list[BotCommand], *, sleep=asyncio.sleep) -> None:
    delay = 5
    while True:
        try:
            identity = await bot.get_me(request_timeout=15)
            await bot.set_my_commands(commands, request_timeout=15)
        except TelegramRetryAfter as error:
            wait = min(300, max(5, error.retry_after))
            log.warning("Telegram ограничил запросы при запуске; повтор через %s с.", wait)
            await sleep(wait)
        except (TelegramNetworkError, TelegramServerError):
            log.warning(
                "Telegram пока недоступен. Повтор через %s с; остановка — Ctrl+C. "
                "Это не подтверждает ошибку токена.",
                delay,
            )
            await sleep(delay)
            delay = min(60, delay * 2)
        else:
            log.info("Подключён Telegram-бот @%s; начинаем получение сообщений.", identity.username)
            return


async def run_polling(
    dispatcher: Dispatcher,
    bot: Bot,
    commands: list[BotCommand],
    backend: BackendClient | None = None,
    *,
    sleep=asyncio.sleep,
) -> None:
    await prepare_telegram(bot, commands, sleep=sleep)
    worker = (
        asyncio.create_task(ReminderScheduler(bot, backend).run(), name="telegram-reminders")
        if backend is not None
        else None
    )
    delay = 5
    try:
        while True:
            try:
                # The outer Bot context owns its session, including across startup retries.
                await dispatcher.start_polling(bot, close_bot_session=False)
                break
            except (TelegramNetworkError, TelegramServerError):
                log.warning("Получение сообщений временно недоступно; повтор через %s с.", delay)
                await sleep(delay)
                delay = min(60, delay * 2)
    finally:
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
