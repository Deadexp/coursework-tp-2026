from app.llm.base import LLMError, Message, T


class StubLLM:
    """Заглушка для разработки без API-ключа: отвечает эхом, структурированные ответы не умеет."""

    async def chat(self, system: str, messages: list[Message]) -> str:
        return f"[stub] echo: {messages[-1].content}"

    async def parse(self, system: str, messages: list[Message], schema: type[T]) -> T:
        raise LLMError(
            "Языковая модель не подключена: "
            "укажите LLM_PROVIDER=anthropic и ANTHROPIC_API_KEY в .env"
        )
