import asyncio
import json
import logging
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import test_connected as connected
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage

from bot.api_client import BackendClient, BackendError, ReminderClaim
from bot.reminders import ReminderScheduler
from bot.runtime import SafeFormatter, prepare_telegram, run_polling


class ReminderUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = connected.ConnectedTests.asyncSetUp
    asyncTearDown = connected.ConnectedTests.asyncTearDown
    send = connected.ConnectedTests.send
    click = connected.ConnectedTests.click
    button = connected.ConnectedTests.button
    practice_snapshot = connected.ConnectedTests.practice_snapshot

    def respond(self, request):
        if request.url.path != "/reminders/settings":
            return connected.ConnectedTests.respond(self, request)
        self.calls.append(request)
        if not self.linked:
            return httpx.Response(403, json={})
        if not hasattr(self, "reminder"):
            self.reminder = {"enabled": False, "time": "19:00", "timezone": "Europe/Moscow"}
        if request.method == "PATCH":
            data = json.loads(request.content)
            if data.get("timezone") == "Not/AZone":
                return httpx.Response(422, json={})
            self.reminder.update(data)
        return httpx.Response(200, json=self.reminder)

    async def test_opt_in_time_timezone_and_disabled_state_are_server_backed(self):
        shown = await self.send("/reminders")
        self.assertIn("выключены", shown.text)
        shown = await self.click(shown, self.button(shown, "reminder"))
        self.assertTrue(self.reminder["enabled"])
        edit = next(
            b.callback_data
            for row in shown.reply_markup.inline_keyboard
            for b in row
            if b.callback_data.endswith(":edit")
        )
        await self.click(shown, edit)
        self.assertIn("00:00", (await self.send("25:99")).text)
        await self.send("20:35")
        self.assertIn("не найден", (await self.send("Not/AZone")).text)
        shown = await self.send("Asia/Tokyo")
        self.assertEqual(self.reminder["time"], "20:35")
        self.assertEqual(self.reminder["timezone"], "Asia/Tokyo")
        self.assertTrue(self.reminder["enabled"])
        await self.click(shown, self.button(shown, "reminder"))
        self.assertFalse(self.reminder["enabled"])
        self.assertTrue(
            all(r.headers["X-Telegram-ID"] == str(connected.SENDER) for r in self.calls)
        )

    async def test_unlinked_cancel_and_foreign_callbacks(self):
        self.linked = False
        self.assertIn("ещё не подключён", (await self.send("/reminders")).text)
        self.linked = True
        shown = await self.send("/reminders")
        data = self.button(shown, "reminder")
        await self.click(shown, data, user_id=connected.SENDER + 1)
        self.assertFalse(self.reminder["enabled"])
        await self.send("/stop")
        await self.click(shown, data)
        self.assertFalse(self.reminder["enabled"])


def synthetic_claim():
    return ReminderClaim(
        delivery_id=42,
        claim_token=uuid4(),
        telegram_id=9000000001,
        local_date=datetime.now(UTC).date(),
        scheduled_at=datetime.now(UTC),
    )


class ReminderApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_uses_only_service_auth_and_settings_include_verified_sender(self):
        claim = synthetic_claim()
        requests = []

        def respond(request):
            requests.append(request)
            if request.url.path == "/reminders/settings":
                return httpx.Response(
                    200, json={"enabled": False, "time": "19:00", "timezone": "Europe/Moscow"}
                )
            if request.url.path == "/reminders/claims":
                return httpx.Response(200, json=[claim.model_dump(mode="json")])
            return httpx.Response(200, json={"status": "sent"})

        async with httpx.AsyncClient(
            base_url="http://backend.test", transport=httpx.MockTransport(respond)
        ) as http:
            backend = BackendClient("http://backend.test", "synthetic-service", http=http)
            await backend.reminder_settings(9000000001)
            leased = await backend.claim_reminders()
            await backend.acknowledge_reminder(leased[0], "sent", telegram_message_id=7)
        self.assertEqual(requests[0].headers["X-Telegram-ID"], "9000000001")
        for request in requests[1:]:
            self.assertEqual(request.headers["X-Service-Token"], "synthetic-service")
            self.assertNotIn("X-Telegram-ID", request.headers)
            self.assertNotIn("Authorization", request.headers)
        self.assertEqual(json.loads(requests[-1].content)["claim_token"], str(claim.claim_token))


class ReminderWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = SimpleNamespace(
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=7))
        )
        self.backend = SimpleNamespace(
            claim_reminders=AsyncMock(side_effect=[[synthetic_claim()], []]),
            acknowledge_reminder=AsyncMock(),
        )
        self.worker = ReminderScheduler(self.bot, self.backend)
        self.method = SendMessage(chat_id=1, text="synthetic test")

    async def test_successful_send_is_not_repeated_after_ack_connection_failure(self):
        self.backend.acknowledge_reminder.side_effect = [BackendError(0), None]
        with self.assertRaises(BackendError):
            await self.worker.tick()
        self.assertEqual(len(self.worker.receipts), 1)
        self.assertTrue(await self.worker.tick())
        self.assertEqual(self.bot.send_message.await_count, 1)
        self.assertEqual(self.backend.acknowledge_reminder.await_count, 2)
        self.assertEqual(self.worker.receipts, {})

    async def test_forbidden_requests_server_side_opt_out(self):
        self.bot.send_message.side_effect = TelegramForbiddenError(self.method, "synthetic blocked")
        self.assertTrue(await self.worker.tick())
        self.assertEqual(self.backend.acknowledge_reminder.await_args.args[1], "forbidden")

    async def test_network_and_rate_limit_do_not_send_immediate_retries(self):
        for error in (
            TelegramNetworkError(self.method, "private-request-details"),
            TelegramRetryAfter(self.method, "rate limit", retry_after=120),
        ):
            with self.subTest(error=type(error).__name__):
                claim = synthetic_claim()
                self.backend.claim_reminders = AsyncMock(return_value=[claim])
                self.bot.send_message = AsyncMock(side_effect=error)
                self.assertFalse(await self.worker.tick())
                self.assertEqual(self.bot.send_message.await_count, 1)
                self.assertEqual(self.backend.claim_reminders.await_count, 1)
                self.assertEqual(self.backend.acknowledge_reminder.await_args.args[1], "retry")

    async def test_scheduler_can_be_cancelled_without_delivering(self):
        self.backend.claim_reminders = AsyncMock(return_value=[])
        task = asyncio.create_task(self.worker.run())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.bot.send_message.assert_not_awaited()


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_network_startup_retries_with_bounded_backoff(self):
        method = SendMessage(chat_id=1, text="synthetic")
        bot = SimpleNamespace(
            get_me=AsyncMock(
                side_effect=[TelegramNetworkError(method, "private-token")] * 6
                + [SimpleNamespace(username="test_bot")]
            ),
            set_my_commands=AsyncMock(),
        )
        sleep = AsyncMock()
        with self.assertLogs("bot.runtime", level="INFO") as logs:
            await prepare_telegram(bot, [], sleep=sleep)
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [5, 10, 20, 40, 60, 60])
        self.assertNotIn("private-token", " ".join(logs.output))
        bot.set_my_commands.assert_awaited_once()

    async def test_polling_shutdown_cancels_reminder_task(self):
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def worker():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def polling(*args, **kwargs):
            await started.wait()

        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="test_bot")),
            set_my_commands=AsyncMock(),
        )
        with patch("bot.runtime.ReminderScheduler") as scheduler:
            scheduler.return_value.run = worker
            await run_polling(SimpleNamespace(start_polling=polling), bot, [], object())
        self.assertTrue(cancelled.is_set())

    def test_formatter_redacts_secrets_in_messages_and_tracebacks(self):
        secret = "123456:synthetic_private_token"
        try:
            raise ValueError("request URL /bot" + secret)
        except ValueError:
            import sys

            record = logging.LogRecord(
                "test", logging.ERROR, "", 0, "secret %s", (secret,), sys.exc_info()
            )
        text = SafeFormatter(secret).format(record)
        self.assertNotIn(secret, text)
        self.assertIn("[redacted]", text)
