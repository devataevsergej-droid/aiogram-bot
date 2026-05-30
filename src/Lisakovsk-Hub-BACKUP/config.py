from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    bot_username: str = Field(default="JobLis_bot", alias="BOT_USERNAME")
    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_key: str = Field(alias="SUPABASE_KEY")
    admin_id: int = Field(default=0, alias="ADMIN_ID")
    admin_chat_id: int = Field(alias="ADMIN_CHAT_ID")
    channel_id: int = Field(alias="CHANNEL_ID")
    beeline_payment_phone: str = Field(default="", alias="BEELINE_PAYMENT_PHONE")
    project_oracle_url: str = Field(default="https://t.me/oracle_bot", alias="PROJECT_ORACLE_URL")
    project_rating_url: str = Field(default="https://t.me/rating_bot", alias="PROJECT_RATING_URL")
    project_workshop_url: str = Field(default="https://t.me/workshop_bot", alias="PROJECT_WORKSHOP_URL")
    health_host: str = Field(default="0.0.0.0", alias="HEALTH_HOST")
    health_port: int = Field(default=8000, alias="PORT")
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_path: str = Field(default="/webhook", alias="WEBHOOK_PATH")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
