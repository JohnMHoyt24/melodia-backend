"""Thin client for the Gemini API (https://ai.google.dev/api).

Free tier. Used for two things:
- `classify_characteristics`: structured-output text generation that scores an artist
  on a fixed vocabulary of characteristics (see app/core/constants.py), based on their
  name + genre tags rather than audio analysis (which Spotify no longer offers for
  free - see PLAN.md).
- `embed_text`: turns a short text summary of an artist into a vector for pgvector
  similarity search.
"""

import json
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.constants import CHARACTERISTIC_NAMES, EMBEDDING_DIM

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_MAX_RETRIES = 5


class GeminiNotConfigured(RuntimeError):
    pass


def _require_api_key() -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY is not set - get a free key at "
            "https://aistudio.google.com/app/apikey"
        )
    return settings.gemini_api_key


_RETRYABLE_STATUS_CODES = {429, 503}


def _post(url: str, api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST with a retry for rate limits, transient 503s, and read timeouts.

    Free-tier Gemini hits all three routinely, not as rare edge cases: 429 (per-minute
    quota - a handful of calls in a short script is enough to trip it), 503 "high
    demand" UNAVAILABLE (same situation as MusicBrainz's 503s, app/services/
    musicbrainz.py), and requests that just sit past a 60s read timeout with no
    response. A 429 honors `Retry-After` when the API sends one, since that's a known
    wait rather than a guess. The 60s per-attempt timeout gives `gemini-flash-latest`'s
    internal "thinking" step room; still errors after `_MAX_RETRIES`.
    """
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = httpx.post(url, params={"key": api_key}, json=body, timeout=60.0)
        except httpx.TimeoutException as exc:
            last_error = exc
            time.sleep(2**attempt)
            continue
        if response.status_code in _RETRYABLE_STATUS_CODES:
            last_error = httpx.HTTPStatusError(
                f"{response.status_code} {response.reason_phrase}",
                request=response.request,
                response=response,
            )
            retry_after = response.headers.get("retry-after")
            delay = float(retry_after) if retry_after else 2**attempt
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response.json()
    assert last_error is not None
    raise last_error


def classify_characteristics(artist_name: str, genres: list[str]) -> dict[str, float]:
    """Return a {characteristic_name: score} dict, each score in [0.0, 1.0]."""
    api_key = _require_api_key()
    settings = get_settings()

    genre_text = ", ".join(genres) if genres else "unknown"
    prompt = (
        "You are a music analyst. Given an artist and their genre tags, estimate "
        "these characteristics on a 0.0-1.0 scale:\n"
        "- energy: overall intensity/loudness feel\n"
        "- valence: positive/upbeat (1.0) vs melancholic/dark (0.0) mood\n"
        "- melody: melodic/tonal (1.0) vs noisy/atonal (0.0)\n"
        "- aggression: aggressive/harsh (1.0) vs gentle/calm (0.0)\n"
        "- danceability: how suited to dancing\n"
        "- complexity: intricate/experimental (1.0) vs simple/accessible (0.0)\n\n"
        f"Artist: {artist_name}\n"
        f"Genre tags: {genre_text}\n"
    )

    data = _post(
        f"{BASE_URL}/models/{settings.gemini_generation_model}:generateContent",
        api_key,
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {name: {"type": "NUMBER"} for name in CHARACTERISTIC_NAMES},
                    "required": CHARACTERISTIC_NAMES,
                },
            },
        },
    )

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    raw_scores: dict[str, Any] = json.loads(text)

    return {
        name: max(0.0, min(1.0, float(raw_scores.get(name, 0.5))))
        for name in CHARACTERISTIC_NAMES
    }


def suggest_artists(prompt: str, count: int = 5) -> list[dict[str, str]]:
    """Return up to `count` real-artist suggestions as [{"name": str, "reason": str}]

    for a free-text discovery prompt (e.g. "like Dinosaur Jr but with more jangly
    guitars"). Leans on Gemini's own trained music knowledge rather than a fixed local
    catalog - callers are expected to verify each name against a real source (see
    app/services/recommend.py, which uses MusicBrainz via ingest_artist) since Gemini
    can hallucinate a name that doesn't exist.
    """
    api_key = _require_api_key()
    settings = get_settings()

    instructions = (
        "You are a knowledgeable music recommender. A user will describe what they "
        f"want in free text. Suggest up to {count} real, existing artists that fit - "
        "not made-up names. For each, give a one-sentence reason tied to what the user "
        "asked for.\n\n"
        f"User request: {prompt}\n"
    )

    data = _post(
        f"{BASE_URL}/models/{settings.gemini_generation_model}:generateContent",
        api_key,
        {
            "contents": [{"parts": [{"text": instructions}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "reason": {"type": "STRING"},
                        },
                        "required": ["name", "reason"],
                    },
                },
            },
        },
    )

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    suggestions: list[dict[str, str]] = json.loads(text)
    return suggestions[:count]


def embed_text(text: str) -> list[float]:
    api_key = _require_api_key()
    settings = get_settings()

    data = _post(
        f"{BASE_URL}/models/{settings.gemini_embedding_model}:embedContent",
        api_key,
        {
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBEDDING_DIM,
        },
    )
    return data["embedding"]["values"]
