"""Thin client for the Last.fm API (https://www.last.fm/api).

Free tier, requires an API key (see .env.example) - used here for user-generated
artist tags, which we fold into our own `genres` table as a cross-check against the
MusicBrainz data.
"""

from typing import Any

import httpx

from app.core.config import get_settings

BASE_URL = "https://ws.audioscrobbler.com/2.0/"


class LastfmNotConfigured(RuntimeError):
    pass


def get_top_tags(artist_name: str) -> list[dict[str, Any]]:
    """Return this artist's top user-generated tags as [{"name": str, "count": int}]."""
    settings = get_settings()
    if not settings.lastfm_api_key:
        raise LastfmNotConfigured(
            "LASTFM_API_KEY is not set - get a free key at "
            "https://www.last.fm/api/account/create"
        )

    response = httpx.get(
        BASE_URL,
        params={
            "method": "artist.gettoptags",
            "artist": artist_name,
            "api_key": settings.lastfm_api_key,
            "format": "json",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        return []

    tags = data.get("toptags", {}).get("tag", [])
    return [{"name": tag["name"], "count": int(tag["count"])} for tag in tags]
