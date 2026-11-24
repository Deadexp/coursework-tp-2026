import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import test_connected as connected
import test_grammar_ui as grammar
from aiogram import Bot
from aiogram.types import Chat, Message, PhotoSize, Update, User

SENDER = connected.SENDER


class HistoryImageTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = connected.ConnectedTests.asyncSetUp
    asyncTearDown = connected.ConnectedTests.asyncTearDown
    send = connected.ConnectedTests.send
    click = connected.ConnectedTests.click
    button = connected.ConnectedTests.button
    practice_snapshot = connected.ConnectedTests.practice_snapshot
    respond = grammar.GrammarUITests.respond
    snapshot = grammar.GrammarUITests.snapshot
    answers = grammar.GrammarUITests.answers
    begin = grammar.GrammarUITests.begin

    async def test_question_answer_error_and_result_survive_menu_navigation(self):
        question = await self.begin()
        feedback = await self.click(
            question, self.button(question, "gchoice").rsplit(":", 1)[0] + ":1"
        )
        self.assertIn("Вопрос: Choose an article", feedback.text)
        self.assertIn("Твой ответ: the", feedback.text)
        self.assertIn("Правильный ответ: a", feedback.text)
        self.assertIn("Existing course explanation", feedback.text)
        next_question = await self.click(feedback, self.button(feedback, "gnext"))
        input_id = self.sequence + 1
        last_feedback = await self.send("wrong")
        result = await self.click(last_feedback, self.button(last_feedback, "gnext"))
        await self.send("🏠 Главное меню")
        for message in (question, feedback, next_question, last_feedback, result):
            self.assertNotIn((SENDER, message.message_id), self.session.deleted)
        self.assertNotIn((SENDER, input_id), self.session.deleted)
        self.assertIn((SENDER, question.message_id), self.session.cleared)

    async def test_cards_request_unscheduled_words_every_time(self):
        await self.send("/review")
        first = [r for r in self.calls if r.url.path == "/vocabulary/review"][-1]
        self.assertEqual(first.url.params["include_future"], "true")
        await self.send("/review")
        self.assertEqual(len([r for r in self.calls if r.url.path == "/vocabulary/review"]), 2)

    async def test_card_with_shared_image_uses_authenticated_backend(self):
        self.rows = [dict(connected.WORD, image_url="/images/vocabulary/apple.svg")]
        card = await self.send("/review")
        request = next(r for r in self.calls if r.url.path == "/vocabulary/42/image")
        self.assertEqual(request.headers["X-Telegram-ID"], str(SENDER))
        self.assertIn("shared", card.text)

    async def test_add_word_with_photo_requires_confirmation_and_keeps_input(self):
        await self.send("/addword")
        word_input = self.sequence + 1
        await self.send("bridge")
        confirm = await self.send("мост")
        await self.click(confirm, self.button(confirm, "picture"))
        self.sequence += 1
        photo_input = self.sequence
        message = Message(
            message_id=photo_input,
            date=datetime.now(UTC),
            from_user=User(id=SENDER, is_bot=False, first_name="Learner"),
            chat=Chat(id=SENDER, type="private"),
            photo=[
                PhotoSize(
                    file_id="synthetic-photo",
                    file_unique_id="synthetic",
                    width=100,
                    height=100,
                    file_size=20,
                )
            ],
        )

        async def download(bot, file, destination, **kwargs):
            destination.write(b"synthetic-photo-bytes")
            return destination

        with patch.object(Bot, "download", download):
            await self.dp.feed_update(self.bot, Update(update_id=self.sequence, message=message))
        confirm = self.session.sent[-1]
        self.assertFalse(any(r.method == "POST" for r in self.calls))
        self.assertNotIn((SENDER, word_input), self.session.deleted)
        self.assertNotIn((SENDER, photo_input), self.session.deleted)
        saved = await self.click(confirm, self.button(confirm, "save"))
        upload = next(r for r in self.calls if r.method == "PUT")
        self.assertEqual(upload.url.path, "/vocabulary/42/image")
        self.assertEqual(upload.content, b"synthetic-photo-bytes")
        self.assertIn("Слово добавлено", saved.text)
        await self.click(confirm, self.button(confirm, "save"))
        self.assertEqual(len([r for r in self.calls if r.method == "PUT"]), 1)
