# English Learning Platform (курсовая)

Сайт + Telegram-бот для изучения английского с адаптивным обучением на основе LLM.
Команда: 3 человека. Документация курсовой — в `docs/`.

## Архитектура
Клиент-сервер, backend — модульный монолит.
- `backend/` — FastAPI, единственный владелец БД и бизнес-логики. Все клиенты ходят только через его REST API.
- `frontend/` — React + TypeScript (Vite), SPA. Запросы к API через префикс `/api` (прокси Vite).
- `bot/` — aiogram 3. **Никогда не обращается к БД напрямую**, только к API через `bot/api_client.py`.
- `backend/app/llm/` — абстракция над LLM-провайдером (`LLMClient`). Остальной код не импортирует SDK провайдеров напрямую, только `get_llm()`.

## Структура backend
- `app/core/` — конфиг (`config.py`) и подключение к БД (`db.py`).
- `app/modules/<домен>/` — по модулю на предметную область: `users`, `learning` (темы, упражнения, попытки, ошибки), `vocabulary`, `dialogs`, `recommendations`.
  Внутри модуля: `models.py` (SQLAlchemy), `schemas.py` (Pydantic), `service.py` (логика), `router.py` (эндпоинты).
- Модули не лезут в таблицы друг друга напрямую — вызывают `service.py` другого модуля.
- Новую модель обязательно импортировать в `app/models.py`, иначе Alembic её не увидит.
- Общие перечисления — `app/core/enums.py`; в колонках использовать `pg_enum(...)` (хранит значения, а не имена).

## База данных
- PostgreSQL, SQLAlchemy 2.0 (async, `Mapped[...]`), миграции только через Alembic. Схему руками не менять.
- `docker compose up` сам применяет миграции (`alembic upgrade head`) перед запуском API.
- После autogenerate проверять миграцию глазами; в `downgrade` удалять созданные ENUM-типы (Alembic этого не делает).
- Проверка, что модели и миграции совпадают: `docker compose run --rm api alembic check`.
- Схема должна быть в 3НФ: производные значения (прогресс, статистика, % правильных) вычисляются запросами, а не хранятся.
- ER-схема и обоснование нормализации — `docs/database.md`. При изменении моделей обновлять и его.

## Команды
- Всё целиком: `docker compose up --build`
- Тесты backend: `docker compose run --rm api pytest`
- Линт/формат Python: `docker compose run --rm api ruff check --fix . && docker compose run --rm api ruff format .`
- Миграция: `docker compose run --rm api alembic revision --autogenerate -m "<msg>"`, затем `alembic upgrade head`
- Фронтенд: `cd frontend && npm run dev | npm run build | npm run lint`
- E2E-тесты сайта (нужна запущенная система): `cd frontend && npm run test:e2e`. Создают пользователей `e2e-*@example.com` в базе разработки.
- Swagger: http://localhost:8000/docs

## Фронтенд
- Все запросы к API — через `request()` из `frontend/src/api/client.ts`: он подставляет токен и превращает ошибки в `ApiError` (с `fieldErrors` из 422).
- Текущий пользователь и вход/выход — `useAuth()` из `src/auth/context.ts`. Закрытые страницы — внутри `<RequireAuth />` в `App.tsx`.
- Интерфейс на русском. Цвета только через CSS-переменные из `src/index.css` (есть тёмная тема).
- Название продукта — константа `APP_NAME` в `src/config.ts`.

## Авторизация
- Вход по email + паролю, JWT access token (`Authorization: Bearer <token>`), пароли — argon2 (`app/core/security.py`).
- Эндпоинт, которому нужен вошедший пользователь, принимает параметр `user: CurrentUser` из `app/modules/users/deps.py`.
- Тесты работают в отдельной базе `<имя>_test` (см. `tests/conftest.py`), фикстура `client` очищает таблицы после каждого теста.

## Соглашения
- Python 3.12, type hints везде, async для I/O.
- Каждый новый эндпоинт — с тестом в `backend/tests/`.
- Ответы LLM, которые разбирает код (ошибки, план занятия), запрашивать в JSON и валидировать Pydantic-схемой.
- Секреты только в `.env` (не коммитится); новые переменные добавлять в `.env.example`.
- Коммиты небольшие, сообщение на русском или английском в повелительном наклонении.
