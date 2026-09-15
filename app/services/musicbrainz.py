"""Thin client for the MusicBrainz API (https://musicbrainz.org/doc/MusicBrainz_API).

No auth required, but MusicBrainz asks anonymous clients to stick to ~1 request/second
and to send a descriptive User-Agent - both handled here.
"""

import time
from typing import Any

import httpx

from app.core.config import get_settings

BASE_URL = "https://musicbrainz.org/ws/2"
_MIN_INTERVAL_SECONDS = 1.0
_MAX_RETRIES = 5

_last_request_at: float = 0.0


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET with MusicBrainz's rate-limit throttle and a retry for transient 503s.

    In practice MusicBrainz's anonymous-tier search/browse endpoints return
    "503 Service Temporarily Unavailable" fairly often even at 1 req/sec - this isn't
    an edge case, it's routine, so it's handled here rather than left to callers.
    """
    settings = get_settings()
    last_error: httpx.HTTPStatusError | None = None
    for attempt in range(_MAX_RETRIES):
        _throttle()
        response = httpx.get(
            f"{BASE_URL}/{path}",
            params={**params, "fmt": "json"},
            headers={"User-Agent": settings.musicbrainz_user_agent},
            timeout=10.0,
        )
        if response.status_code == 503:
            last_error = httpx.HTTPStatusError(
                "503 Service Temporarily Unavailable",
                request=response.request,
                response=response,
            )
            time.sleep(2**attempt)
            continue
        response.raise_for_status()
        return response.json()
    assert last_error is not None
    raise last_error


def search_artist(name: str) -> dict[str, Any] | None:
    """Return the best-matching artist for `name`, or None if nothing was found."""
    data = _get("artist", {"query": f'artist:"{name}"', "limit": 1})
    artists = data.get("artists", [])
    return artists[0] if artists else None


def browse_release_groups(artist_mbid: str, limit: int = 25) -> list[dict[str, Any]]:
    """Return this artist's studio albums (release-group primary-type "Album")."""
    data = _get(
        "release-group",
        {"artist": artist_mbid, "type": "album", "limit": limit},
    )
    return data.get("release-groups", [])


def get_release_group_tracks(release_group_mbid: str) -> list[dict[str, Any]]:
    """Return the tracklist of one representative release for a release-group."""
    data = _get(
        "release",
        {"release-group": release_group_mbid, "inc": "recordings", "limit": 1},
    )
    releases = data.get("releases", [])
    if not releases:
        return []
    media = releases[0].get("media", [])
    tracks: list[dict[str, Any]] = []
    for medium in media:
        tracks.extend(medium.get("tracks", []))
    return tracks
