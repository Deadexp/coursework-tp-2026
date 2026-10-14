from fastapi import FastAPI

from app.modules.users.router import router as users_router

app = FastAPI(title="English Learning API")
app.include_router(users_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
