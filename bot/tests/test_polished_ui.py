"""Check visible screens and cleanup boundaries with simulated Telegram and backend."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import test_connected as connected
import test_grammar_ui as grammar
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.methods import DeleteMessage, SendMessage

from bot.chat_ui import ChatView
from bot.connected_handlers import MENU
from bot.main import CONNECTED_COMMANDS

SENDER = connected.SENDER


class PolishedUITests(unittest.IsolatedAsyncioTestCase):
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

    def visible(self, user_id=SENDER):
        return [
            m
            for m in self.session.sent
            if m.chat.id == user_id and (user_id, m.message_id) not in self.session.deleted
        ]

    async def test_main_buttons_and_published_commands(self):
        self.assertEqual(
            [[b.text for b in row] for row in MENU.keyboard],
            [
                ["📖 Словарь", "📝 Мини-тест"],
                ["📊 Статистика"],
                ["💬 Разговор на английском"],
                ["🏠 Главное меню", "❓ Помощь"],
            ],
        )
        self.assertEqual(
            [command for command, _ in CONNECTED_COMMANDS],
            ["start", "dictionary", "quiz", "talk", "stats", "help"],
        )
        home = await self.send("/start")
        self.assertNotIn("подключённый режим", home.text)
        self.assertNotIn("практику дня", home.text)
        dictionary = await self.send("📖 Словарь")
        self.assertIn("shared", dictionary.text)
        quiz = await self.send("📝 Мини-тест")
        self.assertIn("Мини-тест", quiz.text)
        statistics = await self.send("📊 Статистика")
        self.assertIn("📊 Статистика", statistics.text)
        help_message = await self.send("❓ Помощь")
        self.assertIn("❓ Помощь", help_message.text)
        self.assertNotIn((SENDER, quiz.message_id), self.session.deleted)
        talk = await self.send("💬 Разговор на английском")
        self.assertIn("Выбери сценарий", talk.text)
        self.assertEqual(self.calls[-1].url.path, "/dialogs/scenarios")
        home = await self.send("🏠 Главное меню")
        self.assertIn("Привет, Learner!", home.text)
        self.assertEqual(len(self.visible()), 1)

    async def test_dictionary_contains_management_and_card_submenu(self):
        page = await self.send("📖 Словарь")
        labels = [b.text for row in page.reply_markup.inline_keyboard for b in row]
        self.assertIn("➕ Добавить", labels)
        self.assertIn("🗑 Удалить", labels)
        self.assertIn("📚 Карточки слов", labels)
        card = await self.click(page, self.button(page, "review"))
        self.assertIn("Карточка", card.text)
        page = await self.click(card, self.button(card, "back"))
        self.assertIn("📖 Словарь", page.text)
        await self.click(page, self.button(page, "add"))
        await self.send("bridge")
        confirm = await self.send("мост")
        page = await self.click(confirm, self.button(confirm, "save"))
        self.assertIn("Слово добавлено", page.text)
        self.assertTrue(
            {card.message_id, confirm.message_id, page.message_id}.issubset(
                {m.message_id for m in self.visible()}
            )
        )

    async def test_difficult_words_open_inside_quiz_and_back_returns_to_quiz(self):
        quiz = await self.send("📝 Мини-тест")
        card = await self.click(quiz, self.button(quiz, "gdifficult"))
        self.assertIn("Карточка", card.text)
        self.assertEqual(self.calls[-1].url.path, "/vocabulary/problem-words")
        quiz = await self.click(card, self.button(card, "back"))
        self.assertIn("Мини-тест", quiz.text)
        self.assertIn("gdifficult", self.button(quiz, "gdifficult"))
        self.assertIn(card.message_id, {m.message_id for m in self.visible()})

    async def test_navigation_removes_previous_bot_screen_and_handled_input(self):
        home = await self.send("/start")
        page = await self.send("📖 Словарь")
        stats = await self.send("📊 Статистика")
        self.assertIn((SENDER, home.message_id), self.session.deleted)
        self.assertIn((SENDER, page.message_id), self.session.deleted)
        self.assertEqual([m.message_id for m in self.visible()], [stats.message_id])
        for input_id in (1, 2, 3):
            self.assertIn((SENDER, input_id), self.session.deleted)

    async def test_arbitrary_text_and_other_chat_history_are_not_deleted(self):
        await self.send("Личная заметка")
        self.assertNotIn((SENDER, 1), self.session.deleted)
        other_page = await self.send("📖 Словарь", user_id=SENDER + 1)
        await self.send("/dictionary")
        await self.send("/stats")
        self.assertNotIn((SENDER + 1, other_page.message_id), self.session.deleted)
        self.assertEqual([m.message_id for m in self.visible(SENDER + 1)], [other_page.message_id])

    async def test_help_and_statistics_preserve_exercise_and_replace_only_notice(self):
        question = await self.begin()
        help_message = await self.send("/help")
        self.assertNotIn((SENDER, question.message_id), self.session.deleted)
        stats = await self.send("/stats")
        self.assertIn((SENDER, help_message.message_id), self.session.deleted)
        self.assertEqual(len(self.visible()), 2)
        self.assertNotIn("Последняя практика", stats.text)
        self.assertNotIn("Уровень:", stats.text)
        feedback = await self.click(question, self.button(question, "gchoice"))
        self.assertIn("Верно", feedback.text)
        self.assertEqual(
            {m.message_id for m in self.visible()}, {question.message_id, feedback.message_id}
        )
        self.assertEqual(len(self.answers()), 1)

    async def test_validation_and_unknown_command_do_not_remove_answer_controls(self):
        question = await self.begin()
        await self.send("a")
        await self.send("/unknown")
        self.assertNotIn((SENDER, question.message_id), self.session.deleted)
        self.assertEqual(len(self.visible()), 2)
        self.assertEqual(self.answers(), [])
        feedback = await self.click(question, self.button(question, "gchoice"))
        self.assertIn("Верно", feedback.text)
        await self.send("Повторный ответ")
        self.assertNotIn((SENDER, feedback.message_id), self.session.deleted)
        next_question = await self.click(feedback, self.button(feedback, "gnext"))
        self.assertIn("Вопрос 2", next_question.text)
        self.assertEqual(
            {m.message_id for m in self.visible()},
            {question.message_id, feedback.message_id, next_question.message_id},
        )

    async def test_cleanup_failures_do_not_break_navigation_or_record_answers_twice(self):
        method = DeleteMessage(chat_id=SENDER, message_id=1)
        for error in (
            TelegramBadRequest(method, "message cannot be deleted"),
            TelegramForbiddenError(method, "not permitted"),
            TelegramNetworkError(method, "network unavailable"),
        ):
            with self.subTest(error=type(error).__name__):
                self.session.delete_error = error
                await self.send("/dictionary")
                card = await self.send("/review")
                rate = await self.click(card, self.button(card, "reveal"))
                data = self.button(rate, "rate")
                before = len([r for r in self.calls if r.url.path.endswith("/reviews")])
                await self.click(rate, data)
                await self.click(rate, data)
                after = len([r for r in self.calls if r.url.path.endswith("/reviews")])
                self.assertEqual(after, before + 1)

    async def test_dictionary_delete_picker_and_cancel_never_delete_data(self):
        page = await self.send("/dictionary")
        picker = await self.click(page, self.button(page, "delete"))
        self.assertNotIn("История", picker.text)
        confirm = await self.click(picker, self.button(picker, "pickdelete"))
        self.assertIn("История повторений", confirm.text)
        page = await self.click(confirm, self.button(confirm, "cancel"))
        self.assertIn("📖 Словарь", page.text)
        self.assertFalse(any(r.method == "DELETE" for r in self.calls))
        self.assertEqual(len(self.visible()), 1)

    async def test_card_feedback_is_combined_with_next_card_and_result(self):
        self.rows = [
            connected.WORD,
            dict(connected.WORD, id=43, text="bridge", translation="мост"),
        ]
        card = await self.send("/review")
        for word in ("shared", "bridge"):
            rating = await self.click(card, self.button(card, "reveal"))
            card = await self.click(rating, self.button(rating, "rate"))
            self.assertIn(f"✓ {word}", card.text)
            self.assertIn("02.01.2030", card.text)
            self.assertNotIn("SM-2", card.text)
            self.assertNotIn("источник:", card.text)
            self.assertNotIn((SENDER, rating.message_id), self.session.deleted)
        self.assertIn("Карточек пройдено: 2", card.text)

    async def test_word_quiz_feedback_remains_visible_in_result(self):
        quiz = await self.send("/quiz")
        card = await self.click(quiz, self.button(quiz, "gwords"))
        result = await self.click(card, self.button(card, "pchoice"))
        self.assertIn("Верно", result.text)
        self.assertIn("shared — общий", result.text)
        self.assertIn("Правильных ответов: 1 из 1", result.text)
        self.assertEqual(
            {m.message_id for m in self.visible()}, {card.message_id, result.message_id}
        )

    async def test_old_submenu_cannot_start_a_quiz_or_delete_data(self):
        quiz = await self.send("/quiz")
        await self.send("/dictionary")
        before = len(self.calls)
        await self.click(quiz, self.button(quiz, "gwords"))
        await self.click(quiz, self.button(quiz, "gdifficult"))
        self.assertEqual(len(self.calls), before)
        self.assertIn("устарела", self.session.answers[-1])

    async def test_groups_never_trigger_cleanup(self):
        await self.send("/dictionary", chat_type="group")
        self.assertEqual(self.session.deleted, [])
        self.assertEqual(self.session.sent, [])


class ChatViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_failure_keeps_previous_screen_and_does_not_delete_it(self):
        view = ChatView()
        message = SimpleNamespace(
            chat=SimpleNamespace(id=1),
            bot=SimpleNamespace(delete_message=AsyncMock()),
            answer=AsyncMock(return_value=SimpleNamespace(message_id=10)),
        )
        await view.show(message, "Previous screen")
        message.answer.side_effect = TelegramNetworkError(
            SendMessage(chat_id=1, text="Next screen"), "unavailable"
        )
        with self.assertRaises(TelegramNetworkError):
            await view.show(message, "Next screen")
        self.assertEqual(view.screens[1], 10)
        message.bot.delete_message.assert_not_awaited()
