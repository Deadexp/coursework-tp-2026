"""Server-backed quizzes, daily practice, progress and shared profile level."""

import secrets

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import BackendClient, PracticeState
from bot.chat_ui import ChatView

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
    def __init__(self, client: BackendClient, menu, view: ChatView | None = None):
        self.client, self.menu = client, menu
        self.view = view or ChatView()
        self.active: dict[int, PracticeState] = {}
        self.tickets: dict[int, str] = {}
        self.levels: dict[int, str] = {}

    def cancel_local(self, user_id: int) -> None:
        self.active.pop(user_id, None)
        self.tickets.pop(user_id, None)
        self.levels.pop(user_id, None)

    async def start(self, message: Message, user_id: int, mode: str) -> None:
        state = await self.client.start_practice(user_id, mode)
        await self.render(message, user_id, state)

    async def render(
        self, message: Message, user_id: int, state: PracticeState, prefix: str = ""
    ) -> None:
        if state.completed:
            self.cancel_local(user_id)
            title = "☀️ Практика дня выполнена" if state.mode == "daily" else "📝 Мини-тест завершён"
            text = prefix + title + f"\n\nПравильных ответов: {state.correct} из {state.attempted}."
            if state.mode == "daily":
                text += f"\nКарточек пройдено: {state.cards_reviewed}."
            await self.view.show(message, keep=True, text=text, reply_markup=self.menu)
            return
        self.active[user_id] = state
        ticket = secrets.token_hex(8)
        self.tickets[user_id] = ticket
        question = state.question
        title = "📝 Мини-тест" if state.mode == "quiz" else "☀️ Практика дня"
        text = prefix + f"{title} · {state.answered + 1} из {state.total}\n\n{question.prompt}"
        if question.kind == "card":
            if question.revealed:
                await self.view.show(
                    message,
                    keep=True,
                    text=text
                    + "\nПеревод: "
                    + question.translation
                    + "\n\nКак вспомнился перевод?",
                    reply_markup=buttons(
                        [
                            [(RATINGS[q], f"prate:{ticket}:{q}") for q in row]
                            for row in ((1, 3), (4, 5))
                        ]
                    ),
                )
            else:
                await self.view.show(
                    message,
                    keep=True,
                    text=text + "\n\nВспомни перевод.",
                    reply_markup=buttons([[("Показать перевод", f"preveal:{ticket}")]]),
                )
        elif question.kind == "choice":
            await self.view.show(
                message,
                keep=True,
                text=text,
                reply_markup=buttons(
                    [
                        [(choice, f"pchoice:{ticket}:{i}")]
                        for i, choice in enumerate(question.choices)
                    ]
                ),
            )
        else:
            await self.view.show(
                message,
                keep=True,
                text=text + "\n\nОтправь английское слово одним сообщением. Вариантов ответа нет.",
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
        await self.render(
            message,
            user_id,
            feedback.state,
            f"Вопрос: {state.question.prompt}\n"
            + (
                f"Твой ответ: {answer['answer']}\n"
                if "answer" in answer
                else f"Твой ответ: {state.question.choices[answer['option_index']]}\n"
                if "option_index" in answer
                else ""
            )
            + text
            + f"\nПравильно: {feedback.word} — {feedback.translation}\n\n",
        )

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
            await self.view.show(
                query.message,
                f"Уровень сохранён: {level}.",
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
            await self.view.notice(
                message, "Напиши непустое английское слово до 200 символов. /stop — выход."
            )
            return True
        if value.startswith("/"):
            return False
        self.tickets.pop(user_id, None)
        await self.submit(message, user_id, answer=value)
        return True

    async def progress(self, message: Message, user_id: int, *, keep_screen: bool = False) -> None:
        data = await self.client.progress(user_id)
        send = self.view.notice if keep_screen else self.view.show
        await send(
            message,
            "📊 Статистика\n\n"
            f"Слов в словаре: {data.words}\n"
            f"К повторению: {data.due}\n"
            f"Повторений слов: {data.reviews}\n\n"
            f"Слова: {data.correct} верных ответов из {data.attempted}\n"
            f"Грамматика: {data.grammar_correct} из {data.grammar_attempted}\n"
            f"Тестов по словам завершено: {data.quizzes_completed}"
            + ("\n\nЗадание остаётся выше — можно продолжить." if keep_screen else ""),
            reply_markup=self.menu,
        )

    async def level(self, message: Message, user_id: int) -> None:
        level = await self.client.level(user_id)
        ticket = secrets.token_hex(8)
        self.levels[user_id] = ticket
        await self.view.show(
            message,
            f"🎚 Уровень английского\n\nТекущий уровень аккаунта: {level}. Выбери новый:",
            reply_markup=buttons(
                [
                    [(value, f"plevel:{ticket}:{value}") for value in LEVELS[i : i + 2]]
                    for i in range(0, len(LEVELS), 2)
                ]
            ),
        )
