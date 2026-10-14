from app.core.config import settings
from app.llm.base import LLMClient, Message
from app.llm.stub import StubLLM


def get_llm() -> LLMClient:
    """Единая точка выбора провайдера. Новый провайдер = новый класс + ветка здесь."""
    if settings.llm_provider == "stub":
        return StubLLM()
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


__all__ = ["LLMClient", "Message", "get_llm"]
