import httpx

from bot.config import settings

# Бот не ходит в БД напрямую: все данные только через backend API.
api = httpx.AsyncClient(
    base_url=settings.api_base_url,
    headers={"X-Service-Token": settings.bot_service_token},
    timeout=30,
)
