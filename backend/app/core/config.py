from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/english"
    bot_service_token: str = "change-me"
    jwt_secret: str = "dev-only-secret-change-me-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    llm_provider: str = "stub"
    llm_api_key: str = ""
    llm_model: str = ""


settings = Settings()
