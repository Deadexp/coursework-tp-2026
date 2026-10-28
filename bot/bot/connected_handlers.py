"""Private-chat UI. Only transient drafts and exercise state live in this process."""

import re
import secrets
from dataclasses import dataclass, field

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.api_client import BackendClient, BackendError, Word
from bot.grammar_ui import GrammarUI
from bot.practice_ui import PracticeUI

BUTTONS = {
    "📖 Мой словарь": "dictionary",
    "➕ Добавить слово": "addword",
    "📚 Карточки слов": "review",
    "🔁 Сложные слова": "difficult",
    "🏠 Главное меню": "start",
    "❓ Помощь": "help",
    "📝 Мини-тест": "quiz",
    "☀️ Практика дня": "daily",
    "📊 Мой прогресс": "progress",
    "🎚 Уровень": "level",
    "💬 Разговор на английском": "talk",
}
MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=label) for label in row]
        for row in (
            ("📖 Мой словарь", "➕ Добавить слово"),
            ("📚 Карточки слов", "📝 Мини-тест"),
            ("🔁 Сложные слова", "☀️ Практика дня"),
            ("📊 Мой прогресс", "🎚 Уровень"),
            ("💬 Разговор на английском",),
            ("🏠 Главное меню", "❓ Помощь"),
        )
    ],
    resize_keyboard=True,
)
RATINGS = {1: "Не помню", 3: "С трудом", 4: "Помню", 5: "Легко"}


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


@dataclass
class Flow:
    stage: str
    ticket: str = field(default_factory=lambda: secrets.token_hex(8))
    page: int = 0
    text: str = ""
    translation: str = ""
    words: list[Word] = field(default_factory=list)
    position: int = 0


def make_connected_router(client: BackendClient, website_url: str) -> Router:
    router = Router()
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    flows: dict[int, Flow] = {}
    practice = PracticeUI(client, MENU)
    grammar = GrammarUI(client, MENU)
    connect_help = (
        "Открой сайт " + website_url + ", войди в свой аккаунт и в разделе «Словарь» "
        "нажми «Подключить Telegram». Открой полученную ссылку и нажми «Запустить». "
        "Ссылка действует 10 минут. Пароль от сайта в боте вводить не нужно."
    )

    async def error(message: Message, user_id: int, exc: BackendError) -> None:
        flows.pop(user_id, None)
        practice.cancel_local(user_id)
        grammar.cancel_local(user_id)
        text = {
            403: "Аккаунт Telegram ещё не подключён.\n\n" + connect_help,
            401: "Служебная авторизация бота не настроена. Обратись к разработчику.",
            409: "Запись уже существует либо задание изменилось. Открой нужный раздел заново. Уже записанные результаты сохранены.",
            412: "Личный словарь пуст. Добавь слова через /dictionary, затем открой занятие.",
            400: "Ссылка истекла или уже использована. Получи новую на сайте.",
            404: "Этого слова уже нет в личном словаре. Открой /dictionary заново.",
            422: "Проверь введённое слово и перевод. Начать заново: /addword.",
        }.get(
            exc.status,
            (
                "Сервер недоступен или вернул неверный ответ. Учебные слова не подставляются. "
                "Повтори запрос позже. Если сохранял ответ или слово, сначала проверь /dictionary: "
                "сервер мог получить запрос до обрыва связи."
            ),
        )
        await message.answer(text, reply_markup=MENU)

    async def home(message: Message, user_id: int) -> None:
        flows.pop(user_id, None)
        name = await client.me(user_id)
        await message.answer(
            f"Привет, {name}! Это подключённый режим.\n\n"
            "Сайт и бот используют один личный словарь. Добавляй и удаляй слова, "
            "повторяй карточки, решай мини-тест и практику дня. Прогресс и уровень хранятся на общем сервере.\n\n"
            "Выбери раздел в меню.",
            reply_markup=MENU,
        )

    async def dictionary(message: Message, user_id: int, page: int = 0) -> None:
        result = await client.dictionary(user_id, page)
        last = max(0, (result.total - 1) // result.page_size)
        if page > last:
            result = await client.dictionary(user_id, last)
        flow = Flow("dictionary", page=result.page, words=[row.word for row in result.items])
        flows[user_id] = flow
        text = (
            f"📖 Мой словарь · страница {result.page + 1} из {last + 1}\n"
            f"Всего слов: {result.total}\n\n"
        )
        text += "\n".join(f"{i}. {w.text} — {w.translation}" for i, w in enumerate(flow.words, 1))
        if not flow.words:
            text += "Пока пусто. Добавь своё слово или слова темы на сайте."
        rows = [
            [(f"Удалить №{i}", f"delete:{flow.ticket}:{w.id}")] for i, w in enumerate(flow.words, 1)
        ]
        navigation = []
        if result.page > 0:
            navigation.append(("← Назад", f"page:{flow.ticket}:{result.page - 1}"))
        if result.page < last:
            navigation.append(("Вперёд →", f"page:{flow.ticket}:{result.page + 1}"))
        if navigation:
            rows.append(navigation)
        rows.extend(
            [
                [("➕ Добавить слово", f"add:{flow.ticket}")],
                [
                    ("📚 Повторить", f"review:{flow.ticket}"),
                    ("Главное меню", f"home:{flow.ticket}"),
                ],
            ]
        )
        await message.answer(text, reply_markup=keyboard(rows))

    async def show_card(message: Message, user_id: int) -> None:
        flow = flows[user_id]
        if flow.position == len(flow.words):
            flows.pop(user_id, None)
            await message.answer(
                "Занятие завершено. Все оценки сохранены на сервере. "
                "Открой карточки снова, чтобы получить следующую пачку.",
                reply_markup=MENU,
            )
            return
        flow.stage = "reveal"
        flow.ticket = secrets.token_hex(8)
        await message.answer(
            f"📚 Карточка {flow.position + 1} из {len(flow.words)}\n\n"
            + flow.words[flow.position].text
            + "\n\nВспомни перевод.",
            reply_markup=keyboard([[("Показать перевод", f"reveal:{flow.ticket}")]]),
        )

    async def action(message: Message, user_id: int, name: str) -> None:
        if name == "help":
            await message.answer(
                "Подключённый режим\n\n/dictionary — личный словарь и удаление.\n"
                "/addword — слово → перевод → подтверждение.\n/review — карточки к повторению.\n"
                "/difficult — слова с ошибками за последние 30 дней.\n"
                "/cancel или /stop — отмена. /start — главное меню.\n/link — подключение.\n\n"
                "Интервалы считает сервер по SM-2. На сайте обнови список для новых данных. "
                "Помощь и прогресс не прерывают занятие.\n"
                "/quiz — грамматика сайта: выбор темы или смешанный тест, до 5 заданий.\n"
                "Выбор — кнопками; пропуск, перевод и сборка предложения — текстом.\n"
                "/wordquiz — сохранённый тест по личным словам.\n"
                "/daily — до 3 карточек и до 2 заданий на ввод; если слов мало, занятие короче.\n"
                "При наличии примера будет пропуск, иначе ввод по переводу.\n"
                "/progress — общие результаты; /level — уровень аккаунта.\n"
                "Тест по словам и практика дня продолжаются после перезапуска. "
                "Незавершённый тест по грамматике после перезапуска нужно начать заново; "
                "принятые ответы остаются. Новый день — по UTC (03:00 по Москве). "
                "LLM в боте пока не подключена; деморежим запускается отдельно.",
                reply_markup=MENU,
            )
            return
        if name == "progress":
            await practice.progress(message, user_id)
            return
        flows.pop(user_id, None)
        practice.cancel_local(user_id)
        grammar.cancel_local(user_id)
        if name == "quiz":
            await grammar.topics(message, user_id)
        elif name == "wordquiz":
            await practice.start(message, user_id, "quiz")
        elif name == "daily":
            await practice.start(message, user_id, "daily")
        elif name == "level":
            await practice.level(message, user_id)
        elif name == "start":
            await home(message, user_id)
        elif name in ("cancel", "stop"):
            await message.answer(
                "Действие отменено. Уже сохранённые данные остаются на сервере.", reply_markup=MENU
            )
        elif name == "link":
            await message.answer(connect_help, reply_markup=MENU)
        elif name == "dictionary":
            await dictionary(message, user_id)
        elif name == "addword":
            await client.me(user_id)
            flows[user_id] = Flow("word")
            await message.answer(
                "Введи английское слово (до 100 символов). /cancel — отмена.", reply_markup=MENU
            )
        elif name in ("review", "difficult"):
            words = await client.cards(user_id, difficult=name == "difficult")
            if not words:
                await message.answer(
                    "Сложных слов за последние 30 дней нет."
                    if name == "difficult"
                    else "Сейчас нет слов к повторению. Добавь слова в /dictionary или вернись позже.",
                    reply_markup=MENU,
                )
                return
            flows[user_id] = Flow("reveal", words=words)
            await show_card(message, user_id)
        else:
            await message.answer(
                "Разговор с LLM в боте пока не подключён. Выбери мини-тест, практику дня или карточки.",
                reply_markup=MENU,
            )

    @router.message(CommandStart())
    async def start(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id
        flows.pop(user_id, None)
        practice.cancel_local(user_id)
        grammar.cancel_local(user_id)
        try:
            if command.args:
                if not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", command.args):
                    await message.answer(
                        "Некорректная ссылка. Получи новую на сайте.", reply_markup=MENU
                    )
                    return
                name = await client.link(user_id, command.args)
                await message.answer(
                    f"Telegram подключён к аккаунту {name}. Общий словарь доступен!",
                    reply_markup=MENU,
                )
            await home(message, user_id)
        except BackendError as exc:
            await error(message, user_id, exc)

    @router.message(
        Command(
            "dictionary",
            "addword",
            "review",
            "difficult",
            "help",
            "link",
            "cancel",
            "stop",
            "quiz",
            "wordquiz",
            "daily",
            "talk",
            "level",
            "progress",
        )
    )
    @router.message(F.text.in_(BUTTONS))
    async def menu(message: Message) -> None:
        name = BUTTONS.get(message.text) or message.text.split()[0].split("@")[0][1:]
        try:
            await action(message, message.from_user.id, name)
        except BackendError as exc:
            await error(message, message.from_user.id, exc)

    @router.callback_query()
    async def callback(query: CallbackQuery) -> None:
        user_id = query.from_user.id
        if (query.data or "").startswith(
            ("gtopic:", "gmix:", "gwords:", "ghome:", "gthemes:", "gagain:", "gnext:", "gchoice:")
        ):
            try:
                outcome = await grammar.callback(query)
                if outcome == "home":
                    await action(query.message, user_id, "start")
                elif outcome == "words":
                    await action(query.message, user_id, "wordquiz")
            except BackendError as exc:
                await error(query.message, user_id, exc)
            return
        if (query.data or "").startswith(("preveal:", "prate:", "pchoice:", "plevel:")):
            try:
                await practice.callback(query)
            except BackendError as exc:
                await error(query.message, user_id, exc)
            return
        flow = flows.get(user_id)
        parts = (query.data or "").split(":")
        if flow is None or len(parts) < 2 or parts[1] != flow.ticket:
            await query.answer("Кнопка устарела. Открой /dictionary или последнее задание.")
            return
        name = parts[0]
        # Consume the stage before the first await, even in duplicate deliveries.
        stage = flow.stage
        allowed = (
            (stage == "dictionary" and name in ("page", "delete", "add", "review", "home"))
            or (stage == "confirm_add" and name in ("save", "cancel"))
            or (stage == "confirm_delete" and name in ("remove", "cancel"))
            or (stage == "reveal" and name == "reveal")
            or (stage == "rate" and name == "rate")
        )
        if not allowed:
            await query.answer("Используй последнее задание или меню.")
            return
        flow.stage = "busy"
        await query.answer()
        try:
            if name == "page" and len(parts) == 3 and parts[2].isdigit():
                await dictionary(query.message, user_id, min(int(parts[2]), 100000))
            elif name in ("add", "review", "home", "cancel"):
                await action(
                    query.message, user_id, {"add": "addword", "home": "start"}.get(name, name)
                )
            elif name == "delete" and len(parts) == 3 and parts[2].isdigit():
                word = next((w for w in flow.words if w.id == int(parts[2])), None)
                if word is None:
                    flow.stage = stage
                    return
                flows[user_id] = confirmation = Flow("confirm_delete", page=flow.page, words=[word])
                await query.message.answer(
                    f"Удалить «{word.text} — {word.translation}» из твоего словаря? "
                    "Его история повторений тоже будет удалена. Словари других пользователей останутся.",
                    reply_markup=keyboard(
                        [
                            [
                                ("Удалить", f"remove:{confirmation.ticket}"),
                                ("Отмена", f"cancel:{confirmation.ticket}"),
                            ]
                        ]
                    ),
                )
            elif name == "remove":
                await client.remove_word(user_id, flow.words[0].id)
                await query.message.answer("Слово удалено из личного словаря.")
                await dictionary(query.message, user_id, flow.page)
            elif name == "save":
                await client.add_word(user_id, flow.text, flow.translation)
                await query.message.answer(
                    "Слово добавлено. Оно появится на сайте после обновления списка."
                )
                await dictionary(query.message, user_id)
            elif name == "reveal":
                flow.stage = "rate"
                flow.ticket = secrets.token_hex(8)
                word = flow.words[flow.position]
                await query.message.answer(
                    f"{word.text} — {word.translation}\n\nОцени, как вспомнился перевод.",
                    reply_markup=keyboard(
                        [
                            [(RATINGS[q], f"rate:{flow.ticket}:{q}") for q in row]
                            for row in ((1, 3), (4, 5))
                        ]
                    ),
                )
            elif name == "rate" and len(parts) == 3 and parts[2] in ("1", "3", "4", "5"):
                result = await client.review(user_id, flow.words[flow.position].id, int(parts[2]))
                await query.message.answer(
                    "Оценка сохранена на сервере (источник: bot).\n"
                    f"Следующее повторение: {result.next_review_at:%d.%m.%Y %H:%M %Z}. "
                    "Дата рассчитана по SM-2.",
                )
                flow.position += 1
                await show_card(query.message, user_id)
            else:
                flow.stage = stage
        except BackendError as exc:
            await error(query.message, user_id, exc)

    @router.message()
    async def text(message: Message) -> None:
        user_id = message.from_user.id
        value = (message.text or "").strip()
        flow = flows.get(user_id)
        if value.startswith("/"):
            await message.answer("Команда не распознана. /help — помощь; /cancel — отмена.")
            return
        try:
            if await grammar.text(message, user_id):
                return
            if await practice.text(message, user_id):
                return
        except BackendError as exc:
            await error(message, user_id, exc)
            return
        if flow is None or flow.stage not in ("word", "translation"):
            await message.answer(
                "Выбери /dictionary, /addword или кнопки последнего задания.", reply_markup=MENU
            )
            return
        limit = 100 if flow.stage == "word" else 200
        if not value or len(value) > limit:
            await message.answer(f"Введи непустой текст до {limit} символов. /cancel — отмена.")
            return
        if flow.stage == "word":
            if not re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", value):
                await message.answer("Напиши слово латиницей; допустимы пробел, дефис и апостроф.")
                return
            flow.text, flow.stage = value, "translation"
            await message.answer("Теперь введи перевод (до 200 символов). /cancel — отмена.")
        else:
            flow.translation, flow.stage = value, "confirm_add"
            flow.ticket = secrets.token_hex(8)
            await message.answer(
                f"Добавить «{flow.text} — {flow.translation}» в личный словарь?",
                reply_markup=keyboard(
                    [[("Сохранить", f"save:{flow.ticket}"), ("Отмена", f"cancel:{flow.ticket}")]]
                ),
            )

    return router
