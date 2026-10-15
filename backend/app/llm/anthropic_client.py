"""Провайдер Claude (Anthropic API)."""

import logging

import anthropic

from app.llm.base import LLMError, LLMRefusalError, Message, T

log = logging.getLogger(__name__)

# При отказе модели по соображениям безопасности API само повторит запрос на модели,
# которую Anthropic рекомендует для этой категории отказа (только Claude API).
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLLM:
    def __init__(
        self,
        api_key: str,
        model: str,
        effort: str,
        max_tokens: int = 4000,
        workspace_id: str = "",
    ) -> None:
        # Ключу, не привязанному к workspace, API велит явно указывать ID пространства.
        headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=60.0, max_retries=2, default_headers=headers
        )
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens

    def _request(self, system: str, messages: list[Message]) -> dict:
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            # Для диалога и разбора ошибок хватает низкого effort: быстрее и дешевле.
            "output_config": {"effort": self._effort},
            "betas": [_FALLBACK_BETA],
            "fallbacks": "default",
        }

    async def chat(self, system: str, messages: list[Message]) -> str:
        response = await self._call(self._client.beta.messages.create, system, messages)
        return "".join(block.text for block in response.content if block.type == "text")

    async def parse(self, system: str, messages: list[Message], schema: type[T]) -> T:
        response = await self._call(
            self._client.beta.messages.parse, system, messages, output_format=schema
        )
        if response.parsed_output is None:
            raise LLMError("Модель вернула ответ не по схеме")
        return response.parsed_output

    async def _call(self, method, system: str, messages: list[Message], **extra):
        try:
            response = await method(**self._request(system, messages), **extra)
        except anthropic.AuthenticationError:
            raise LLMError("Неверный ANTHROPIC_API_KEY") from None
        except anthropic.PermissionDeniedError:
            raise LLMError("У API-ключа нет доступа к модели") from None
        except anthropic.NotFoundError:
            raise LLMError(f"Модель {self._model} не найдена — проверьте LLM_MODEL") from None
        except anthropic.RateLimitError:
            raise LLMError("Превышен лимит запросов к модели, попробуйте позже") from None
        except anthropic.BadRequestError as e:
            log.error("Anthropic API rejected request: %s, request_id=%s", e.message, e.request_id)
            raise LLMError(f"Anthropic API отклонил запрос: {e.message}") from None
        except anthropic.APIStatusError as e:
            log.error("Anthropic API error %s, request_id=%s", e.status_code, e.request_id)
            raise LLMError("Языковая модель временно недоступна") from None
        except anthropic.APIConnectionError:
            raise LLMError("Нет связи с Anthropic API") from None

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            log.warning("LLM refusal, category=%s, request_id=%s", category, response._request_id)
            raise LLMRefusalError("Модель отказалась отвечать на этот запрос")
        if response.stop_reason == "max_tokens":
            log.warning("LLM hit max_tokens, request_id=%s", response._request_id)
        return response
