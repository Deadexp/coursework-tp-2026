"""Server-backed quizzes, daily practice, progress and shared profile level."""

import secrets

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import BackendClient, PracticeState

RATINGS = {1: "Не помню", 3: "С трудом", 4: "Помню", 5: "Легко"}
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def buttons(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


class PracticeUI:
    def __init__(self, client: BackendClient, menu):
        self.client, self.menu = client, menu
        self.active: dict[int, PracticeState] = {}
        self.tickets: dict[int, str] = {}
        self.levels: dict[int, str] = {}

    def cancel_local(self, user_id: int) -> None:
        self.active.pop(user_id, None)
        self.tickets.pop(user_id, None)
        self.levels.pop(user_id, None)

    async def start(self, message: Message, user_id: int, mode: str) -> None:
        state = await self.client.start_practice(user_id, mode)
        title = "📝 Мини-тест" if mode == "quiz" else "☀️ Практика дня"
        if not state.completed:
            await message.answer(
                title + "\n\nСлова из твоего личного словаря. "
                "Сервер сохраняет каждый ответ. Незавершённое занятие можно продолжить.\n"
                "Вопросов: " + str(state.total) + ". Если слов мало, занятие короче.\n"
                "/stop — выйти из занятия, /help — помощь.",
                reply_markup=self.menu,
            )
        await self.render(message, user_id, state)

    async def render(self, message: Message, user_id: int, state: PracticeState) -> None:
        if state.completed:
            self.cancel_local(user_id)
            title = "☀️ Практика дня выполнена" if state.mode == "daily" else "📝 Мини-тест завершён"
            text = (
                title + f"\n\nКарточек пройдено: {state.cards_reviewed}.\n"
                f"Правильных ответов: {state.correct} из {state.attempted}.\n"
                "Самооценки карточек не считаются правильными ответами."
            )
            if state.mode == "daily":
                text += "\nСледующая практика — в новый день по UTC (03:00 по Москве)."
            await message.answer(text, reply_markup=self.menu)
            return
        self.active[user_id] = state
        ticket = secrets.token_hex(8)
        self.tickets[user_id] = ticket
        question = state.question
        title = "📝 Мини-тест" if state.mode == "quiz" else "☀️ Практика дня"
        text = f"{title} · {state.answered + 1} из {state.total}\n\n{question.prompt}"
        if question.kind == "card":
            if question.revealed:
                await message.answer(
                    text + "\nПеревод: " + question.translation + "\n\nКак вспомнился перевод?",
                    reply_markup=buttons(
                        [
                            [(RATINGS[q], f"prate:{ticket}:{q}") for q in row]
                            for row in ((1, 3), (4, 5))
                        ]
                    ),
                )
            else:
                await message.answer(
                    text + "\n\nВспомни перевод.",
                    reply_markup=buttons([[("Показать перевод", f"preveal:{ticket}")]]),
                )
        elif question.kind == "choice":
            await message.answer(
                text,
                reply_markup=buttons(
                    [
                        [(choice, f"pchoice:{ticket}:{i}")]
                        for i, choice in enumerate(question.choices)
                    ]
                ),
            )
        else:
            await message.answer(
                text + "\n\nОтправь английское слово одним сообщением. Вариантов ответа нет.",
                reply_markup=self.menu,
            )

    async def submit(self, message: Message, user_id: int, **answer) -> None:
        state = self.active[user_id]
        feedback = await self.client.answer_practice(
            user_id,
            state.session_id,
            state.question.position,
            **answer,
        )
        text = (
            "Оценка карточки сохранена."
            if feedback.is_correct is None
            else "✅ Верно!"
            if feedback.is_correct
            else "Ответ неверный. Запомним правильное слово."
        )
        await message.answer(
            text + f"\n\n{feedback.word} — {feedback.translation}\n"
            f"Следующее повторение: {feedback.next_review_at:%d.%m.%Y %H:%M} UTC (SM-2).",
        )
        await self.render(message, user_id, feedback.state)

    async def callback(self, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        parts = (query.data or "").split(":")
        if len(parts) < 2:
            await query.answer("Кнопка устарела.")
            return
        name, ticket = parts[:2]
        if name == "plevel":
            if self.levels.get(user_id) != ticket or len(parts) != 3 or parts[2] not in LEVELS:
                await query.answer("Кнопка устарела. Открой /level.")
                return
            self.levels.pop(user_id, None)
            await query.answer()
            level = await self.client.level(user_id, parts[2])
            await query.message.answer(
                f"Уровень аккаунта сохранён: {level}. На сайте он обновится после перезагрузки страницы.",
                reply_markup=self.menu,
            )
            return
        state = self.active.get(user_id)
        if self.tickets.get(user_id) != ticket or state is None:
            await query.answer("Кнопка устарела. Открой нужный режим или последнее задание.")
            return
        question = state.question
        valid = (
            name == "preveal"
            and question.kind == "card"
            and not question.revealed
            and len(parts) == 2
            or name == "prate"
            and question.kind == "card"
            and question.revealed
            and len(parts) == 3
            and parts[2] in ("1", "3", "4", "5")
            or name == "pchoice"
            and question.kind == "choice"
            and len(parts) == 3
            and parts[2] in [str(i) for i in range(len(question.choices))]
        )
        if not valid:
            await query.answer("Используй последнее задание.")
            return
        self.tickets.pop(user_id, None)
        await query.answer()
        if name == "preveal":
            result = await self.client.reveal_practice(user_id, state.session_id, question.position)
            await self.render(query.message, user_id, result)
        elif name == "prate":
            await self.submit(query.message, user_id, quality=int(parts[2]))
        else:
            await self.submit(query.message, user_id, option_index=int(parts[2]))

    async def text(self, message: Message, user_id: int) -> bool:
        state = self.active.get(user_id)
        if state is None or state.question.kind != "recall":
            return False
        value = (message.text or "").strip()
        if not value or len(value) > 200:
            await message.answer("Напиши непустое английское слово до 200 символов. /stop — выход.")
            return True
        if value.startswith("/"):
            return False
        self.tickets.pop(user_id, None)
        await self.submit(message, user_id, answer=value)
        return True

    async def progress(self, message: Message, user_id: int) -> None:
        data = await self.client.progress(user_id)
        await message.answer(
            "📊 Мой прогресс\n\n"
            f"Уровень: {data.level}\nСлов в словаре: {data.words}\n"
            f"Пора повторить: {data.due}\nПовторений по текущему словарю: {data.reviews}\n"
            f"Ответов в тестах и практике: {data.attempted}\nПравильных: {data.correct}\n"
            f"Завершено тестов по словам: {data.quizzes_completed}\n"
            f"Грамматика сайта и бота: {data.grammar_correct} верных из {data.grammar_attempted} ответов\n"
            f"Завершено практик дня: {data.daily_completed}\n"
            f"Последняя практика (UTC): {data.last_daily_date or 'ещё не выполнена'}\n\n"
            "Данные хранятся на общем сервере. Текущее занятие продолжается.",
            reply_markup=self.menu,
        )

    async def level(self, message: Message, user_id: int) -> None:
        level = await self.client.level(user_id)
        ticket = secrets.token_hex(8)
        self.levels[user_id] = ticket
        await message.answer(
            f"🎚 Уровень английского\n\nТекущий уровень аккаунта: {level}. Выбери новый:",
            reply_markup=buttons(
                [
                    [(value, f"plevel:{ticket}:{value}") for value in LEVELS[i : i + 2]]
                    for i in range(0, len(LEVELS), 2)
                ]
            ),
        )
