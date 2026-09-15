from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cors_origins: list[str] = ["http://localhost:5173"]

    musicbrainz_user_agent: str = "Melodia/0.1 (https://github.com/melodia-app)"
    lastfm_api_key: str = ""

    gemini_api_key: str = ""
    gemini_generation_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "text-embedding-004"


@lru_cache
def get_settings() -> Settings:
    return Settings()
