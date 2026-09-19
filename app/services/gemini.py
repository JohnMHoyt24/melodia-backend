"""Thin client for the Gemini API (https://ai.google.dev/api).

Free tier. Used for three things:
- `classify_characteristics`: structured-output text generation that scores an artist
  on a fixed vocabulary of characteristics (see app/core/constants.py), based on their
  name + genre tags rather than audio analysis (which Spotify no longer offers for
  free - see PLAN.md).
- `chat_turn`: one structured-output call per conversational turn that both replies to
  the user and, when warranted, suggests real artists - see app/services/chat.py.
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


_MAX_HISTORY_MESSAGES = 20

_CHAT_SYSTEM_INSTRUCTIONS = (
    "You are Melodia, a knowledgeable, conversational music recommender chatting with "
    "a user across multiple turns. Keep using earlier turns as context - if the user "
    "asks a follow-up ('more like the first one', 'why that one?', 'less mellow'), "
    "answer with that context in mind rather than starting over.\n\n"
    "Always write a short, conversational `reply` to the user.\n"
    "Only when the turn actually calls for new recommendations, also fill `artists` "
    "with up to {count} real, existing artists that fit - never made-up names - each "
    "with a one-sentence reason tied to what the user asked for. Leave `artists` empty "
    "for turns that are just conversation, clarification, or commentary on artists "
    "already suggested, rather than a request for something new."
)


def chat_turn(
    history: list[dict[str, str]],
    message: str,
    count: int = 5,
    context: str | None = None,
) -> dict[str, Any]:
    """Run one conversational turn: one Gemini call that can both chat and, when the

    turn calls for it, suggest real artists - replaces the old single-purpose
    `suggest_artists`. Returns {"reply": str, "artists": [{"name", "reason"}, ...]}.

    `history` is prior turns as [{"role": "user"|"assistant", "content": str}, ...],
    oldest first; only the last `_MAX_HISTORY_MESSAGES` are sent to bound prompt size.
    Callers are expected to verify each suggested name against a real source (see
    app/services/chat.py, which uses MusicBrainz via ingest_artist) since Gemini can
    hallucinate a name that doesn't exist. Still exactly one Gemini call per turn,
    regardless of history length - see PLAN.md for why that constraint matters on the
    free tier (retrieval in app/services/rag.py adds one embedding call on top).

    `context` is an optional block describing analyzed library artists retrieved for
    this turn; when present the model is told to prefer them, which keeps
    recommendations grounded in what Melodia actually knows about.
    """
    api_key = _require_api_key()
    settings = get_settings()

    system_text = _CHAT_SYSTEM_INSTRUCTIONS.format(count=count)
    if context:
        system_text += (
            "\n\nArtists in the user's Melodia library that are relevant to this "
            "conversation (with genres and 0.0-1.0 characteristic scores):\n"
            f"{context}\n"
            "Prefer these when they fit the request and say so; you may still suggest "
            "other real artists when they fit better."
        )

    contents = [
        {
            "role": "user" if turn["role"] == "user" else "model",
            "parts": [{"text": turn["content"]}],
        }
        for turn in history[-_MAX_HISTORY_MESSAGES:]
    ]
    contents.append({"role": "user", "parts": [{"text": message}]})

    data = _post(
        f"{BASE_URL}/models/{settings.gemini_generation_model}:generateContent",
        api_key,
        {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "reply": {"type": "STRING"},
                        "artists": {
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
                    "required": ["reply", "artists"],
                },
            },
        },
    )

    text = data["candidates"][0]["content"]["parts"][0]["text"]
    result: dict[str, Any] = json.loads(text)
    result["artists"] = result.get("artists", [])[:count]
    return result


_RAG_SYSTEM_INSTRUCTIONS = (
    "You are Melodia, a music assistant. Answer the user's question using ONLY the "
    "artists in the provided context - their genres and 0.0-1.0 characteristic scores "
    "(energy, valence, melody, aggression, danceability, complexity). Do not recommend "
    "or mention artists that are not in the context. If the context doesn't contain "
    "anything relevant, say so plainly instead of guessing. Keep the answer short and "
    "conversational."
)


def answer_with_context(question: str, context: str) -> str:
    """Generation step of RAG: answer `question` grounded in retrieved `context`.

    One plain-text Gemini call - see app/services/rag.py for retrieval and prompt
    assembly.
    """
    api_key = _require_api_key()
    settings = get_settings()

    data = _post(
        f"{BASE_URL}/models/{settings.gemini_generation_model}:generateContent",
        api_key,
        {
            "systemInstruction": {"parts": [{"text": _RAG_SYSTEM_INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"Context:\n{context}\n\nQuestion: {question}"}
                    ],
                }
            ],
        },
    )
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


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
