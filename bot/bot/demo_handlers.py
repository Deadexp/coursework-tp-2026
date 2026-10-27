"""Telegram UI for the explicitly selected standalone demo mode."""

import secrets
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.demo import GAP_EXERCISES, LEVELS, DemoClient, Flow

MENU_ROWS = (
    (("📚 Карточки слов", "review"), ("📝 Мини-тест", "quiz")),
    (("🔁 Сложные слова", "difficult"), ("☀️ Практика дня", "daily")),
    (("💬 Разговор на английском", "talk"),),
    (("📊 Мой прогресс", "progress"), ("🎚 Уровень", "level")),
    (("❓ Помощь", "help"),),
)
BUTTONS = {label: action for row in MENU_ROWS for label, action in row}
# Accept the old reply keyboard until the user opens the new menu.
BUTTONS.update({
    "Повторить слова": "review",
    "Мини-тест": "quiz",
    "Сложные слова": "difficult",
    "Практика на сегодня": "daily",
    "Поговорить на английском": "talk",
    "Мой прогресс": "progress",
    "Уровень английского": "level",
    "Помощь": "help",
})
MENU = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=label) for label, _ in row] for row in MENU_ROWS],
    resize_keyboard=True,
)
TITLES = {
    "review": "📚 Карточки слов",
    "difficult": "🔁 Сложные слова",
    "quiz": "📝 Мини-тест",
    "daily": "☀️ Практика дня",
}
RATINGS = {1: "Не помню", 3: "С трудом", 4: "Помню", 5: "Легко"}
HELP = (
    "❓ Помощь\n\n"
    "Что выбрать\n"
    "/review — карточки: вспомни перевод, открой его и оцени себя.\n"
    "/quiz — мини-тест: 5 вопросов, в каждом 4 варианта перевода.\n"
    "/difficult — карточки слов, в которых были ошибки. Их можно повторять внепланово.\n"
    "/daily — практика дня: 3 карточки и 2 предложения с пропуском. "
    "В пропусках нужно написать английское слово, вариантов ответа нет.\n\n"
    "Другие разделы\n"
    "/talk — разговор на английском: LLM пока не подключена.\n"
    "/level — выбрать уровень A1–C2; пока задания одинаковы для всех уровней.\n"
    "/progress — посмотреть результаты.\n"
    "/link — информация о будущей связи с сайтом.\n\n"
    "Как управлять занятием\n"
    "/stop — закончить текущее занятие.\n"
    "/start — открыть главное меню и закончить текущее занятие.\n"
    "/help — эта помощь. Помощь и прогресс не прерывают задание.\n"
    "Кнопки меню и команды доступны всегда. При выборе другого режима "
    "начинается новое занятие; уже записанные ответы сохраняются.\n\n"
    "Когда повторять\n"
    "Не помню — через 10 минут; С трудом — через 1 день; "
    "Помню — через 3 дня; Легко — через 7 дней.\n"
    "Верный ответ в задании назначает повторение через 3 дня, ошибка — через 10 минут. "
    "Это демонстрационные интервалы. Прошлые ошибки остаются в списке сложных слов.\n\n"
    "Практика дня\n"
    "Сначала идут сложные слова и слова к повторению. Занятие выполнено только после "
    "всех 5 шагов. Самооценка карточек и правильность вставленных слов считаются отдельно. "
    "После завершения новое занятие доступно на следующий день по UTC "
    "(в 03:00 по Москве). До этого можно заниматься в других режимах.\n\n"
    "Об учебной версии\n"
    "Словарь содержит 8 слов и не связан с сайтом. База данных и LLM не подключены. "
    "Результаты каждого пользователя хранятся отдельно только до остановки программы. "
    "Автоматических напоминаний нет.\n\n"
    "Выбери раздел в меню внизу или отправь команду."
)


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def step_heading(flow: Flow) -> str:
    return f"{TITLES[flow.mode]} · {flow.position + 1} из {len(flow.words)}"


def make_demo_router(client: DemoClient) -> Router:
    router = Router()
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    flows: dict[int, Flow] = {}
    level_tickets: dict[int, str] = {}

    def clear(user_id: int) -> None:
        flows.pop(user_id, None)
        level_tickets.pop(user_id, None)

    def resume_hint(user_id: int) -> str:
        flow = flows.get(user_id)
        if not flow:
            return ""
        instruction = {
            "reveal": "Нажми «Показать перевод» под последним словом.",
            "rate": "Оцени, насколько легко вспомнился перевод, кнопкой под ним.",
            "answer": "Выбери перевод кнопкой под последним вопросом.",
            "gap": "Напиши пропущенное английское слово из последнего задания.",
        }.get(flow.stage, "Открой нужный режим в меню.")
        return f"\n\nТекущее занятие продолжается\n{step_heading(flow)}\n{instruction}"

    async def show_step(message: Message, user_id: int) -> None:
        flow = flows[user_id]
        flow.ticket = secrets.token_hex(4)
        prefix = step_heading(flow) + "\n\n"
        if flow.is_card:
            flow.stage = "reveal"
            if flow.mode == "daily":
                prefix += f"Карточка {flow.position + 1} из 3\n\n"
            await message.answer(
                prefix + flow.word.text
                + "\n\nВспомни перевод, затем нажми «Показать перевод».",
                reply_markup=keyboard([[("Показать перевод", f"reveal:{flow.ticket}")]]),
            )
        elif flow.mode == "daily":
            flow.stage = "gap"
            exercise = GAP_EXERCISES[flow.word.id]
            await message.answer(
                prefix + f"Задание с пропуском · {flow.position - 2} из 2\n\n"
                + exercise.sentence + f"\nПодсказка: «{flow.word.translation}».\n\n"
                "Напиши пропущенное слово по-английски одним сообщением. "
                "Вариантов ответа нет.",
                reply_markup=MENU,
            )
        else:
            flow.stage = "answer"
            flow.options = client.choices(flow.word)
            await message.answer(
                prefix + f"Выбери перевод: {flow.word.text}\n\n"
                "Нажми один из четырёх вариантов ниже.",
                reply_markup=keyboard([
                    [(option, f"answer:{flow.ticket}:{i}")]
                    for i, option in enumerate(flow.options)
                ]),
            )

    async def advance(message: Message, user_id: int) -> None:
        flow = flows[user_id]
        flow.position += 1
        if flow.position < len(flow.words):
            await show_step(message, user_id)
            return
        if flow.mode == "daily":
            client.learner(user_id).daily_date = datetime.now(UTC).date().isoformat()
            summary = (
                f"Карточек пройдено: {flow.cards_reviewed} из 3.\n"
                f"Правильных ответов в заданиях с пропуском: {flow.correct} из 2.\n\n"
                "Карточки оцениваешь ты; они не входят в число правильных ответов.\n"
                "Следующая практика дня — завтра по UTC (в 03:00 по Москве). "
                "Сейчас можно открыть мини-тест или сложные слова."
            )
        elif flow.mode == "quiz":
            summary = f"Правильных ответов: {flow.correct} из {len(flow.words)}."
        else:
            summary = f"Карточек пройдено: {flow.cards_reviewed} из {len(flow.words)}."
        title = TITLES[flow.mode]
        clear(user_id)
        await message.answer(
            title + " · Итоги\n\nЗанятие завершено!\n\n" + summary
            + "\n\nВыбери следующий раздел в меню внизу.",
            reply_markup=MENU,
        )

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        clear(message.from_user.id)
        await message.answer(
            "👋 Привет! Давай практиковать английский\n\n"
            "Выбери занятие\n"
            "Карточки слов — вспомнить перевод и оценить себя.\n"
            "Мини-тест — проверить перевод в 5 вопросах с вариантами ответа.\n"
            "Сложные слова — повторить слова, в которых были ошибки.\n"
            "Практика дня — 3 карточки и 2 предложения: слова в пропуски пишешь сам.\n\n"
            "Другие возможности\n"
            "В «Моём прогрессе» видны результаты, в «Уровне» можно выбрать A1–C2. "
            "Уровень пока не меняет задания. Разговор на английском пока недоступен: "
            "LLM ещё не подключена.\n\n"
            "Об учебной версии\n"
            "В словаре 8 слов. Связи с сайтом и базой данных нет. "
            "Результаты хранятся только до остановки программы.\n\n"
            "Нажми кнопку в меню внизу. /help — подробная помощь. "
            "/stop — закончить текущее занятие.",
            reply_markup=MENU,
        )

    async def run_action(message: Message, action: str) -> None:
        user_id = message.from_user.id
        learner = client.learner(user_id)
        if action == "help":
            await message.answer(HELP + resume_hint(user_id), reply_markup=MENU)
            return
        if action == "progress":
            await message.answer(
                "📊 Мой прогресс\n\n"
                f"Уровень: {learner.level}\n"
                f"Всего оценок карточек и ответов: {learner.reviewed}\n"
                f"Ответов в мини-тестах и заданиях с пропуском: {learner.attempted}\n"
                f"Из них правильных: {learner.correct}\n"
                f"Сложных слов: {len(client.review_words(user_id, difficult=True))}\n\n"
                f"Последняя завершённая практика дня (дата по UTC): "
                f"{learner.daily_date or 'ещё не выполнена'}\n\n"
                "Самооценки карточек не считаются правильными ответами. "
                "После остановки программы результаты исчезнут.\n\n"
                "Выбери раздел в меню внизу." + resume_hint(user_id),
                reply_markup=MENU,
            )
            return
        previous = flows.get(user_id)
        interrupted_daily = previous is not None and previous.mode == "daily"
        clear(user_id)
        if action == "stop":
            await message.answer(
                "Занятие остановлено\n\n"
                "Уже записанные оценки и ответы сохранены до остановки программы.\n\n"
                + ("Практика дня не завершена. Её можно начать заново в меню.\n\n"
                   if interrupted_daily else "")
                + "Выбери следующий раздел в меню внизу.",
                reply_markup=MENU,
            )
        elif action == "link":
            await message.answer(
                "Связь с сайтом\n\n"
                "Связь с сайтом ещё не подключена. Пока используем учебный словарь. "
                "Коды и пароли вводить не нужно.\n\nВыбери занятие в меню внизу.",
                reply_markup=MENU,
            )
        elif action == "talk":
            await message.answer(
                "💬 Разговор на английском\n\n"
                "LLM пока не подключена, поэтому свободная беседа и разбор ошибок "
                "ещё недоступны. Позже здесь можно будет выбрать тему "
                "и общаться с учётом своего уровня.\n\n"
                "Пока выбери карточки, мини-тест или практику дня в меню внизу.",
                reply_markup=MENU,
            )
        elif action == "level":
            ticket = secrets.token_hex(4)
            level_tickets[user_id] = ticket
            await message.answer(
                f"🎚 Уровень английского\n\nТвой уровень: {learner.level}.\n\n"
                "Нажми нужный уровень ниже. Пока задания общие для всех; "
                "позже уровень будет учитываться в разговоре с LLM.",
                reply_markup=keyboard([
                    [(level, f"level:{ticket}:{level}") for level in LEVELS[i : i + 2]]
                    for i in range(0, len(LEVELS), 2)
                ]),
            )
        elif action in TITLES:
            if action == "daily" and learner.daily_date == datetime.now(UTC).date().isoformat():
                await message.answer(
                    "☀️ Практика дня уже выполнена\n\n"
                    "Новое занятие откроется на следующий день по UTC "
                    "(в 03:00 по Москве).\n\n"
                    "Сейчас выбери мини-тест, карточки или сложные слова в меню внизу.",
                    reply_markup=MENU,
                )
                return
            words = (
                client.quiz_words(user_id) if action == "quiz"
                else client.daily_words(user_id) if action == "daily"
                else client.review_words(user_id, difficult=action == "difficult")
            )
            if not words:
                await message.answer(
                    ("🔁 Сложных слов пока нет\n\n"
                     "Они появятся после неверных ответов или оценки «Не помню».\n\n"
                     "Попробуй карточки или мини-тест в меню внизу.")
                    if action == "difficult" else
                    ("📚 Пока нет слов к повторению\n\n"
                     "Все слова уже оценены, время следующего повторения ещё не наступило.\n\n"
                     "Выбери мини-тест или внепланово повтори сложные слова в меню внизу."),
                    reply_markup=MENU,
                )
                return
            flows[user_id] = Flow(action, words)
            descriptions = {
                "review": "Вспоминай перевод, открывай его и оценивай, как легко вспомнилось.",
                "difficult": "Повтори слова с ошибками: открой перевод и оцени себя.",
                "quiz": "Ответь на 5 вопросов. В каждом выбери один из четырёх переводов.",
                "daily": "Пройди 3 карточки, затем впиши слова в 2 предложения. "
                         "В итогах карточки и ответы будут показаны отдельно.",
            }
            await message.answer(
                TITLES[action] + "\n\n" + descriptions[action]
                + "\n\n/stop — закончить занятие. Выбор другого режима начинает "
                "новое занятие; уже записанные результаты сохраняются.",
                reply_markup=MENU,
            )
            await show_step(message, user_id)

    @router.message(Command(
        "help", "review", "quiz", "difficult", "daily", "talk", "level", "progress",
        "stop", "link",
    ))
    async def command(message: Message) -> None:
        action = message.text.split()[0].split("@")[0][1:]
        await run_action(message, action)

    @router.message(F.text.in_(BUTTONS))
    async def menu(message: Message) -> None:
        await run_action(message, BUTTONS[message.text])

    @router.callback_query()
    async def callback(query: CallbackQuery) -> None:
        user_id = query.from_user.id
        parts = (query.data or "").split(":")
        if (
            len(parts) == 3 and parts[0] == "level"
            and level_tickets.get(user_id) == parts[1] and parts[2] in LEVELS
        ):
            client.learner(user_id).level = parts[2]
            clear(user_id)
            await query.answer()
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer(
                f"🎚 Уровень сохранён\n\nВыбран уровень {parts[2]}.\n\n"
                "Выбери занятие в меню внизу.", reply_markup=MENU,
            )
            return
        flow = flows.get(user_id)
        if not flow or len(parts) < 2 or parts[1] != flow.ticket:
            await query.answer("Эта кнопка устарела. Используй последнее задание или меню внизу.")
            return
        if parts[0] == "reveal" and len(parts) == 2 and flow.stage == "reveal":
            flow.stage = "rate"
            await query.answer()
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer(
                step_heading(flow) + f"\n\n{flow.word.text} — {flow.word.translation}\n\n"
                "Насколько легко вспомнился перевод до подсказки?\n"
                "Нажми подходящую оценку ниже.",
                reply_markup=keyboard([
                    [(RATINGS[q], f"rate:{flow.ticket}:{q}") for q in row]
                    for row in ((1, 3), (4, 5))
                ]),
            )
            return
        if (
            parts[0] == "rate" and len(parts) == 3 and flow.stage == "rate"
            and parts[2] in ("1", "3", "4", "5")
        ):
            flow.stage = "finished"
            quality = int(parts[2])
            due = client.rate(user_id, flow.word, quality)
            flow.cards_reviewed += 1
            await query.answer()
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer(
                f"Оценка сохранена: «{RATINGS[quality]}»\n\n"
                f"{flow.word.text} — {flow.word.translation}\n"
                f"Следующее повторение: {due:%d.%m.%Y %H:%M} UTC.\n\n"
                "Продолжим следующим шагом. Если шаг был последним, ниже появятся итоги.",
            )
            await advance(query.message, user_id)
            return
        if (
            parts[0] == "answer" and len(parts) == 3 and flow.stage == "answer"
            and parts[2] in [str(i) for i in range(len(flow.options))]
        ):
            flow.stage = "finished"
            correct = flow.options[int(parts[2])] == flow.word.translation
            flow.correct += correct
            client.record_answer(user_id, flow.word, correct)
            await query.answer()
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer(
                ("✅ Верно!" if correct else "Ответ неверный. Запомним правильный перевод.")
                + f"\n\n{flow.word.text} — {flow.word.translation}\n\n"
                "Далее — следующий вопрос или итоги, если это был последний вопрос.",
            )
            await advance(query.message, user_id)
            return
        await query.answer("Используй кнопки последнего задания. /help — помощь.")

    @router.message()
    async def text_or_hint(message: Message) -> None:
        user_id = message.from_user.id
        text = message.text
        # Commands, including unknown commands, must never become learning answers.
        if text and text.lstrip().startswith("/"):
            await message.answer(
                "Команда не распознана\n\n"
                "Открой /help со списком команд или выбери раздел в меню внизу."
                + resume_hint(user_id), reply_markup=MENU,
            )
            return
        flow = flows.get(user_id)
        if flow and flow.stage == "gap" and text and text.strip():
            flow.stage = "finished"
            exercise = GAP_EXERCISES[flow.word.id]
            correct = exercise.accepts(text)
            flow.correct += correct
            client.record_answer(user_id, flow.word, correct)
            await message.answer(
                ("✅ Верно!" if correct else "Ответ неверный. Разберём пропуск.")
                + f"\n\nПравильное слово: {exercise.answers[0]}\n"
                + exercise.completed_sentence
                + (f"\n\n{exercise.explanation}" if not correct else "")
                + "\n\nДалее — следующий шаг или итоги занятия.",
            )
            await advance(message, user_id)
            return
        await message.answer(
            ("Нужен ответ на текущее задание\n\n"
             "Используй кнопки упражнения. В задании с пропуском отправь слово текстом."
             if flow else
             "Выбери занятие\n\n"
             "Нажми кнопку в меню внизу: карточки, мини-тест или практику дня. "
             "Свободная беседа пока недоступна — LLM ещё не подключена.")
            + "\n\n/help — помощь. /stop — закончить занятие."
            + resume_hint(user_id), reply_markup=MENU,
        )

    return router
