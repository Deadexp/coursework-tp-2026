from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/english"
    bot_service_token: str = "change-me"
    jwt_secret: str = "dev-only-secret-change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    llm_provider: str = "stub"  # stub | anthropic
    llm_model: str = "claude-sonnet-5-5"
    llm_effort: str = "low"  # low | medium | high — глубина размышлений модели
    anthropic_api_key: str = ""

    @field_validator("llm_provider", "llm_model", "llm_effort", mode="before")
    @classmethod
    def empty_means_default(cls, value: str, info):
        # Строка «LLM_MODEL=» в .env не должна затирать значение по умолчанию.
        if value == "":
            return cls.model_fields[info.field_name].default
        return value


settings = Settings()
