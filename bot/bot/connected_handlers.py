"""Private-chat UI. Only transient drafts and exercise state live in this process."""

import re
import secrets
import textwrap
from dataclasses import dataclass, field
from io import BytesIO

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
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
from bot.chat_ui import ChatView
from bot.grammar_ui import GrammarUI
from bot.practice_ui import PracticeUI
from bot.reminder_ui import ReminderUI

BUTTONS = {
    "📖 Словарь": "dictionary",
    "📊 Статистика": "stats",
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
    "⏰ Напоминания": "reminders",
    "💬 Разговор на английском": "talk",
}
MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=label) for label in row]
        for row in (
            ("📖 Словарь", "📝 Мини-тест"),
            ("📊 Статистика",),
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
    section: str = "dictionary"
    image: bytes | None = None
    dialog_id: int | None = None


def make_connected_router(client: BackendClient, website_url: str) -> Router:
    router = Router()
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    flows: dict[int, Flow] = {}
    view = ChatView()
    practice = PracticeUI(client, MENU, view)
    grammar = GrammarUI(client, MENU, view)
    reminders = ReminderUI(client, MENU, view)

    @router.message.outer_middleware()
    async def clean_input(handler, event: Message, data):
        value = (event.text or "").strip()
        command = value.split()[0].split("@")[0] if value else ""
        handled = value in BUTTONS or command in {
            "/start",
            "/dictionary",
            "/addword",
            "/review",
            "/difficult",
            "/quiz",
            "/wordquiz",
            "/stats",
            "/progress",
            "/help",
            "/stop",
            "/cancel",
            "/link",
            "/daily",
            "/level",
            "/talk",
            "/reminders",
        }
        result = await handler(event, data)
        if event.chat.type == ChatType.PRIVATE and handled:
            await view.consume(event)
        return result

    def studying(user_id: int) -> bool:
        flow = flows.get(user_id)
        return bool(
            flow
            and flow.stage != "dictionary"
            or user_id in practice.active
            or user_id in grammar.flows
            or user_id in reminders.flows
        )

    connect_help = (
        "Открой сайт " + website_url + ", войди в свой аккаунт и в разделе «Словарь» "
        "нажми «Подключить Telegram». Открой полученную ссылку и нажми «Запустить». "
        "Ссылка действует 10 минут. Пароль от сайта в боте вводить не нужно."
    )

    async def error(message: Message, user_id: int, exc: BackendError) -> None:
        flows.pop(user_id, None)
        practice.cancel_local(user_id)
        grammar.cancel_local(user_id)
        reminders.cancel_local(user_id)
        text = {
            403: "Аккаунт Telegram ещё не подключён.\n\n" + connect_help,
            401: "Служебная авторизация бота не настроена. Обратись к разработчику.",
            409: "Слово уже существует или задание изменилось. Открой раздел заново.",
            412: "Личный словарь пуст. Добавь слова через /dictionary, затем открой занятие.",
            400: "Ссылка истекла или уже использована. Получи новую на сайте.",
            404: "Этого слова уже нет в личном словаре. Открой /dictionary заново.",
            422: "Проверь введённое слово и перевод. Начать заново: /addword.",
        }.get(
            exc.status,
            (
                "Сервер недоступен. Попробуй позже.\n\n"
                "Если сохранял слово или ответ, проверь результат перед повтором."
            ),
        )
        await view.show(message, text, reply_markup=MENU)

    async def dialog_error(message: Message, user_id: int, exc: BackendError) -> None:
        if exc.status in (401, 403):
            await error(message, user_id, exc)
            return
        if exc.status == 404:
            flows.pop(user_id, None)
            await view.show(
                message, "Разговор не найден. Выбери сценарий через /talk.", reply_markup=MENU
            )
            return
        text = {
            409: "Продолжить этот диалог уже нельзя. Нажми /stop, чтобы получить итог.",
            422: "Эмма не смогла ответить на этот запрос. Попробуй переформулировать.",
        }.get(exc.status, "Эмма временно недоступна. Проверь историю на сайте и попробуй позже.")
        await view.notice(message, text)

    async def show_dialog_text(
        message: Message, text: str, markup: InlineKeyboardMarkup | ReplyKeyboardMarkup
    ) -> None:
        # Even long feedback fits Telegram's 4096-character limit, including emoji.
        parts = textwrap.wrap(text, width=2000, replace_whitespace=False, expand_tabs=False)
        for index, part in enumerate(parts):
            await view.show(
                message, part, keep=True, reply_markup=markup if index == len(parts) - 1 else None
            )

    def finish_button(flow: Flow) -> InlineKeyboardMarkup:
        return keyboard([[("Завершить и получить отзыв", f"talkend:{flow.ticket}")]])

    async def finish_talk(message: Message, user_id: int, dialog_id: int) -> None:
        result = await client.finish_dialog(user_id, dialog_id)
        flows.pop(user_id, None)
        await show_dialog_text(message, result.summary or "Разговор завершён.", MENU)

    async def home(message: Message, user_id: int, prefix: str = "") -> None:
        flows.pop(user_id, None)
        name = await client.me(user_id)
        await view.show(
            message,
            prefix + f"Привет, {name}!\n\n"
            "📖 Словарь — слова и карточки.\n"
            "📝 Мини-тест — задания и сложные слова.\n"
            "📊 Статистика — результаты обучения.\n\n"
            "Выбери раздел внизу.",
            reply_markup=MENU,
        )

    async def dictionary(message: Message, user_id: int, page: int = 0, prefix: str = "") -> None:
        result = await client.dictionary(user_id, page)
        last = max(0, (result.total - 1) // result.page_size)
        if page > last:
            result = await client.dictionary(user_id, last)
        flow = Flow("dictionary", page=result.page, words=[row.word for row in result.items])
        flows[user_id] = flow
        text = prefix + f"📖 Словарь · всего: {result.total}\n\n"
        text += "\n".join(f"{i}. {w.text} — {w.translation}" for i, w in enumerate(flow.words, 1))
        if not flow.words:
            text += "Пока пусто. Добавь своё слово или слова темы на сайте."
        rows = [[("📚 Карточки слов", f"review:{flow.ticket}")]] if flow.words else []
        management = [("➕ Добавить", f"add:{flow.ticket}")]
        if flow.words:
            management.append(("🗑 Удалить", f"delete:{flow.ticket}"))
        rows.append(management)
        navigation = []
        if result.page > 0:
            navigation.append(("← Назад", f"page:{flow.ticket}:{result.page - 1}"))
        if result.page < last:
            navigation.append(("Вперёд →", f"page:{flow.ticket}:{result.page + 1}"))
        if navigation:
            text += f"\n\nСтраница {result.page + 1} из {last + 1}"
            rows.append(navigation)
        rows.append([("← Меню", f"home:{flow.ticket}")])
        await view.show(message, text, keep=bool(prefix), reply_markup=keyboard(rows))

    async def show_card(message: Message, user_id: int, prefix: str = "") -> None:
        flow = flows[user_id]
        if flow.position == len(flow.words):
            flows.pop(user_id, None)
            await view.show(
                message,
                prefix + f"✅ Готово! Карточек пройдено: {len(flow.words)}.",
                keep=True,
                reply_markup=MENU,
            )
            return
        flow.stage = "reveal"
        flow.ticket = secrets.token_hex(8)
        word = flow.words[flow.position]
        image = None
        if word.image_url:
            try:
                image = await client.image(user_id, word.id)
            except BackendError:
                prefix += "Картинка временно недоступна.\n\n"
        await view.show(
            message,
            prefix
            + f"📚 Карточка {flow.position + 1} из {len(flow.words)}\n\n"
            + flow.words[flow.position].text
            + "\n\nВспомни перевод.",
            keep=True,
            image=image,
            reply_markup=keyboard(
                [
                    [("Показать перевод", f"reveal:{flow.ticket}")],
                    [("← Назад", f"back:{flow.ticket}")],
                ]
            ),
        )

    async def action(message: Message, user_id: int, name: str) -> None:
        if name == "help":
            send = view.notice if studying(user_id) else view.show
            await send(
                message,
                "❓ Помощь\n\n"
                "Словарь — добавление и удаление слов, карточки.\n"
                "Мини-тест — грамматика, тест по словам и сложные слова.\n"
                "Статистика — количество слов и результаты ответов.\n\n"
                "/start — меню · /stop — выйти из задания\n"
                "/link — подключить аккаунт сайта\n"
                "/talk — поговорить с Эммой и получить исправления\n"
                "/reminders — настроить напоминания\n\n"
                "Слова и результаты общие с сайтом."
                + ("\n\nЗадание остаётся выше — можно продолжить." if studying(user_id) else ""),
                reply_markup=MENU,
            )
            return
        if name in ("progress", "stats"):
            await practice.progress(message, user_id, keep_screen=studying(user_id))
            return
        current = flows.get(user_id)
        if current and current.dialog_id is not None:
            if name == "stop":
                try:
                    await finish_talk(message, user_id, current.dialog_id)
                except BackendError as exc:
                    await dialog_error(message, user_id, exc)
                return
            if name == "talk":
                await view.notice(
                    message, "Разговор уже открыт. Напиши Эмме или нажми /stop для отзыва."
                )
                return
        flows.pop(user_id, None)
        practice.cancel_local(user_id)
        grammar.cancel_local(user_id)
        reminders.cancel_local(user_id)
        if name == "quiz":
            await grammar.show_menu(message, user_id)
        elif name == "wordquiz":
            await practice.start(message, user_id, "quiz")
        elif name == "daily":
            await practice.start(message, user_id, "daily")
        elif name == "level":
            await practice.level(message, user_id)
        elif name == "reminders":
            await reminders.show(message, user_id)
        elif name == "start":
            await home(message, user_id)
        elif name in ("cancel", "stop"):
            await view.show(
                message, "Занятие остановлено. Результаты сохранены.", reply_markup=MENU
            )
        elif name == "link":
            await view.show(message, connect_help, reply_markup=MENU)
        elif name == "dictionary":
            await dictionary(message, user_id)
        elif name == "addword":
            await client.me(user_id)
            flows[user_id] = Flow("word")
            await view.show(
                message,
                "➕ Новое слово\n\nНапиши слово по-английски. /cancel — отмена.",
                reply_markup=MENU,
            )
        elif name in ("review", "difficult"):
            words = await client.cards(user_id, difficult=name == "difficult")
            if not words:
                await view.show(
                    message,
                    "Сложных слов за последние 30 дней нет."
                    if name == "difficult"
                    else "Словарь пуст. Добавь слова, чтобы открыть карточки.",
                    reply_markup=MENU,
                )
                return
            flows[user_id] = Flow(
                "reveal", words=words, section="quiz" if name == "difficult" else "dictionary"
            )
            await show_card(message, user_id)
        elif name == "talk":
            try:
                scenarios = await client.dialog_scenarios(user_id)
            except BackendError as exc:
                await dialog_error(message, user_id, exc)
                return
            flow = Flow("talk_pick")
            flows[user_id] = flow
            await view.show(
                message,
                "💬 Разговор с Эммой\n\nВыбери сценарий и пиши по-английски. "
                "Эмма ответит и объяснит ошибки.",
                reply_markup=keyboard(
                    [[(s.title, f"talkstart:{flow.ticket}:{s.code}")] for s in scenarios]
                ),
            )

    @router.message(CommandStart())
    async def start(message: Message, command: CommandObject) -> None:
        user_id = message.from_user.id
        flows.pop(user_id, None)
        practice.cancel_local(user_id)
        grammar.cancel_local(user_id)
        reminders.cancel_local(user_id)
        try:
            prefix = ""
            if command.args:
                if not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", command.args):
                    await view.show(
                        message, "Некорректная ссылка. Получи новую на сайте.", reply_markup=MENU
                    )
                    return
                name = await client.link(user_id, command.args)
                prefix = f"✅ Telegram подключён к аккаунту {name}.\n\n"
            await home(message, user_id, prefix)
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
            "stats",
            "reminders",
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
        if (query.data or "").startswith("reminder:"):
            try:
                await reminders.callback(query, user_id)
            except BackendError as exc:
                await error(query.message, user_id, exc)
            return
        if (query.data or "").startswith(
            (
                "gtopic:",
                "gmix:",
                "gwords:",
                "gdifficult:",
                "gsite:",
                "gback:",
                "ghome:",
                "gthemes:",
                "gagain:",
                "gnext:",
                "gchoice:",
            )
        ):
            try:
                outcome = await grammar.callback(query)
                if outcome == "home":
                    await action(query.message, user_id, "start")
                elif outcome == "words":
                    await action(query.message, user_id, "wordquiz")
                elif outcome == "difficult":
                    await action(query.message, user_id, "difficult")
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
            or (stage == "choose_delete" and name in ("pickdelete", "cancel"))
            or (stage == "confirm_add" and name in ("save", "cancel", "picture"))
            or (stage == "confirm_delete" and name in ("remove", "cancel"))
            or (stage == "reveal" and name == "reveal")
            or (stage == "rate" and name == "rate")
            or (stage in ("reveal", "rate") and name == "back")
            or (stage == "talk_pick" and name == "talkstart" and len(parts) == 3)
            or (stage == "talk" and name == "talkend" and flow.dialog_id is not None)
        )
        if not allowed:
            await query.answer("Используй последнее задание или меню.")
            return
        flow.stage = "busy"
        await query.answer()
        try:
            if name == "talkstart":
                dialog = await client.start_dialog(user_id, parts[2])
                flow = Flow("talk", dialog_id=dialog.id)
                flows[user_id] = flow
                await show_dialog_text(
                    message=query.message,
                    text="Эмма: " + dialog.messages[0].content,
                    markup=finish_button(flow),
                )
            elif name == "talkend":
                await finish_talk(query.message, user_id, flow.dialog_id)
            elif name == "page" and len(parts) == 3 and parts[2].isdigit():
                await dictionary(query.message, user_id, min(int(parts[2]), 100000))
            elif name == "cancel":
                await dictionary(query.message, user_id, flow.page)
            elif name == "back":
                await action(query.message, user_id, flow.section)
            elif name in ("add", "review", "home"):
                await action(
                    query.message, user_id, {"add": "addword", "home": "start"}.get(name, name)
                )
            elif name == "delete" and len(parts) == 2:
                selection = Flow("choose_delete", page=flow.page, words=flow.words)
                flows[user_id] = selection
                await view.show(
                    query.message,
                    "🗑 Удалить слово\n\nВыбери слово из списка.",
                    reply_markup=keyboard(
                        [
                            [
                                (
                                    f"{w.text} — {w.translation}"[:60],
                                    f"pickdelete:{selection.ticket}:{w.id}",
                                )
                            ]
                            for w in flow.words
                        ]
                        + [[("← Словарь", f"cancel:{selection.ticket}")]]
                    ),
                )
            elif name == "pickdelete" and len(parts) == 3 and parts[2].isdigit():
                word = next((w for w in flow.words if w.id == int(parts[2])), None)
                if word is None:
                    flow.stage = stage
                    return
                flows[user_id] = confirmation = Flow("confirm_delete", page=flow.page, words=[word])
                await view.show(
                    query.message,
                    f"Удалить «{word.text} — {word.translation}»?\n\n"
                    "История повторений этого слова тоже будет удалена.",
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
                await dictionary(query.message, user_id, flow.page, "Слово удалено.\n\n")
            elif name == "save":
                saved = await client.add_word(user_id, flow.text, flow.translation)
                if flow.image:
                    try:
                        await client.upload_image(user_id, saved["word"]["id"], flow.image)
                    except (BackendError, KeyError, TypeError):
                        await dictionary(
                            query.message,
                            user_id,
                            prefix="Слово добавлено, но картинка не сохранилась. "
                            "Её можно добавить в словаре на сайте.\n\n",
                        )
                        return
                await dictionary(query.message, user_id, prefix="Слово добавлено.\n\n")
            elif name == "picture":
                flow.stage = "image"
                flow.ticket = secrets.token_hex(8)
                await view.show(query.message, "Пришли фотографию до 5 МБ. /cancel — отмена.")
            elif name == "reveal":
                flow.stage = "rate"
                flow.ticket = secrets.token_hex(8)
                word = flow.words[flow.position]
                await view.show(
                    query.message,
                    f"{word.text} — {word.translation}\n\nОцени, как вспомнился перевод.",
                    keep=True,
                    reply_markup=keyboard(
                        [
                            [(RATINGS[q], f"rate:{flow.ticket}:{q}") for q in row]
                            for row in ((1, 3), (4, 5))
                        ]
                        + [[("← Назад", f"back:{flow.ticket}")]]
                    ),
                )
            elif name == "rate" and len(parts) == 3 and parts[2] in ("1", "3", "4", "5"):
                result = await client.review(user_id, flow.words[flow.position].id, int(parts[2]))
                flow.position += 1
                await show_card(
                    query.message,
                    user_id,
                    f"✓ {flow.words[flow.position - 1].text} · {RATINGS[int(parts[2])]}\n"
                    f"Перевод: {flow.words[flow.position - 1].translation}\n"
                    f"Повторение: {result.next_review_at:%d.%m.%Y %H:%M} UTC.\n\n",
                )
            else:
                flow.stage = stage
        except BackendError as exc:
            if name in ("talkstart", "talkend"):
                flow.stage = stage
                await dialog_error(query.message, user_id, exc)
            else:
                await error(query.message, user_id, exc)

    @router.message()
    async def text(message: Message) -> None:
        user_id = message.from_user.id
        value = (message.text or "").strip()
        flow = flows.get(user_id)
        if message.photo and flow and flow.stage in ("image", "confirm_add"):
            photo = message.photo[-1]
            if photo.file_size and photo.file_size > 5 * 1024 * 1024:
                await view.notice(message, "Картинка должна быть не больше 5 МБ.")
                return
            buffer = BytesIO()
            try:
                await message.bot.download(photo, destination=buffer)
            except TelegramAPIError:
                await view.notice(message, "Не удалось загрузить фото. Отправь его ещё раз.")
                return
            if buffer.tell() > 5 * 1024 * 1024:
                await view.notice(message, "Картинка должна быть не больше 5 МБ.")
                return
            flow.image = buffer.getvalue()
            flow.stage = "confirm_add"
            flow.ticket = secrets.token_hex(8)
            await view.show(
                message,
                f"{flow.text} — {flow.translation}\n\nСохранить слово с картинкой?",
                image=flow.image,
                keep=True,
                reply_markup=keyboard(
                    [
                        [
                            ("Сохранить", f"save:{flow.ticket}"),
                            ("Отмена", f"cancel:{flow.ticket}"),
                        ]
                    ]
                ),
            )
            return
        if flow and flow.stage == "image":
            await view.notice(message, "Отправь картинку как фото. /cancel — отмена.")
            return
        if value.startswith("/"):
            await view.notice(
                message, "Команда не распознана. /help — помощь; /stop — выйти из задания."
            )
            return
        if flow and flow.stage == "talk" and flow.dialog_id is not None:
            if not value or len(value) > 1000:
                await view.notice(message, "Напиши Эмме текст от 1 до 1000 символов.")
                return
            try:
                turn = await client.dialog_message(user_id, flow.dialog_id, value)
            except BackendError as exc:
                await dialog_error(message, user_id, exc)
                return
            lines = ["Эмма: " + turn.reply.content]
            if turn.user_message.corrections:
                lines.append("\nИсправления")
                for fix in turn.user_message.corrections:
                    lines.append(f"• {fix.fragment} → {fix.correction}")
                    if fix.explanation:
                        lines.append(fix.explanation)
            await show_dialog_text(message, "\n".join(lines), finish_button(flow))
            return
        if flow and flow.stage == "talk_pick":
            await view.notice(message, "Выбери сценарий кнопкой выше.")
            return
        try:
            if await reminders.text(message, user_id):
                return
            if await grammar.text(message, user_id):
                return
            if await practice.text(message, user_id):
                return
        except BackendError as exc:
            await error(message, user_id, exc)
            return
        if flow is None or flow.stage not in ("word", "translation"):
            await view.notice(
                message, "Выбери «Словарь», «Мини-тест» или «Статистика» внизу.", reply_markup=MENU
            )
            return
        limit = 100 if flow.stage == "word" else 200
        if not value or len(value) > limit:
            await view.show(message, f"Введи непустой текст до {limit} символов. /cancel — отмена.")
            return
        if flow.stage == "word":
            if not re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", value):
                await view.show(
                    message, "Напиши слово латиницей; допустимы пробел, дефис и апостроф."
                )
                return
            flow.text, flow.stage = value, "translation"
            await view.show(message, f"{flow.text}\n\nТеперь напиши перевод. /cancel — отмена.")
        else:
            flow.translation, flow.stage = value, "confirm_add"
            flow.ticket = secrets.token_hex(8)
            await view.show(
                message,
                f"Добавить «{flow.text} — {flow.translation}» в личный словарь?",
                keep=True,
                reply_markup=keyboard(
                    [
                        [("📷 Добавить картинку", f"picture:{flow.ticket}")],
                        [("Сохранить", f"save:{flow.ticket}"), ("Отмена", f"cancel:{flow.ticket}")],
                    ]
                ),
            )

    return router
