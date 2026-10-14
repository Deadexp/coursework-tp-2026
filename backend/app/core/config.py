from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/english"
    bot_service_token: str = "change-me"
    llm_provider: str = "stub"
    llm_api_key: str = ""
    llm_model: str = ""


settings = Settings()
