"""Exercise the real aiogram router without Telegram network calls."""

import asyncio
import json
import unittest

import httpx
import test_connected as connected

SENDER = connected.SENDER


class GrammarUITests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = connected.ConnectedTests.asyncSetUp
    asyncTearDown = connected.ConnectedTests.asyncTearDown
    send = connected.ConnectedTests.send
    click = connected.ConnectedTests.click
    button = connected.ConnectedTests.button
    practice_snapshot = connected.ConnectedTests.practice_snapshot

    def respond(self, request):
        if not request.url.path.startswith("/grammar/"):
            return connected.ConnectedTests.respond(self, request)
        self.calls.append(request)
        if self.unavailable:
            raise httpx.ConnectError("private details", request=request)
        if not self.linked or self.status != 200:
            return httpx.Response(403 if not self.linked else self.status, json={})
        if request.url.path == "/grammar/topics":
            return httpx.Response(
                200, json=[{"id": 61, "title": "Server theme", "exercises_total": 2}]
            )
        body = json.loads(request.content)
        if request.url.path == "/grammar/quizzes":
            if not hasattr(self, "grammars"):
                self.grammars = {}
            token = f"synthetic-quiz-{len(self.grammars)}"
            self.grammars[token] = {"position": 0, "correct": 0, "topic_id": body["topic_id"]}
            return httpx.Response(200, json=self.snapshot(token))
        token = body["session_token"]
        quiz = self.grammars[token]
        correct = body.get("option_index") == 0 or body.get("answer") == "goes"
        quiz["position"] += 1
        quiz["correct"] += correct
        return httpx.Response(
            200,
            json={
                "is_correct": correct,
                "correct_answers": ["a" if body["position"] == 0 else "goes"],
                "explanation": "Existing course explanation",
                "state": self.snapshot(token),
            },
        )

    def snapshot(self, token):
        q = self.grammars[token]
        pos = q["position"]
        question = (
            None
            if pos == 2
            else {
                "position": pos,
                "topic": "Server theme",
                "type": "multiple_choice" if pos == 0 else getattr(self, "text_type", "fill_gap"),
                "prompt": "Choose an article" if pos == 0 else "He ___ to school.",
                "options": ["a", "the"] if pos == 0 else [],
                "words": ["school", "to", "goes", "He"] if pos == 1 else [],
            }
        )
        return {
            "session_token": token,
            "topic_id": q["topic_id"],
            "total": 2,
            "answered": pos,
            "correct": q["correct"],
            "completed": pos == 2,
            "mistake_topics": ["Server theme"] if pos > q["correct"] else [],
            "question": question,
        }

    def answers(self):
        return [r for r in self.calls if r.url.path == "/grammar/quizzes/answers"]

    async def begin(self, user=SENDER, mixed=False):
        themes = await self.send("/quiz", user_id=user)
        return await self.click(
            themes, self.button(themes, "gmix" if mixed else "gtopic"), user_id=user
        )

    async def test_dynamic_topics_mixed_and_rules(self):
        themes = await self.send("📝 Мини-тест")
        labels = [b.text for row in themes.reply_markup.inline_keyboard for b in row]
        self.assertIn("Server theme", labels)
        self.assertIn("Смешанный тест", labels)
        question = await self.click(themes, self.button(themes, "gmix"))
        self.assertIn("Вопрос 1 из 2", question.text)
        self.assertTrue(any("В тесте 2" in m.text for m in self.session.sent))
        self.assertNotIn("Правильный ответ", question.text)
        self.assertEqual(self.button(question, "gchoice").split(":")[-1], "0")
        self.assertNotIn("synthetic", self.button(question, "gchoice"))
        req = next(r for r in self.calls if r.url.path == "/grammar/quizzes")
        self.assertIsNone(json.loads(req.content)["topic_id"])
        self.assertEqual(req.headers["X-Telegram-ID"], str(SENDER))

    async def test_feedback_next_text_final_and_repeat(self):
        question = await self.begin()
        feedback = await self.click(question, self.button(question, "gchoice"))
        self.assertIn("Верно", feedback.text)
        self.assertIn("Existing course explanation", feedback.text)
        self.assertNotIn("Вопрос 2", feedback.text)
        await self.send("extra answer")
        self.assertEqual(len(self.answers()), 1)
        question = await self.click(feedback, self.button(feedback, "gnext"))
        self.assertIn("Вопрос 2 из 2", question.text)
        feedback = await self.send("wrong")
        self.assertIn("Правильный ответ: goes", feedback.text)
        result = await self.click(feedback, self.button(feedback, "gnext"))
        self.assertIn("1 из 2", result.text)
        self.assertIn("Темы с ошибками: Server theme", result.text)
        question = await self.click(result, self.button(result, "gagain"))
        self.assertIn("Вопрос 1 из 2", question.text)
        req = [r for r in self.calls if r.url.path == "/grammar/quizzes"][-1]
        self.assertEqual(
            json.loads(req.content), {"topic_id": 61, "previous_token": "synthetic-quiz-0"}
        )

    async def test_duplicates_foreign_stale_and_cancel(self):
        question = await self.begin()
        data = self.button(question, "gchoice")
        await self.click(question, data, user_id=SENDER + 1)
        self.assertEqual(len(self.answers()), 0)
        await asyncio.gather(self.click(question, data), self.click(question, data))
        self.assertEqual(len(self.answers()), 1)
        await self.send("/stop")
        await self.click(question, data)
        question = await self.begin()
        await self.click(question, self.button(question, "ghome"))
        self.assertEqual(len(self.answers()), 1)

    async def test_commands_and_invalid_text_are_not_answers(self):
        question = await self.begin()
        await self.send("a")
        self.assertEqual(len(self.answers()), 0)
        feedback = await self.click(question, self.button(question, "gchoice"))
        await self.click(feedback, self.button(feedback, "gnext"))
        for text in ["/unknown_command", "/help", "   ", "x" * 501]:
            await self.send(text)
        self.assertEqual(len(self.answers()), 1)
        await self.send("goes")
        self.assertEqual(len(self.answers()), 2)

    async def test_failure_and_same_request_retry(self):
        question = await self.begin()
        data = self.button(question, "gchoice")
        self.unavailable = True
        reply = await self.click(question, data)
        self.assertIn("Сервер не подтвердил", reply.text)
        self.assertNotIn("Ответ сохранён.", reply.text)
        self.assertNotIn("private", reply.text)
        self.unavailable = False
        reply = await self.click(question, data)
        self.assertIn("Ответ сохранён.", reply.text)
        self.assertEqual(len(self.answers()), 2)
        self.assertEqual(self.answers()[0].content, self.answers()[1].content)

    async def test_users_independent_and_word_order_text(self):
        self.text_type = "word_order"
        first = await self.begin()
        second = await self.begin(user=SENDER + 1)
        feedback = await self.click(first, self.button(first, "gchoice"))
        question = await self.click(feedback, self.button(feedback, "gnext"))
        self.assertIn("Слова:", question.text)
        await self.send("goes")
        await self.click(second, self.button(second, "gchoice"), user_id=SENDER + 1)
        self.assertEqual(
            [r.headers["X-Telegram-ID"] for r in self.answers()],
            [str(SENDER), str(SENDER), str(SENDER + 1)],
        )

    async def test_unlinked_unavailable_no_demo(self):
        self.linked = False
        reply = await self.send("/quiz")
        self.assertIn("http://site.test", reply.text)
        self.assertFalse(hasattr(self, "grammars"))
        self.linked = True
        self.unavailable = True
        reply = await self.send("/quiz")
        self.assertIn("Сервер недоступен", reply.text)
        self.assertFalse(hasattr(self, "grammars"))

    async def test_word_quiz_stays_in_submenu(self):
        themes = await self.send("/quiz")
        await self.click(themes, self.button(themes, "gwords"))
        self.assertTrue(any(r.url.path == "/practice/sessions" for r in self.calls))

    async def test_course_disappeared_has_specific_error_without_word_dictionary_hint(self):
        themes = await self.send("/quiz")
        self.status = 412
        reply = await self.click(themes, self.button(themes, "gtopic"))
        self.assertIn("Грамматические задания", reply.text)
        self.assertNotIn("Личный словарь пуст", reply.text)
        self.assertEqual(len(self.answers()), 0)
