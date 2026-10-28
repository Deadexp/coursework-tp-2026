import asyncio
import json
import unittest
from datetime import UTC, datetime

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.api_client import BackendClient, BackendError
from bot.connected_handlers import make_connected_router

SENDER = 9000000001
WORD = {"id": 42, "text": "shared", "translation": "общий"}
DATE = "2030-01-02T12:00:00Z"


class FakeTelegram(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []
        self.answers = []

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetMe):
            return User(id=123456, is_bot=True, first_name="Test", username="test_bot")
        if isinstance(method, SendMessage):
            result = Message(
                message_id=len(self.sent) + 1,
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
                reply_markup=method.reply_markup
                if getattr(method.reply_markup, "inline_keyboard", None)
                else None,
            )
            self.sent.append(result)
            return result
        if isinstance(method, AnswerCallbackQuery):
            self.answers.append(method.text or "")
            return True
        raise AssertionError(type(method).__name__)


class ConnectedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.practice = None
        self.level = "A1"
        self.rows = [WORD]
        self.status = 200
        self.unavailable = False
        self.linked = True
        self.http = httpx.AsyncClient(
            base_url="http://backend.test",
            transport=httpx.MockTransport(self.respond),
        )
        self.client = BackendClient(
            "http://backend.test", "test-service-" + "x" * 40, http=self.http
        )
        self.session = FakeTelegram()
        self.bot = Bot("123456:synthetic_connected_test_token", session=self.session)
        self.dp = Dispatcher(events_isolation=SimpleEventIsolation())
        self.dp.include_router(make_connected_router(self.client, "http://site.test"))
        self.sequence = 0

    async def asyncTearDown(self):
        await self.http.aclose()
        await self.bot.session.close()
        await self.dp.storage.close()
        await self.dp.fsm.events_isolation.close()

    def respond(self, request):
        self.calls.append(request)
        if self.unavailable:
            raise httpx.ConnectError("private connection details", request=request)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "private internal details"})
        path = request.url.path
        if path == "/telegram/link":
            self.linked = True
            return httpx.Response(200, json={"display_name": "Learner"})
        if not self.linked:
            return httpx.Response(403, json={})

        if path == "/practice/level":
            if request.method == "PATCH":
                self.level = json.loads(request.content)["level"]
            return httpx.Response(200, json={"level": self.level})
        if path == "/practice/progress":
            return httpx.Response(
                200,
                json={
                    "level": self.level,
                    "words": len(self.rows),
                    "due": len(self.rows),
                    "reviews": 0,
                    "attempted": 0,
                    "correct": 0,
                    "quizzes_completed": 0,
                    "daily_completed": 0,
                },
            )
        if path == "/practice/sessions":
            mode = json.loads(request.content)["mode"]
            if not self.rows:
                return httpx.Response(412, json={})
            if self.practice is None or self.practice[0] != mode:
                self.practice = (mode, 0, False)
            return httpx.Response(200, json=self.practice_snapshot())
        if path.endswith("/reveal"):
            mode, position, _ = self.practice
            self.practice = (mode, position, True)
            return httpx.Response(200, json=self.practice_snapshot())
        if path.endswith("/answers"):
            mode, position, _ = self.practice
            data = json.loads(request.content)
            self.practice = (mode, position + 1, False)
            return httpx.Response(
                200,
                json={
                    "is_correct": None if "quality" in data else True,
                    "word": "shared",
                    "translation": "общий",
                    "next_review_at": DATE,
                    "state": self.practice_snapshot(),
                },
            )

        if path == "/telegram/me":
            return httpx.Response(200, json={"display_name": "Learner"})
        if path == "/vocabulary/page":
            page = int(request.url.params.get("page", 0))
            items = self.rows[page * 8 : (page + 1) * 8]
            return httpx.Response(
                200,
                json={
                    "items": [{"word": w, "next_review_at": DATE} for w in items],
                    "total": len(self.rows),
                    "page": page,
                    "page_size": 8,
                },
            )
        if path in ("/vocabulary/review", "/vocabulary/problem-words"):
            return httpx.Response(200, json=[{"word": w} for w in self.rows])
        if path.endswith("/reviews"):
            return httpx.Response(200, json={"next_review_at": DATE, "interval_days": 1})
        if request.method == "DELETE":
            self.rows = [w for w in self.rows if w["id"] != int(path.split("/")[-1])]
            return httpx.Response(204)
        if request.method == "POST" and path == "/vocabulary":
            return httpx.Response(201, json={})
        raise AssertionError((request.method, path))

    async def send(self, text, user_id=SENDER, chat_type="private"):
        self.sequence += 1
        message = Message(
            message_id=self.sequence,
            date=datetime.now(UTC),
            text=text,
            from_user=User(id=user_id, is_bot=False, first_name="Learner"),
            chat=Chat(id=user_id, type=chat_type),
        )
        await self.dp.feed_update(self.bot, Update(update_id=self.sequence, message=message))
        return self.session.sent[-1] if self.session.sent else None

    async def click(self, message, data, user_id=SENDER):
        self.sequence += 1
        query = CallbackQuery(
            id=str(self.sequence),
            from_user=User(id=user_id, is_bot=False, first_name="Learner"),
            chat_instance="test",
            message=message,
            data=data,
        )
        await self.dp.feed_update(self.bot, Update(update_id=self.sequence, callback_query=query))
        return self.session.sent[-1] if self.session.sent else None

    def button(self, message, prefix):
        return next(
            b.callback_data
            for row in message.reply_markup.inline_keyboard
            for b in row
            if b.callback_data.startswith(prefix + ":")
        )

    async def test_start_link_uses_actual_telegram_sender(self):
        self.linked = False
        await self.send("/start " + "a" * 43)
        call = next(r for r in self.calls if r.url.path == "/telegram/link")
        self.assertEqual(json.loads(call.content), {"code": "a" * 43, "telegram_id": SENDER})
        self.assertTrue(any("Telegram подключён" in m.text for m in self.session.sent))

    async def test_unlinked_account_gets_connection_instructions(self):
        self.linked = False
        reply = await self.send("/dictionary")
        self.assertIn("Подключить Telegram", reply.text)
        self.assertIn("http://site.test", reply.text)

    async def test_dictionary_reads_api_and_paginates(self):
        self.rows = [dict(WORD, id=i, text=f"word{i}") for i in range(10)]
        page = await self.send("📖 Мой словарь")
        self.assertIn("1 из 2", page.text)
        self.assertIn("word0", page.text)
        page = await self.click(page, self.button(page, "page"))
        self.assertIn("2 из 2", page.text)
        self.assertIn("word8", page.text)
        self.assertNotIn("word0", page.text)
        self.assertEqual(self.calls[-1].headers["X-Telegram-ID"], str(SENDER))

    async def test_empty_dictionary(self):
        self.rows = []
        self.assertIn("Пока пусто", (await self.send("/dictionary")).text)

    async def test_add_pair_only_after_confirmation_and_once(self):
        await self.send("/addword")
        self.assertIn("непустой", (await self.send("   ")).text)
        await self.send("bridge")
        await self.send("/help")
        confirm = await self.send("мост")
        self.assertFalse(any(r.method == "POST" for r in self.calls))
        data = self.button(confirm, "save")
        await asyncio.gather(self.click(confirm, data), self.click(confirm, data))
        requests = [r for r in self.calls if r.method == "POST"]
        self.assertEqual(len(requests), 1)
        self.assertEqual(json.loads(requests[0].content), {"text": "bridge", "translation": "мост"})

    async def test_cancel_and_menu_are_not_translation_answers(self):
        await self.send("/addword")
        await self.send("bridge")
        await self.send("/cancel")
        await self.send("мост")
        await self.send("/addword")
        await self.send("bridge")
        await self.send("📖 Мой словарь")
        await self.send("мост")
        self.assertFalse(any(r.method == "POST" for r in self.calls))

    async def test_delete_requires_confirmation_and_preserves_other_users(self):
        page = await self.send("/dictionary")
        confirm = await self.click(page, self.button(page, "delete"))
        self.assertFalse(any(r.method == "DELETE" for r in self.calls))
        await self.click(confirm, self.button(confirm, "remove"), user_id=SENDER + 1)
        self.assertFalse(any(r.method == "DELETE" for r in self.calls))
        await self.click(confirm, self.button(confirm, "remove"))
        calls = [r for r in self.calls if r.method == "DELETE"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url.path, "/vocabulary/42")

    async def test_stale_delete_button_does_not_delete(self):
        page = await self.send("/dictionary")
        await self.send("/addword")
        await self.click(page, self.button(page, "delete"))
        self.assertFalse(any(r.method == "DELETE" for r in self.calls))

    async def test_review_uses_server_date_and_source_bot_once(self):
        card = await self.send("/review")
        rating = await self.click(card, self.button(card, "reveal"))
        data = self.button(rating, "rate")
        await self.click(rating, data)
        await self.click(rating, data)
        calls = [r for r in self.calls if r.url.path.endswith("/reviews")]
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(calls[0].content), {"quality": 1, "source": "bot"})
        self.assertTrue(any("02.01.2030" in m.text for m in self.session.sent))

    async def test_difficult_words_are_requested_from_api(self):
        await self.send("/difficult")
        self.assertEqual(self.calls[-1].url.path, "/vocabulary/problem-words")

    async def test_server_unavailable_has_no_demo_fallback(self):
        self.unavailable = True
        reply = await self.send("/dictionary")
        self.assertIn("Сервер недоступен", reply.text)
        self.assertNotIn("private", reply.text)
        self.assertNotIn("apple", reply.text)

    async def test_duplicate_word_is_reported_without_leaking_backend(self):
        await self.send("/addword")
        await self.send("bridge")
        confirm = await self.send("мост")
        self.status = 409
        reply = await self.click(confirm, self.button(confirm, "save"))
        self.assertIn("уже существует", reply.text)
        self.assertNotIn("private", reply.text)

    async def test_talk_is_explicitly_unavailable(self):
        reply = await self.send("/talk")
        self.assertIn("LLM", reply.text)
        self.assertEqual(self.calls, [])

    async def test_groups_are_ignored(self):
        await self.send("/dictionary", chat_type="group")
        self.assertEqual(self.calls, [])

    async def test_client_handles_bad_json_and_http_auth_errors(self):
        async with httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, text="bad json")),
        ) as http:
            client = BackendClient("http://test", "test", http=http)
            with self.assertRaises(BackendError) as raised:
                await client.dictionary(SENDER)
            self.assertEqual(raised.exception.status, 502)
        self.status = 401
        with self.assertRaises(BackendError) as raised:
            await self.client.dictionary(SENDER)
        self.assertEqual(raised.exception.status, 401)

    def practice_snapshot(self):
        mode, position, revealed = self.practice
        daily = mode == "daily"
        total = 2 if daily else 1
        finished = position >= total
        question = None
        if not finished:
            kind = "card" if daily and position == 0 else "recall" if daily else "choice"
            question = {
                "position": position,
                "kind": kind,
                "prompt": "Напиши по-английски: общий" if kind == "recall" else "shared",
                "choices": ["общий", "другой"] if kind == "choice" else [],
                "revealed": revealed,
                "translation": "общий" if revealed else None,
            }
        return {
            "session_id": 101,
            "mode": mode,
            "completed": finished,
            "total": total,
            "answered": position,
            "cards_reviewed": int(daily and position > 0),
            "attempted": max(0, position - 1) if daily else position,
            "correct": max(0, position - 1) if daily else position,
            "question": question,
        }

    async def test_quiz_button_answers_and_duplicate_callback(self):
        card = await self.send("/wordquiz")
        data = self.button(card, "pchoice")
        await asyncio.gather(self.click(card, data), self.click(card, data))
        answers = [r for r in self.calls if r.url.path.endswith("/answers")]
        self.assertEqual(len(answers), 1)
        self.assertIn("Мини-тест завершён", self.session.sent[-1].text)

    async def test_daily_reveal_rate_text_and_progress_do_not_interrupt(self):
        card = await self.send("/daily")
        rate = await self.click(card, self.button(card, "preveal"))
        question = await self.click(rate, self.button(rate, "prate"))
        self.assertIn("Напиши", question.text)
        await self.send("/progress")
        await self.send("/help")
        await self.send("/unknown")
        self.assertEqual(len([r for r in self.calls if r.url.path.endswith("/answers")]), 1)
        final = await self.send("shared")
        self.assertIn("Практика дня выполнена", final.text)
        self.assertIn("Правильных ответов: 1 из 1", final.text)
        self.assertIn("Карточек пройдено: 1", final.text)

    async def test_level_is_shared_and_old_or_foreign_buttons_rejected(self):
        choice = await self.send("🎚 Уровень")
        data = self.button(choice, "plevel").rsplit(":", 1)[0] + ":B2"
        await self.click(choice, data, user_id=SENDER + 1)
        self.assertEqual(self.level, "A1")
        await self.click(choice, data)
        self.assertEqual(self.level, "B2")
        await self.click(choice, data)
        self.assertEqual(len([r for r in self.calls if r.method == "PATCH"]), 1)

    async def test_stop_reopens_persistent_daily_without_scoring_messages(self):
        card = await self.send("/daily")
        await self.send("/stop")
        await self.click(card, self.button(card, "preveal"))
        self.assertFalse(any(r.url.path.endswith("/reveal") for r in self.calls))
        await self.send("shared")
        self.assertFalse(any(r.url.path.endswith("/answers") for r in self.calls))
        reopened = await self.send("/daily")
        self.assertIn("1 из 2", reopened.text)

    async def test_practice_server_failure_never_falls_back_to_demo(self):
        self.unavailable = True
        reply = await self.send("/quiz")
        self.assertIn("Сервер недоступен", reply.text)
        self.assertNotIn("apple", reply.text)
