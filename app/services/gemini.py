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
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.constants import CHARACTERISTIC_NAMES

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


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

    response = httpx.post(
        f"{BASE_URL}/models/{settings.gemini_generation_model}:generateContent",
        params={"key": api_key},
        json={
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
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    raw_scores: dict[str, Any] = json.loads(text)

    return {
        name: max(0.0, min(1.0, float(raw_scores.get(name, 0.5))))
        for name in CHARACTERISTIC_NAMES
    }


def embed_text(text: str) -> list[float]:
    api_key = _require_api_key()
    settings = get_settings()

    response = httpx.post(
        f"{BASE_URL}/models/{settings.gemini_embedding_model}:embedContent",
        params={"key": api_key},
        json={"content": {"parts": [{"text": text}]}},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["embedding"]["values"]
