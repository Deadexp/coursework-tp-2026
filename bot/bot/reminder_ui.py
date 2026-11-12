"""Private-chat reminder settings. IANA timezone validation is done by the backend."""

import re
import secrets
from dataclasses import dataclass

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import BackendClient, BackendError, ReminderSettings

TIME_PATTERN = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"


@dataclass
class ReminderFlow:
    ticket: str
    settings: ReminderSettings
    stage: str = "menu"
    new_time: str = ""


class ReminderUI:
    def __init__(self, backend: BackendClient, menu) -> None:
        self.backend, self.menu = backend, menu
        self.flows: dict[int, ReminderFlow] = {}

    def cancel_local(self, user_id: int) -> None:
        self.flows.pop(user_id, None)

    async def show(self, message: Message, user_id: int, settings=None) -> None:
        settings = settings or await self.backend.reminder_settings(user_id)
        ticket = secrets.token_hex(8)
        self.flows[user_id] = ReminderFlow(ticket, settings)
        toggle = "off" if settings.enabled else "on"
        await message.answer(
            "⏰ Напоминания " + ("включены" if settings.enabled else "выключены") + ".\n\n"
            f"Время: {settings.time}\nЧасовой пояс: {settings.timezone}\n\n"
            "Одно плановое напоминание в день. Если компьютер с ботом выключен, "
            "сообщение не придёт; после запуска возможна доставка в течение часа от выбранного времени.\n"
            "Включение — только по твоему выбору. /stop — выйти из настройки.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Выключить" if settings.enabled else "Включить",
                            callback_data=f"reminder:{ticket}:{toggle}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Изменить время и часовой пояс",
                            callback_data=f"reminder:{ticket}:edit",
                        )
                    ],
                ]
            ),
        )

    async def callback(self, query: CallbackQuery, user_id: int) -> bool:
        if not (query.data or "").startswith("reminder:"):
            return False
        parts = query.data.split(":")
        flow = self.flows.get(user_id)
        if len(parts) != 3 or flow is None or parts[1] != flow.ticket:
            await query.answer("Кнопка устарела. Открой /reminders.")
            return True
        action = parts[2]
        if action not in ("on", "off", "edit"):
            await query.answer("Открой /reminders.")
            return True
        await query.answer()
        if action == "edit":
            flow.stage = "time"
            flow.ticket = secrets.token_hex(8)
            await query.message.answer(
                "Введи время в формате ЧЧ:ММ, например 19:00. /stop — отмена."
            )
        else:
            settings = await self.backend.reminder_settings(user_id, enabled=action == "on")
            await self.show(query.message, user_id, settings)
        return True

    async def text(self, message: Message, user_id: int) -> bool:
        flow = self.flows.get(user_id)
        if flow is None or flow.stage == "menu":
            return False
        value = (message.text or "").strip()
        if flow.stage == "time":
            if not re.fullmatch(TIME_PATTERN, value):
                await message.answer(
                    "Нужно время от 00:00 до 23:59, например 19:00. /stop — отмена."
                )
                return True
            flow.new_time = value
            flow.stage = "timezone"
            await message.answer(
                "Введи часовой пояс IANA: например Europe/Moscow, Europe/Berlin или Asia/Yekaterinburg.\n"
                f"Чтобы оставить {flow.settings.timezone}, отправь «оставить». /stop — отмена."
            )
            return True
        timezone = flow.settings.timezone if value.lower() == "оставить" else value
        if not timezone or len(timezone) > 100:
            await message.answer("Введи часовой пояс IANA, например Europe/Moscow.")
            return True
        try:
            settings = await self.backend.reminder_settings(
                user_id, time=flow.new_time, timezone=timezone
            )
        except BackendError as error:
            if error.status != 422:
                raise
            await message.answer(
                "Такой часовой пояс не найден. Пример: Europe/Moscow. /stop — отмена."
            )
            return True
        await message.answer("Время и часовой пояс сохранены на сервере.", reply_markup=self.menu)
        await self.show(message, user_id, settings)
        return True
