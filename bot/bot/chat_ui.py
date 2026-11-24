"""Keep one exercise screen and one optional notice per private chat.

Only IDs observed during this process are used. We never scan chat history.
"""

from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message


class ChatView:
    def __init__(self) -> None:
        self.screens: dict[int, int] = {}
        self.notices: dict[int, int] = {}
        self.kept: set[int] = set()

    async def discard(self, message: Message, message_id: int) -> None:
        try:
            await message.bot.delete_message(message.chat.id, message_id)
        except TelegramAPIError:
            # Expired messages, missing permissions and network failures are harmless.
            pass

    async def consume(self, message: Message) -> None:
        """Remove only a command or input that the router actually handled."""
        await self.discard(message, message.message_id)

    async def show(
        self,
        message: Message,
        text: str,
        *,
        keep: bool = False,
        image: bytes | None = None,
        **kwargs,
    ) -> Message:
        chat_id = message.chat.id
        if image:
            result = await message.answer_photo(
                BufferedInputFile(image, filename="word.jpg"), caption=text, **kwargs
            )
        else:
            result = await message.answer(text, **kwargs)
        previous = self.screens.get(chat_id)
        notice = self.notices.pop(chat_id, None)
        self.screens[chat_id] = result.message_id
        if previous is not None and previous != result.message_id:
            if chat_id in self.kept:
                try:
                    await message.bot.edit_message_reply_markup(
                        chat_id=chat_id, message_id=previous, reply_markup=None
                    )
                except TelegramAPIError:
                    pass
            else:
                await self.discard(message, previous)
        if notice is not None and notice != result.message_id:
            await self.discard(message, notice)
        if keep:
            self.kept.add(chat_id)
        else:
            self.kept.discard(chat_id)
        return result

    async def notice(self, message: Message, text: str, **kwargs) -> Message:
        """Keep the active exercise and its buttons while showing help or statistics."""
        chat_id = message.chat.id
        result = await message.answer(text, **kwargs)
        previous = self.notices.get(chat_id)
        self.notices[chat_id] = result.message_id
        if previous is not None and previous != result.message_id:
            await self.discard(message, previous)
        return result
