"""Grammar quiz UI. Exercises and grading come exclusively from the shared API."""

import secrets
from dataclasses import dataclass, field

from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)

from bot.api_client import BackendClient, BackendError, GrammarState


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


@dataclass
class QuizFlow:
    phase: str
    ticket: str = field(default_factory=lambda: secrets.token_hex(8))
    topics: set[int] = field(default_factory=set)
    state: GrammarState | None = None


class GrammarUI:
    def __init__(self, client: BackendClient, menu: ReplyKeyboardMarkup) -> None:
        self.client, self.menu = client, menu
        self.flows: dict[int, QuizFlow] = {}

    def cancel_local(self, user_id: int) -> None:
        self.flows.pop(user_id, None)

    async def topics(self, message: Message, user_id: int) -> None:
        topics = await self.client.grammar_topics(user_id)
        flow = QuizFlow("topics", topics={t.id for t in topics})
        self.flows[user_id] = flow
        rows = [[(t.title, f"gtopic:{flow.ticket}:{t.id}")] for t in topics]
        if topics:
            rows.append([("Смешанный тест", f"gmix:{flow.ticket}")])
            text = (
                "📝 Мини-тест по грамматике\n\nВыбери тему или смешанный тест.\n"
                "До 5 разных заданий из курса сайта. Повторные прохождения могут "
                "использовать знакомые задания: банк ограничен."
            )
        else:
            text = (
                "Грамматические задания пока не загружены на сервер. Сообщи об этом разработчику."
            )
        rows.extend(
            [
                [("Тест по моим словам", f"gwords:{flow.ticket}")],
                [("Главное меню", f"ghome:{flow.ticket}")],
            ]
        )
        await message.answer(text, reply_markup=keyboard(rows))

    async def begin(
        self,
        message: Message,
        user_id: int,
        topic_id: int | None,
        previous_token: str | None = None,
    ) -> None:
        try:
            state = await self.client.start_grammar(user_id, topic_id, previous_token)
        except BackendError as exc:
            if exc.status not in (404, 409, 412):
                raise
            self.cancel_local(user_id)
            text = (
                "Грамматические задания пока не загружены на сервер. Сообщи разработчику."
                if exc.status == 412
                else "Тема или прошлый тест изменились либо устарели. Открой /quiz заново. "
                "Принятые ответы сохранены."
            )
            await message.answer(text, reply_markup=self.menu)
            return
        self.flows[user_id] = QuizFlow("question", state=state)
        await message.answer(
            f"В тесте {state.total} заданий.\n\n"
            "Выбор ответа — кнопкой. Пропуск, перевод или предложение — текстом.\n"
            "Для сборки предложения используй предложенные слова.\n\n"
            "После ответа будут результат, объяснение и кнопка перехода дальше.\n"
            "/stop — отменить; /help — помощь.",
            reply_markup=self.menu,
        )
        await self.show_question(message, user_id)

    async def show_question(self, message: Message, user_id: int) -> None:
        flow = self.flows[user_id]
        state, question = flow.state, flow.state.question
        flow.phase, flow.ticket = "question", secrets.token_hex(8)
        text = (
            f"📝 Вопрос {question.position + 1} из {state.total}\n"
            f"Тема: {question.topic}\n\n{question.prompt}"
        )
        if question.type == "multiple_choice":
            markup = keyboard(
                [
                    [(label, f"gchoice:{flow.ticket}:{i}")]
                    for i, label in enumerate(question.options)
                ]
                + [[("Отменить тест", f"ghome:{flow.ticket}")]]
            )
        else:
            if question.type == "word_order":
                text += "\n\nСлова: " + " · ".join(question.words)
            text += "\n\nОтправь ответ одним сообщением. /stop — отмена."
            markup = self.menu
        await message.answer(text, reply_markup=markup)

    async def show_result(self, message: Message, user_id: int) -> None:
        flow = self.flows[user_id]
        state = flow.state
        flow.phase, flow.ticket = "result", secrets.token_hex(8)
        mistakes = ", ".join(state.mistake_topics) if state.mistake_topics else "ошибок нет"
        await message.answer(
            f"Тест завершён!\n\n✅ Правильных ответов: {state.correct} из {state.total}.\n\n"
            f"Темы с ошибками: {mistakes}.\n\nПринятые ответы сохранены в общем аккаунте.",
            reply_markup=keyboard(
                [
                    [("Пройти ещё раз", f"gagain:{flow.ticket}")],
                    [
                        ("Выбрать тему", f"gthemes:{flow.ticket}"),
                        ("Главное меню", f"ghome:{flow.ticket}"),
                    ],
                ]
            ),
        )

    async def submit(self, message: Message, user_id: int, **answer) -> None:
        flow = self.flows[user_id]
        state = flow.state
        flow.phase = "saving"
        try:
            feedback = await self.client.answer_grammar(
                user_id,
                state.session_token,
                state.question.position,
                **answer,
            )
        except BackendError as exc:
            flow.phase = "question"
            if exc.status == 0 or exc.status >= 500:
                await message.answer(
                    "Сервер не подтвердил сохранение. Ответ пока не отмечен как сохранённый.\n\n"
                    "Повтори последнее нажатие или отправь тот же текст ещё раз. "
                    "Сервер защитит результат от двойного сохранения. /stop — отмена.",
                    reply_markup=self.menu,
                )
                return
            if exc.status in (404, 409):
                self.cancel_local(user_id)
                await message.answer(
                    "Этот тест устарел или ответ уже был принят. Начни новый через /quiz. "
                    "Уже принятые ответы сохранены.",
                    reply_markup=self.menu,
                )
                return
            raise
        flow.state = feedback.state
        flow.phase, flow.ticket = "feedback", secrets.token_hex(8)
        text = "✅ Верно!" if feedback.is_correct else "Ответ неверный."
        if not feedback.is_correct:
            text += "\n\nПравильный ответ: " + " / ".join(feedback.correct_answers)
        if feedback.explanation:
            text += "\n\nОбъяснение:\n" + feedback.explanation
        text += "\n\nОтвет сохранён."
        label = "Показать результат" if feedback.state.completed else "Следующий вопрос"
        await message.answer(text, reply_markup=keyboard([[(label, f"gnext:{flow.ticket}")]]))

    async def callback(self, query: CallbackQuery) -> str | None:
        user_id = query.from_user.id
        flow = self.flows.get(user_id)
        parts = (query.data or "").split(":")
        if flow is None or len(parts) < 2 or parts[1] != flow.ticket:
            await query.answer("Кнопка устарела. Используй последнее задание или /quiz.")
            return None
        name = parts[0]
        if name == "ghome":
            self.cancel_local(user_id)
            await query.answer()
            return "home"
        if name == "gwords" and flow.phase == "topics":
            self.cancel_local(user_id)
            await query.answer()
            return "words"
        if name == "gthemes" and flow.phase == "result":
            flow.phase = "busy"
            await query.answer()
            await self.topics(query.message, user_id)
            return None
        if name == "gagain" and flow.phase == "result":
            previous = flow.state
            flow.phase = "busy"
            await query.answer()
            await self.begin(query.message, user_id, previous.topic_id, previous.session_token)
            return None
        if flow.phase == "topics" and (
            name == "gmix"
            and bool(flow.topics)
            or name == "gtopic"
            and len(parts) == 3
            and parts[2].isdigit()
            and int(parts[2]) in flow.topics
        ):
            topic_id = None if name == "gmix" else int(parts[2])
            flow.phase = "busy"
            await query.answer()
            await self.begin(query.message, user_id, topic_id)
            return None
        if name == "gnext" and flow.phase == "feedback":
            flow.phase = "busy"
            await query.answer()
            if flow.state.completed:
                await self.show_result(query.message, user_id)
            else:
                await self.show_question(query.message, user_id)
            return None
        if name == "gchoice" and flow.phase == "question":
            question = flow.state.question
            if (
                question.type != "multiple_choice"
                or len(parts) != 3
                or parts[2] not in [str(i) for i in range(len(question.options))]
            ):
                await query.answer("Выбери один из вариантов последнего вопроса.")
                return None
            flow.phase = "saving"
            await query.answer()
            await self.submit(query.message, user_id, option_index=int(parts[2]))
            return None
        await query.answer("Используй последнее задание.")
        return None

    async def text(self, message: Message, user_id: int) -> bool:
        flow = self.flows.get(user_id)
        if flow is None:
            return False
        if flow.phase == "feedback":
            await message.answer("Ответ уже принят. Нажми кнопку перехода под результатом.")
            return True
        if flow.phase != "question" or flow.state.question.type == "multiple_choice":
            await message.answer("Используй кнопки последнего сообщения или /stop.")
            return True
        value = (message.text or "").strip()
        if not value or len(value) > 500:
            await message.answer("Отправь непустой ответ до 500 символов. /stop — отмена.")
            return True
        if value.startswith("/"):
            return False
        await self.submit(message, user_id, answer=value)
        return True
