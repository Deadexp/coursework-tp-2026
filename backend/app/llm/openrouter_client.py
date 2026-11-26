import logging

import openai
from openai.types.chat import ChatCompletionMessageParam, ParsedChatCompletionMessage
from pydantic import ValidationError

from app.llm.base import LLMError, LLMRefusalError, Message, T

log = logging.getLogger(__name__)

_STATUS_ERRORS = {
    400: "OpenRouter отклонил параметры запроса. Проверьте LLM_MODEL и LLM_EFFORT",
    401: "OpenRouter отклонил OPENROUTER_API_KEY",
    402: "Недостаточно кредитов OpenRouter",
    403: "OpenRouter ограничил доступ к модели",
    404: "Модель недоступна для этого запроса. Проверьте LLM_MODEL в OpenRouter",
    429: "Превышен лимит запросов OpenRouter, попробуйте позже",
}


class OpenRouterLLM:
    def __init__(self, api_key: str, model: str, effort: str) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=60.0,
            max_retries=2,
            _strict_response_validation=True,
        )
        self._model = model
        self._effort = effort

    async def chat(self, system: str, messages: list[Message], fast: bool = False) -> str:
        reply = await self._request(system, messages, fast)
        if not reply.content or not reply.content.strip():
            raise LLMError("Модель вернула пустой ответ")
        return reply.content

    async def parse(
        self, system: str, messages: list[Message], schema: type[T], fast: bool = False
    ) -> T:
        reply = await self._request(system, messages, fast, schema)
        if reply.parsed is None:
            raise LLMError("Модель вернула ответ не по схеме")
        return reply.parsed

    async def _request(
        self, system: str, messages: list[Message], fast: bool, schema: type[T] | None = None
    ) -> ParsedChatCompletionMessage[T]:
        history: list[ChatCompletionMessageParam] = [{"role": "system", "content": system}]
        history.extend({"role": m.role, "content": m.content} for m in messages)
        try:
            completion = await self._client.chat.completions.parse(
                model=self._model,
                messages=history,
                max_tokens=4000,
                response_format=schema if schema is not None else openai.omit,
                extra_body={
                    "reasoning": {"effort": "none" if fast else self._effort},
                    "provider": {"require_parameters": True},
                },
            )
        except openai.ContentFilterFinishReasonError:
            raise LLMRefusalError("Модель отказалась отвечать на этот запрос") from None
        except openai.LengthFinishReasonError:
            raise LLMError("Модель исчерпала лимит длины ответа") from None
        except (ValidationError, openai.APIResponseValidationError):
            raise LLMError("Модель вернула ответ не по схеме") from None
        except openai.APIStatusError as exc:
            log.warning("OpenRouter HTTP %s, request_id=%s", exc.status_code, exc.request_id)
            raise LLMError(
                _STATUS_ERRORS.get(exc.status_code, "OpenRouter временно недоступен")
            ) from None
        except openai.APIConnectionError:
            raise LLMError("Нет связи с OpenRouter") from None

        if not completion.choices:
            raise LLMError("OpenRouter не вернул ответ модели")
        message = completion.choices[0].message
        if message.refusal:
            raise LLMRefusalError("Модель отказалась отвечать на этот запрос")
        return message
