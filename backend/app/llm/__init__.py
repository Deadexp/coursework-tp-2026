from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMClient, LLMError, LLMRefusalError, Message
from app.llm.stub import StubLLM


@lru_cache
def get_llm() -> LLMClient:
    """Единая точка выбора провайдера. Новый провайдер = новый класс + ветка здесь."""
    if settings.llm_provider == "stub":
        return StubLLM()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMError("LLM_PROVIDER=anthropic, но ANTHROPIC_API_KEY не задан в .env")
        from app.llm.anthropic_client import AnthropicLLM

        return AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            effort=settings.llm_effort,
        )
    raise LLMError(f"Неизвестный LLM_PROVIDER: {settings.llm_provider}")


__all__ = ["LLMClient", "LLMError", "LLMRefusalError", "Message", "get_llm"]
