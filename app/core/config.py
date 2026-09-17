from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cors_origins: list[str] = ["http://localhost:5173"]

    musicbrainz_user_agent: str = "Melodia/0.1 (https://github.com/melodia-app)"
    lastfm_api_key: str = ""

    # From Supabase dashboard -> Settings -> API -> JWT Secret. Used to verify the
    # access tokens supabase-js issues on the frontend, without a network round-trip
    # per request.
    supabase_jwt_secret: str = ""

    gemini_api_key: str = ""
    # gemini-flash-latest (-> gemini-3.8-flash as of writing) has a 20 requests/day free-tier
    # cap - hit it live during Milestone 3 testing. gemini-flash-lite-latest has more free-tier
    # headroom; reconfirm at https://ai.google.dev/gemini-api/docs/rate-limits before relying
    # on either number.
    gemini_generation_model: str = "gemini-flash-lite-latest"
    gemini_embedding_model: str = "gemini-embedding-001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
