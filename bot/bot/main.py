import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import settings

dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("Hi! Привяжи аккаунт с сайта, чтобы повторять свои слова.")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(Bot(settings.bot_token))


if __name__ == "__main__":
    asyncio.run(main())
