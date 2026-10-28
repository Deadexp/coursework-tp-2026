from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    api_base_url: str = "http://localhost:8000"
    bot_service_token: str = "change-me"
    website_url: str = "http://localhost:5173"


settings = Settings()
