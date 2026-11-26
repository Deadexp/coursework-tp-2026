from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.llm.base import LLMClient, LLMError, LLMRefusalError, Message
from app.llm.stub import StubLLM


@lru_cache
def get_llm() -> LLMClient:
    """Единая точка выбора провайдера. Новый провайдер = новый класс + ветка здесь."""
    if settings.llm_provider == "stub":
        return StubLLM()
    if settings.llm_provider == "openrouter":
        if not settings.openrouter_api_key.strip():
            raise LLMError("Для подключения OpenRouter задайте OPENROUTER_API_KEY в .env")
        from app.llm.openrouter_client import OpenRouterLLM

        return OpenRouterLLM(
            api_key=settings.openrouter_api_key.strip(),
            model=settings.llm_model,
            effort=settings.llm_effort,
        )
    raise LLMError(f"Неизвестный LLM_PROVIDER: {settings.llm_provider}")


# Зависимость для эндпоинтов; в тестах подменяется через app.dependency_overrides[get_llm].
LLMDep = Annotated[LLMClient, Depends(get_llm)]

__all__ = ["LLMClient", "LLMDep", "LLMError", "LLMRefusalError", "Message", "get_llm"]
