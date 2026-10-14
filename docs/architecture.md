# 2. Архитектура системы

Тип: клиент-сервер; сервер — модульный монолит.

```mermaid
flowchart LR
  Web[Сайт: React SPA] -->|REST /api| API
  Bot[Telegram-бот: aiogram] -->|REST| API
  TG[Telegram] <--> Bot
  API[Backend: FastAPI] --> DB[(PostgreSQL)]
  API --> LLM[LLM-провайдер]
```

## Почему не микросервисы
TODO: команда из 3 человек, один семестр, общая БД, сложность развёртывания.

## Модули backend
users · learning · vocabulary · dialogs · recommendations · llm

## Привязка Telegram-аккаунта к аккаунту сайта
TODO: одноразовый код / deep-link `t.me/<bot>?start=<code>`.
