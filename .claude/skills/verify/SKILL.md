---
name: verify
description: Полная проверка проекта перед коммитом или Pull Request — линтер и тесты backend, соответствие моделей и миграций, типы, линтер и сборка сайта, e2e-тесты в браузере. Использовать, когда просят «проверь всё», перед открытием PR или после крупных изменений.
---

# Полная проверка проекта

Система должна быть запущена (`docker compose up -d`), а контент загружен (`docker compose run --rm api python -m app.seed`). Выполняй шаги по порядку из корня репозитория; при первой ошибке остановись, исправь причину и начни проверку заново.

1. Backend — формат, линтер, тесты:
   `docker compose run --rm -T api sh -c "ruff format --check . && ruff check . && pytest -q"`
2. Модели и миграции совпадают (схема не менялась мимо Alembic):
   `docker compose run --rm -T api alembic check`
3. Сайт — форматирование, типы, линтер, сборка:
   `cd frontend && npx prettier --check src e2e && npx tsc -b && npm run lint && npm run build`
   В выводе `npm run lint` должно быть 0 предупреждений.
4. E2E-тесты в браузере:
   `cd frontend && npm run test:e2e`
5. Убери пользователей, которых создали e2e-тесты:
   `docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "delete from users where email like '"'"'e2e-%@example.com'"'"'"'`

Итог сообщи таблицей «шаг — результат» с числом пройденных тестов. Не называй проверку успешной, если какой-то шаг пропущен или упал, — так и напиши, что именно.
