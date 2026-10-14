from fastapi import FastAPI

import app.models  # noqa: F401 — регистрирует все модели, чтобы внешние ключи между модулями находили таблицы
from app.modules.learning.router import router as learning_router
from app.modules.users.router import router as users_router
from app.modules.vocabulary.router import router as vocabulary_router

app = FastAPI(title="English Learning API")
app.include_router(users_router)
app.include_router(learning_router)
app.include_router(vocabulary_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
