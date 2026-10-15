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
- Новую модель обязательно импортировать в `app/models.py`, иначе Alembic и приложение её не увидят (`app/main.py` импортирует `app.models`; тест `test_app_startup.py` ловит забытые модели).
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
- E2E-тесты сайта (нужна запущенная система): `cd frontend && npm run test:e2e`. Идут по настоящему контенту (нужен `python -m app.seed`) и создают пользователей `e2e-*@example.com` в базе разработки.
- Swagger: http://localhost:8000/docs
- Загрузить учебный контент из `backend/content/course.json`: `docker compose run --rm api python -m app.seed` (повторный запуск безопасен)

## Учебный контент
- Темы, упражнения, слова и типы ошибок — в `backend/content/course.json`, а не в коде и не в миграциях. Формат проверяется Pydantic-моделями в `app/seed.py`.
- Проверка ответов — `app/modules/learning/checking.py` (без учёта регистра, лишних пробелов, апострофов и точки в конце). Все допустимые варианты ответа перечислять в `correct`.
- Правильные ответы клиент получает только в ответе на попытку, никогда — вместе с заданием.

## Словарь и повторение
- Алгоритм SM-2 — чистая функция в `app/modules/vocabulary/sm2.py`; состояние хранится в `user_words`, история — в `word_reviews`.
- Контракт для сайта и бота (порядок запросов, какую оценку `quality` отправлять) — `docs/api-vocabulary.md`. При изменении API обновлять его.

## ИИ (языковая модель)
- Провайдер настраивается в `.env`: `LLM_PROVIDER=anthropic|stub`, `ANTHROPIC_API_KEY`, `LLM_MODEL` (по умолчанию `claude-sonnet-5-5`), `LLM_EFFORT` (по умолчанию `low`), при необходимости `ANTHROPIC_WORKSPACE_ID`. Проверка подключения: `docker compose run --rm api python -m app.llm.check`.
- SDK Anthropic импортируется только в `app/llm/anthropic_client.py`. Эндпоинты получают модель зависимостью `llm: LLMDep` и вызывают `llm.chat(...)` или `llm.parse(..., Schema)` — второй возвращает проверенный Pydantic-объект (structured outputs).
- Модель вызывать **до** записи в БД, чтобы сбой ИИ не оставлял частичных данных. `LLMError` → 503, `LLMRefusalError` → 422 (обработчик в `app/main.py`).
- Ссылки, которые возвращает модель (id тем, коды ошибок), проверять по БД перед сохранением.
- Промпты — в `prompts.py` своего модуля (`dialogs`, `recommendations`).
- `fast=True` (без размышлений модели, только Sonnet 5.5) — для реплик в живом диалоге; отзыв и план — без него, там важнее качество. Изменения промптов проверять живым прогоном: подставная модель в тестах не покажет качество ответов.
- В pytest модель подменяется фикстурой `fake_llm` (`tests/conftest.py`); в e2e ответы ИИ подменяются через `page.route` — тесты не тратят деньги и не зависят от сети.

## Фронтенд
- Все запросы к API — через `request()` из `frontend/src/api/client.ts`: он подставляет токен и превращает ошибки в `ApiError` (с `fieldErrors` из 422). Обёртки по модулям — `src/api/learning.ts`, `src/api/vocabulary.ts`.
- Загрузка данных на страницах — хук `useApi(load)` из `src/hooks/useApi.ts`; `load` оборачивать в `useCallback`. При 401 он сам выходит из аккаунта.
- Страницы: `/` курс и план наставника, `/topics/:id` тема с упражнениями, `/vocabulary` словарь, `/review` повторение, `/talk` и `/talk/:id` разговор с собеседником. Общая шапка — `components/AppLayout.tsx`.
- Текущий пользователь и вход/выход — `useAuth()` из `src/auth/context.ts`. Закрытые страницы — внутри `<RequireAuth />` в `App.tsx`.
- Интерфейс на русском. Цвета только через CSS-переменные из `src/index.css` (есть тёмная тема).
- Название продукта — константа `APP_NAME` в `src/config.ts`.

## Авторизация
- Вход по email + паролю, JWT access token (`Authorization: Bearer <token>`), пароли — argon2 (`app/core/security.py`).
- Эндпоинт, которому нужен вошедший пользователь, принимает параметр `user: CurrentUser` из `app/modules/users/deps.py`.
- Тесты работают в отдельной базе `<имя>_test` (см. `tests/conftest.py`), фикстура `client` очищает таблицы после каждого теста.

## Проверка
- Перед открытием Pull Request — скилл `/verify` (все тесты, миграции, сборка, e2e). Не называть проверку успешной, если шаг пропущен или упал.
- После изменения моделей или миграций — субагент `db-reviewer` (3НФ, ограничения, downgrade, документация).
- Новую найденную ошибку агента записывать в журнал `docs/agent-choice.md`, а урок — правилом сюда.

## Соглашения
- Python 3.12, type hints везде, async для I/O.
- Каждый новый эндпоинт — с тестом в `backend/tests/`.
- Ответы LLM, которые разбирает код (ошибки, план занятия), запрашивать в JSON и валидировать Pydantic-схемой.
- Секреты только в `.env` (не коммитится); новые переменные добавлять в `.env.example`.
- Коммиты небольшие, сообщение на русском или английском в повелительном наклонении.
