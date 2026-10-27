import asyncio
import unittest
from datetime import UTC, datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, EditMessageReplyMarkup, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.demo import GAP_EXERCISES, WORDS, DemoClient
from bot.demo_handlers import HELP, MENU, MENU_ROWS, RATINGS, make_demo_router


class DemoClientTests(unittest.TestCase):
    def test_gap_exercises_cover_dictionary_and_normalize_answers(self) -> None:
        self.assertEqual(set(GAP_EXERCISES), {w.id for w in WORDS})
        for word in WORDS:
            exercise = GAP_EXERCISES[word.id]
            with self.subTest(word=word.text):
                self.assertEqual(exercise.sentence.count("___"), 1)
                self.assertIn(word.text, exercise.completed_sentence)
                self.assertNotIn("___", exercise.completed_sentence)
                self.assertTrue(exercise.explanation)
                for text in (word.text, word.text.upper(), f"  {word.text}. \n",
                             f"\t{word.text.upper()}.\t"):
                    self.assertTrue(exercise.accepts(text), repr(text))
                for text in ("", " ", ".", "wrong", word.translation,
                             exercise.completed_sentence):
                    self.assertFalse(exercise.accepts(text), repr(text))

    def test_daily_prioritizes_difficult_then_due_words(self) -> None:
        client = DemoClient()
        # Make all words future-due, then add two problem words and one overdue word.
        for word in WORDS:
            client.rate(1, word, 5)
        client.rate(1, WORDS[7], 1)
        client.rate(1, WORDS[6], 1)
        client.rate(1, WORDS[6], 1)
        client.learner(1).words[WORDS[5].id].next_due = datetime.now(UTC) - timedelta(days=1)
        selected = client.daily_words(1)
        self.assertEqual(selected[:3], [WORDS[6], WORDS[7], WORDS[5]])
        self.assertEqual(len(set(selected)), 5)
        self.assertEqual(client.daily_words(2), list(WORDS[:5]))

    def test_reviews_schedule_and_due_filter(self) -> None:
        client = DemoClient()
        self.assertEqual(len(client.review_words(1)), 8)
        due = client.rate(1, WORDS[0], 1)
        self.assertLess(abs((due - datetime.now(UTC)).total_seconds() - 600), 2)
        self.assertNotIn(WORDS[0], client.review_words(1))
        self.assertIn(WORDS[0], client.review_words(1, difficult=True))
        client.learner(1).words[WORDS[0].id].next_due = datetime.now(UTC) - timedelta(seconds=1)
        self.assertIn(WORDS[0], client.review_words(1))
        with self.assertRaises(ValueError):
            client.rate(1, WORDS[0], 99)

    def test_users_are_isolated_and_quiz_choices_are_valid(self) -> None:
        client = DemoClient()
        client.record_answer(1, WORDS[0], False)
        self.assertEqual(client.learner(2).attempted, 0)
        self.assertEqual(client.review_words(2, difficult=True), [])
        self.assertEqual(client.quiz_words(1)[0], WORDS[0])
        self.assertEqual(len(client.daily_words(1)), 5)
        for word in WORDS:
            choices = client.choices(word)
            self.assertEqual(len(set(choices)), 4)
            self.assertEqual(choices.count(word.translation), 1)


class FakeTelegram(BaseSession):
    """Exercise real aiogram routing without Telegram credentials or network."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[Message] = []
        self.answers: list[str] = []
        self.requests = []

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, GetMe):
            return User(id=123456, is_bot=True, first_name="Demo", username="demo_test_bot")
        if isinstance(method, SendMessage):
            message = Message(
                message_id=len(self.sent) + 1,
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                from_user=User(id=123456, is_bot=True, first_name="Demo"),
                text=method.text,
                reply_markup=method.reply_markup
                if getattr(method.reply_markup, "inline_keyboard", None)
                else None,
            )
            self.sent.append(message)
            return message
        if isinstance(method, AnswerCallbackQuery):
            self.answers.append(method.text or "")
            return True
        if isinstance(method, EditMessageReplyMarkup):
            return True
        raise AssertionError(f"Unexpected network method: {type(method).__name__}")


class DemoConversationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = DemoClient()
        self.session = FakeTelegram()
        self.bot = Bot(token="123456:synthetic_demo_test_token", session=self.session)
        self.dp = Dispatcher(events_isolation=SimpleEventIsolation())
        self.dp.include_router(make_demo_router(self.client))
        self.update_id = 0

    async def asyncTearDown(self) -> None:
        await self.bot.session.close()
        await self.dp.storage.close()
        await self.dp.fsm.events_isolation.close()

    async def send(
        self, text: str | None, user_id: int = 1, chat_type: str = "private"
    ) -> Message | None:
        self.update_id += 1
        message = Message(
            message_id=self.update_id,
            date=datetime.now(UTC),
            chat=Chat(id=user_id, type=chat_type),
            from_user=User(id=user_id, is_bot=False, first_name="Learner"),
            text=text,
        )
        await self.dp.feed_update(self.bot, Update(update_id=self.update_id, message=message))
        return self.session.sent[-1] if self.session.sent else None

    async def click(self, message: Message, data: str, user_id: int = 1) -> Message:
        self.update_id += 1
        query = CallbackQuery(
            id=str(self.update_id),
            from_user=User(id=user_id, is_bot=False, first_name="Learner"),
            chat_instance="demo-test",
            message=message,
            data=data,
        )
        await self.dp.feed_update(self.bot, Update(update_id=self.update_id, callback_query=query))
        return self.session.sent[-1]

    async def rate_card(self, card: Message, quality: int = 4, user_id: int = 1) -> Message:
        reveal = card.reply_markup.inline_keyboard[0][0].callback_data
        rating = await self.click(card, reveal, user_id)
        button = next(
            b for row in rating.reply_markup.inline_keyboard for b in row
            if b.callback_data.endswith(f":{quality}")
        )
        return await self.click(rating, button.callback_data, user_id)

    async def reach_daily_gaps(self, user_id: int = 1) -> Message:
        card = await self.send("☀️ Практика дня", user_id)
        for i in range(3):
            self.assertIn(f"{i + 1} из 5", card.text)
            self.assertIn(f"Карточка {i + 1} из 3", card.text)
            card = await self.rate_card(card, user_id=user_id)
        self.assertIn("4 из 5", card.text)
        self.assertIn("Напиши пропущенное слово", card.text)
        self.assertIsNone(card.reply_markup)
        return card

    def gap_word(self, message: Message):
        return next(w for w in WORDS if GAP_EXERCISES[w.id].sentence in message.text)

    def quiz_word(self, message: Message):
        english = message.text.split("Выбери перевод: ")[1].splitlines()[0]
        return next(w for w in WORDS if w.text == english)

    async def test_start_and_buttons_route_without_site(self) -> None:
        reply = await self.send("/start")
        self.assertIn("8 слов", reply.text)
        reply = await self.send("Помощь")
        self.assertIn("/review", reply.text)
        await self.send("Поговорить на английском")
        self.assertIn("LLM пока не подключена", self.session.sent[-1].text)
        await self.send("/link")
        self.assertIn("ещё не подключена", self.session.sent[-1].text)
        await self.send("Hello!")
        self.assertIn("Свободная беседа пока недоступна", self.session.sent[-1].text)

    async def test_review_reveal_rate_and_duplicate_click(self) -> None:
        card = await self.send("/review")
        reveal = card.reply_markup.inline_keyboard[0][0].callback_data
        rating = await self.click(card, reveal)
        self.assertIn("apple — яблоко", rating.text)
        await self.click(card, reveal)
        self.assertEqual(self.client.learner(1).reviewed, 0)
        data = rating.reply_markup.inline_keyboard[0][0].callback_data
        await self.click(rating, data)
        self.assertEqual(self.client.learner(1).reviewed, 1)
        await self.click(rating, data)
        self.assertEqual(self.client.learner(1).reviewed, 1)
        self.assertIn("устарела", self.session.answers[-1])
        await self.send("Сложные слова")
        self.assertIn("apple", self.session.sent[-1].text)

    async def test_quiz_correct_answers_and_final_result(self) -> None:
        card = await self.send("Мини-тест")
        for _ in range(5):
            self.assertIn(f"📝 Мини-тест · {_ + 1} из 5", card.text)
            word = self.quiz_word(card)
            buttons = [row[0] for row in card.reply_markup.inline_keyboard]
            self.assertEqual(len(buttons), 4)
            self.assertEqual(len({b.text for b in buttons}), 4)
            correct = next(b for b in buttons if b.text == word.translation)
            card = await self.click(card, correct.callback_data)
        self.assertIn("Правильных ответов: 5 из 5", card.text)
        self.assertEqual(self.client.learner(1).attempted, 5)
        self.assertEqual(self.client.learner(1).correct, 5)

    async def test_wrong_answer_records_difficult_word_and_stop_invalidates_buttons(self) -> None:
        card = await self.send("/quiz")
        word = self.quiz_word(card)
        wrong = next(
            row[0] for row in card.reply_markup.inline_keyboard if row[0].text != word.translation
        )
        next_card = await self.click(card, wrong.callback_data)
        self.assertIn(word, self.client.review_words(1, difficult=True))
        await self.send("/stop")
        await self.click(next_card, next_card.reply_markup.inline_keyboard[0][0].callback_data)
        self.assertEqual(self.client.learner(1).attempted, 1)
        self.assertIn("устарела", self.session.answers[-1])

    async def test_daily_completes_only_after_five_answers(self) -> None:
        card = await self.reach_daily_gaps()
        self.assertIsNone(self.client.learner(1).daily_date)
        self.assertEqual(self.client.learner(1).attempted, 0)
        self.assertEqual(self.client.learner(1).correct, 0)
        self.assertEqual(self.client.learner(1).reviewed, 3)
        for i in range(2):
            word = self.gap_word(card)
            card = await self.send(f"  {word.text.upper()}.  ")
            feedback = self.session.sent[-2].text
            self.assertIn("Верно", feedback)
            self.assertIn(f"Правильное слово: {word.text}", feedback)
            self.assertIn(GAP_EXERCISES[word.id].completed_sentence, feedback)
            if i == 0:
                self.assertIn("5 из 5", card.text)
                self.assertIsNone(self.client.learner(1).daily_date)
        self.assertIn("Карточек пройдено: 3 из 3", card.text)
        self.assertIn("Правильных ответов в заданиях с пропуском: 2 из 2", card.text)
        self.assertEqual(self.client.learner(1).attempted, 2)
        self.assertEqual(self.client.learner(1).correct, 2)
        self.assertEqual(self.client.learner(1).reviewed, 5)
        self.assertIsNotNone(self.client.learner(1).daily_date)
        await self.send("/daily")
        self.assertIn("уже выполнена", self.session.sent[-1].text)
        self.assertIsNone(self.client.learner(2).daily_date)

    async def test_level_buttons_and_cross_user_rejection(self) -> None:
        choice = await self.send("/level")
        data = choice.reply_markup.inline_keyboard[1][0].callback_data
        await self.click(choice, data, user_id=2)
        self.assertEqual(self.client.learner(1).level, "A1")
        await self.click(choice, data)
        self.assertEqual(self.client.learner(1).level, "B1")
        self.assertEqual(self.client.learner(2).level, "A1")
        await self.send("/progress")
        self.assertIn("Уровень: B1", self.session.sent[-1].text)

    async def test_group_messages_are_ignored(self) -> None:
        await self.send("/start", chat_type="group")
        self.assertEqual(self.session.sent, [])

    async def test_rating_requires_reveal(self) -> None:
        card = await self.send("/review")
        reveal = card.reply_markup.inline_keyboard[0][0].callback_data
        await self.click(card, reveal.replace("reveal:", "rate:") + ":5")
        self.assertEqual(self.client.learner(1).reviewed, 0)
        self.assertIn("последнего задания", self.session.answers[-1])

    async def test_every_new_menu_button_opens_its_section(self) -> None:
        expected_rows = [
            ["📚 Карточки слов", "📝 Мини-тест"],
            ["🔁 Сложные слова", "☀️ Практика дня"],
            ["💬 Разговор на английском"],
            ["📊 Мой прогресс", "🎚 Уровень"],
            ["❓ Помощь"],
        ]
        self.assertEqual([[b.text for b in row] for row in MENU.keyboard], expected_rows)
        self.client.rate(1, WORDS[0], 1)
        for row in MENU_ROWS:
            for label, action in row:
                with self.subTest(button=label):
                    reply = await self.send(label)
                    expected = {
                        "review": "📚 Карточки слов · 1 из",
                        "quiz": "📝 Мини-тест · 1 из 5",
                        "difficult": "🔁 Сложные слова · 1 из",
                        "daily": "☀️ Практика дня · 1 из 5",
                        "talk": "LLM пока не подключена",
                        "progress": "📊 Мой прогресс",
                        "level": "🎚 Уровень английского",
                        "help": "❓ Помощь",
                    }[action]
                    self.assertIn(expected, reply.text)

    async def test_card_labels_keep_original_intervals(self) -> None:
        intervals = {1: 600, 3: 86400, 4: 259200, 5: 604800}
        self.assertEqual(RATINGS, {1: "Не помню", 3: "С трудом", 4: "Помню", 5: "Легко"})
        for quality, seconds in intervals.items():
            with self.subTest(quality=quality):
                card = await self.send("/review", user_id=quality)
                rating = await self.click(
                    card, card.reply_markup.inline_keyboard[0][0].callback_data, quality
                )
                buttons = [b for row in rating.reply_markup.inline_keyboard for b in row]
                self.assertEqual([b.text for b in buttons], list(RATINGS.values()))
                button = next(b for b in buttons if b.text == RATINGS[quality])
                await self.click(rating, button.callback_data, quality)
                record = self.client.learner(quality).words[WORDS[0].id]
                remaining = (record.next_due - datetime.now(UTC)).total_seconds()
                self.assertLess(abs(remaining - seconds), 2)
                feedback = self.session.sent[-2].text
                self.assertIn(f"Оценка сохранена: «{RATINGS[quality]}»", feedback)
                self.assertIn("Следующее повторение:", feedback)
                self.assertNotIn("Интервалы демонстрационные", feedback)

    async def test_daily_mixed_result_and_wrong_answer_explanation(self) -> None:
        card = await self.reach_daily_gaps()
        first = self.gap_word(card)
        card = await self.send(first.text)
        second = self.gap_word(card)
        result = await self.send("wrong")
        feedback = self.session.sent[-2].text
        self.assertIn("Ответ неверный", feedback)
        self.assertIn(f"Правильное слово: {second.text}", feedback)
        self.assertIn(GAP_EXERCISES[second.id].completed_sentence, feedback)
        self.assertIn(GAP_EXERCISES[second.id].explanation, feedback)
        self.assertIn("Карточек пройдено: 3 из 3", result.text)
        self.assertIn("Правильных ответов в заданиях с пропуском: 1 из 2", result.text)
        self.assertEqual(self.client.learner(1).words[second.id].mistakes, 1)
        for word, seconds in ((first, 259200), (second, 600)):
            due = self.client.learner(1).words[word.id].next_due
            self.assertLess(abs((due - datetime.now(UTC)).total_seconds() - seconds), 2)

    async def test_daily_self_assessments_do_not_raise_correct_score(self) -> None:
        card = await self.send("/daily")
        for _ in range(3):
            card = await self.rate_card(card, quality=5)
        await self.send("wrong")
        result = await self.send("wrong")
        self.assertIn("Правильных ответов в заданиях с пропуском: 0 из 2", result.text)
        self.assertEqual(self.client.learner(1).correct, 0)
        self.assertEqual(self.client.learner(1).attempted, 2)

    async def test_daily_wrong_answers_mark_words_difficult(self) -> None:
        card = await self.send("/daily")
        for _ in range(3):
            card = await self.rate_card(card, quality=1)
        first = self.gap_word(card)
        card = await self.send("wrong")
        second = self.gap_word(card)
        await self.send("wrong")
        self.assertEqual(len(self.client.review_words(1, difficult=True)), 5)
        self.assertIn(first, self.client.review_words(1, difficult=True))
        self.assertIn(second, self.client.review_words(1, difficult=True))

    async def test_help_progress_and_unknown_commands_do_not_answer_gap(self) -> None:
        card = await self.reach_daily_gaps()
        word = self.gap_word(card)
        for text in ("/help", "❓ Помощь", "/progress", "📊 Мой прогресс",
                     "/unknown", "/wrong@other_bot"):
            with self.subTest(text=text):
                reply = await self.send(text)
                self.assertEqual(self.client.learner(1).attempted, 0)
                self.assertIsNone(self.client.learner(1).daily_date)
                self.assertIn("Текущее занятие продолжается", reply.text)
                self.assertIn("4 из 5", reply.text)
        reply = await self.send(word.text)
        self.assertEqual(self.client.learner(1).attempted, 1)
        self.assertIn("5 из 5", reply.text)

    async def test_stop_during_gap_preserves_answers_but_not_completion(self) -> None:
        card = await self.reach_daily_gaps()
        await self.send(self.gap_word(card).text)
        result = await self.send("/stop")
        self.assertIn("Практика дня не завершена", result.text)
        self.assertIsNone(self.client.learner(1).daily_date)
        self.assertEqual(self.client.learner(1).attempted, 1)
        await self.send("habit")
        self.assertEqual(self.client.learner(1).attempted, 1)
        restarted = await self.send("/daily")
        self.assertIn("1 из 5", restarted.text)
        self.assertIsNotNone(restarted.reply_markup)

    async def test_switching_modes_and_commands_during_gap_never_counts_as_answer(self) -> None:
        for text in ("📝 Мини-тест", "📚 Карточки слов", "🔁 Сложные слова",
                     "💬 Разговор на английском", "🎚 Уровень", "☀️ Практика дня",
                     "/quiz", "/review", "/difficult", "/talk", "/level", "/link",
                     "/daily", "/start", "Практика на сегодня"):
            with self.subTest(action=text):
                # Ensure the difficult section is populated for this transition.
                self.client.rate(1, WORDS[7], 1)
                await self.reach_daily_gaps()
                attempted = self.client.learner(1).attempted
                reviewed = self.client.learner(1).reviewed
                await self.send(text)
                self.assertEqual(self.client.learner(1).attempted, attempted)
                self.assertIsNone(self.client.learner(1).daily_date)
                await self.send("enough")
                self.assertEqual(self.client.learner(1).attempted, attempted)
                self.assertEqual(self.client.learner(1).reviewed, reviewed)

    async def test_interrupted_daily_cards_do_not_complete_and_old_buttons_expire(self) -> None:
        card = await self.send("/daily")
        reveal = card.reply_markup.inline_keyboard[0][0].callback_data
        rating = await self.click(card, reveal)
        rate = rating.reply_markup.inline_keyboard[1][0].callback_data
        await self.send("/quiz")
        await self.click(rating, rate)
        await self.click(card, reveal)
        self.assertEqual(self.client.learner(1).reviewed, 0)
        self.assertIsNone(self.client.learner(1).daily_date)
        self.assertIn("устарела", self.session.answers[-1])

    async def test_daily_duplicate_rating_and_old_quiz_buttons_during_gap(self) -> None:
        quiz = await self.send("/quiz")
        answer = quiz.reply_markup.inline_keyboard[0][0].callback_data
        card = await self.send("/daily")
        rating = await self.click(card, card.reply_markup.inline_keyboard[0][0].callback_data)
        rate = rating.reply_markup.inline_keyboard[1][0].callback_data
        card = await self.click(rating, rate)
        await self.click(rating, rate)
        self.assertEqual(self.client.learner(1).reviewed, 1)
        card = await self.rate_card(card)
        card = await self.rate_card(card)
        gap_word = self.gap_word(card)
        for old_message, data in ((quiz, answer), (rating, rate)):
            await self.click(old_message, data)
            self.assertIn("устарела", self.session.answers[-1])
        self.assertEqual(self.client.learner(1).reviewed, 3)
        self.assertEqual(self.client.learner(1).attempted, 0)
        await self.send(gap_word.text)
        self.assertEqual(self.client.learner(1).correct, 1)

    async def test_daily_users_have_independent_steps_and_results(self) -> None:
        card1 = await self.reach_daily_gaps(user_id=1)
        card2 = await self.send("/daily", user_id=2)
        reveal2 = card2.reply_markup.inline_keyboard[0][0].callback_data
        await self.click(card2, reveal2, user_id=1)
        self.assertIn("устарела", self.session.answers[-1])
        await self.send(self.gap_word(card1).text, user_id=2)
        self.assertEqual(self.client.learner(2).attempted, 0)
        self.assertEqual(self.client.learner(2).reviewed, 0)
        card1 = await self.send(self.gap_word(card1).text, user_id=1)
        await self.send(self.gap_word(card1).text, user_id=1)
        self.assertIsNotNone(self.client.learner(1).daily_date)
        self.assertIsNone(self.client.learner(2).daily_date)
        card2 = await self.rate_card(card2, user_id=2)
        self.assertIn("2 из 5", card2.text)
        self.assertEqual(self.client.learner(2).reviewed, 1)

    async def test_daily_can_repeat_after_utc_date_changes(self) -> None:
        self.client.learner(1).daily_date = (
            datetime.now(UTC) - timedelta(days=1)
        ).date().isoformat()
        reply = await self.send("/daily")
        self.assertIn("1 из 5", reply.text)

    async def test_blank_and_nontext_messages_do_not_answer_gap(self) -> None:
        card = await self.reach_daily_gaps()
        for text in (None, "  "):
            reply = await self.send(text)
            self.assertIn("Напиши пропущенное", reply.text)
            self.assertEqual(self.client.learner(1).attempted, 0)
        await self.send(self.gap_word(card).text)
        self.assertEqual(self.client.learner(1).correct, 1)

    async def test_quiz_feedback_and_old_answer_cannot_score_twice(self) -> None:
        card = await self.send("📝 Мини-тест")
        word = self.quiz_word(card)
        correct = next(
            row[0] for row in card.reply_markup.inline_keyboard
            if row[0].text == word.translation
        )
        await self.click(card, correct.callback_data)
        self.assertIn("Верно", self.session.sent[-2].text)
        self.assertIn(f"{word.text} — {word.translation}", self.session.sent[-2].text)
        await self.click(card, correct.callback_data)
        self.assertEqual(self.client.learner(1).attempted, 1)
        self.assertIn("устарела", self.session.answers[-1])

    async def test_plain_text_outside_exercises_is_not_scored(self) -> None:
        reply = await self.send("apple")
        self.assertIn("Выбери занятие", reply.text)
        self.assertEqual(self.client.learner(1).attempted, 0)
        card = await self.send("/review")
        await self.send("apple")
        self.assertEqual(self.client.learner(1).reviewed, 0)
        self.assertIn("Показать перевод", self.session.sent[-1].text)
        await self.rate_card(card)
        self.assertEqual(self.client.learner(1).reviewed, 1)

    async def test_help_fits_telegram_message_with_resume_hint(self) -> None:
        await self.reach_daily_gaps()
        reply = await self.send("/help")
        self.assertTrue(reply.text.startswith(HELP))
        self.assertLessEqual(len(reply.text.encode("utf-16-le")) // 2, 4096)

    async def test_full_card_session_summary(self) -> None:
        card = await self.send("📚 Карточки слов")
        for step in range(8):
            self.assertIn(f"📚 Карточки слов · {step + 1} из 8", card.text)
            card = await self.rate_card(card)
        self.assertIn("Карточек пройдено: 8 из 8", card.text)
        self.assertEqual(self.client.learner(1).attempted, 0)
        reply = await self.send("/review")
        self.assertIn("Пока нет слов к повторению", reply.text)

    async def test_simultaneous_duplicate_clicks_are_counted_once(self) -> None:
        card = await self.send("/daily")
        rating = await self.click(card, card.reply_markup.inline_keyboard[0][0].callback_data)
        rate = rating.reply_markup.inline_keyboard[1][0].callback_data
        await asyncio.gather(self.click(rating, rate), self.click(rating, rate))
        self.assertEqual(self.client.learner(1).reviewed, 1)
        self.assertIn("устарела", self.session.answers[-1])
        card = await self.send("/quiz")
        answer = card.reply_markup.inline_keyboard[0][0].callback_data
        await asyncio.gather(self.click(card, answer), self.click(card, answer))
        self.assertEqual(self.client.learner(1).attempted, 1)
        self.assertIsNone(self.client.learner(1).daily_date)
