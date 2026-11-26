from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/english"
    bot_service_token: str = "change-me"
    bot_username: str = ""  # Public BotFather username, without @.
    jwt_secret: str = "dev-only-secret-change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    llm_provider: str = "openrouter"
    llm_model: str = "deepseek/deepseek-v4.1-flash-1017"
    llm_effort: str = "low"  # Уровень рассуждений для отзыва и плана занятия
    openrouter_api_key: str = ""

    @field_validator("llm_provider", "llm_model", "llm_effort", mode="before")
    @classmethod
    def empty_means_default(cls, value: str, info):
        # Строка «LLM_MODEL=» в .env не должна затирать значение по умолчанию.
        if value == "":
            return cls.model_fields[info.field_name].default
        return value


settings = Settings()
