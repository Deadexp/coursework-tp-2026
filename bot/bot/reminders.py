"""Telegram delivery worker. The backend owns settings, dates, leases and retries."""

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

from bot.api_client import BackendClient, BackendError, ReminderClaim

log = logging.getLogger(__name__)
REMINDER_TEXT = (
    "⏰ Время для английского!\n\n"
    "Открой /daily для короткой практики или /review для повторения слов.\n"
    "Изменить время или выключить напоминания: /reminders."
)


@dataclass
class Receipt:
    claim: ReminderClaim
    outcome: str
    retry_after_seconds: int = 0
    telegram_message_id: int | None = None


class ReminderScheduler:
    def __init__(self, bot: Bot, backend: BackendClient, poll_seconds: float = 45) -> None:
        self.bot = bot
        self.backend = backend
        self.poll_seconds = poll_seconds
        # Keep successful send receipts until acknowledged; never repeat send just because
        # the acknowledgement failed. A process crash still has an unavoidable ambiguity.
        self.receipts: dict[int, Receipt] = {}

    async def acknowledge(self, receipt: Receipt) -> None:
        try:
            await self.backend.acknowledge_reminder(
                receipt.claim,
                receipt.outcome,
                retry_after_seconds=receipt.retry_after_seconds,
                telegram_message_id=receipt.telegram_message_id,
            )
        except BackendError as error:
            if error.status not in (404, 409):
                raise
            log.warning(
                "Подтверждение напоминания устарело; повторной отправки этим процессом нет."
            )
        self.receipts.pop(receipt.claim.delivery_id, None)

    async def tick(self) -> bool:
        """Return False on a Telegram connectivity/rate failure to back off globally."""
        for receipt in list(self.receipts.values()):
            await self.acknowledge(receipt)
        for _ in range(10):
            claims = await self.backend.claim_reminders(limit=1)
            if not claims:
                return True
            # One lease immediately before send keeps the disable/send race very short.
            claim = claims[0]
            healthy = True
            try:
                result = await self.bot.send_message(
                    claim.telegram_id, REMINDER_TEXT, request_timeout=20
                )
                receipt = Receipt(claim, "sent", telegram_message_id=result.message_id)
            except TelegramForbiddenError:
                receipt = Receipt(claim, "forbidden")
                log.info("Напоминания отключаются: Telegram запретил доставку получателю.")
            except TelegramRetryAfter as error:
                receipt = Receipt(claim, "retry", retry_after_seconds=min(3600, error.retry_after))
                healthy = False
                log.warning("Telegram ограничил частоту напоминаний; следующая попытка отложена.")
            except (TelegramNetworkError, TelegramServerError):
                receipt = Receipt(claim, "retry")
                healthy = False
                log.warning("Telegram временно недоступен; напоминание отложено.")
            except TelegramUnauthorizedError:
                receipt = Receipt(claim, "retry")
                healthy = False
                log.error("Telegram не принял настройки бота; проверьте их локально.")
            except TelegramBadRequest:
                receipt = Receipt(claim, "failed")
                log.warning("Telegram отклонил напоминание; повторов сегодня не будет.")
            self.receipts[claim.delivery_id] = receipt
            await self.acknowledge(receipt)
            if not healthy:
                return False
        return True

    async def run(self) -> None:
        failures = 0
        while True:
            try:
                healthy = await self.tick()
                failures = 0 if healthy else min(failures + 1, 4)
            except BackendError as error:
                failures = min(failures + 1, 4)
                log.warning("API напоминаний недоступен (статус %s); повтор отложен.", error.status)
            except Exception as error:  # noqa: BLE001 - keep the worker alive; log no request data
                failures = min(failures + 1, 4)
                # Exception messages/tracebacks can contain a request URL with a bot token.
                log.error("Ошибка worker напоминаний: %s; повтор отложен.", type(error).__name__)
            await asyncio.sleep(min(300, self.poll_seconds * 2**failures))
