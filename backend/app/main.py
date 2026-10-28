from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import app.models  # noqa: F401 — регистрирует все модели, чтобы внешние ключи между модулями находили таблицы
from app.llm import LLMError, LLMRefusalError
from app.modules.dialogs.router import router as dialogs_router
from app.modules.learning.grammar_router import router as grammar_router
from app.modules.learning.router import router as learning_router
from app.modules.recommendations.router import router as recommendations_router
from app.modules.users.router import router as users_router
from app.modules.users.telegram_router import router as telegram_router
from app.modules.vocabulary.practice_router import router as practice_router
from app.modules.vocabulary.router import router as vocabulary_router

app = FastAPI(title="English Learning API")
app.include_router(users_router)
app.include_router(telegram_router)
app.include_router(learning_router)
app.include_router(grammar_router)
app.include_router(vocabulary_router)
app.include_router(practice_router)
app.include_router(dialogs_router)
app.include_router(recommendations_router)


@app.exception_handler(LLMError)
async def llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
    # Отказ модели — проблема конкретного сообщения (422); остальное — ИИ недоступен (503).
    status = 422 if isinstance(exc, LLMRefusalError) else 503
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
