from app.llm.base import Message


class StubLLM:
    """Заглушка для разработки и тестов без API-ключа."""

    async def chat(self, messages: list[Message]) -> str:
        return f"[stub] echo: {messages[-1].content}"
