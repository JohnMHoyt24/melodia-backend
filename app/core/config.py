from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    cors_origins: list[str] = ["http://localhost:5173"]

    musicbrainz_user_agent: str = "Melodia/0.1 (https://github.com/melodia-app)"
    lastfm_api_key: str = ""

    # Supabase project URL (Settings -> API). Used to fetch the project's public JWKS
    # to verify access tokens supabase-js issues on the frontend - Supabase signs them
    # with a per-project asymmetric key (ES256), not a shared secret, so verification
    # needs the public key, not a secret.
    supabase_url: str = ""

    # Analyze newly ingested artists in the background (app/services/analysis_queue.py).
    # Costs 2 Gemini calls per artist, so turn it off if the free-tier quota is tight.
    auto_analyze: bool = True
    analysis_delay_seconds: float = 2.0

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
