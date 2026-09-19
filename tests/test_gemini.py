import json
from types import SimpleNamespace

import pytest
import respx
from httpx import Response

from app.services import gemini


def _settings(**overrides):
    defaults = dict(
        gemini_api_key="test-key",
        gemini_generation_model="gemini-flash-latest",
        gemini_embedding_model="gemini-embedding-001",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_classify_characteristics_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", lambda: _settings(gemini_api_key=""))

    with pytest.raises(gemini.GeminiNotConfigured):
        gemini.classify_characteristics("Boards of Canada", ["idm", "ambient"])


@respx.mock
def test_classify_characteristics_parses_structured_output(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    scores = {
        "energy": 0.4,
        "valence": 0.3,
        "melody": 0.8,
        "aggression": 0.1,
        "danceability": 0.2,
        "complexity": 0.7,
    }
    respx.post(f"{gemini.BASE_URL}/models/gemini-flash-latest:generateContent").mock(
        return_value=Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(scores)}]}}
                ]
            },
        )
    )

    result = gemini.classify_characteristics("Boards of Canada", ["idm", "ambient"])

    assert result == scores


@respx.mock
def test_classify_characteristics_clamps_and_fills_missing(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    respx.post(f"{gemini.BASE_URL}/models/gemini-flash-latest:generateContent").mock(
        return_value=Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps({"energy": 1.5, "valence": -0.5})}]}}
                ]
            },
        )
    )

    result = gemini.classify_characteristics("Unknown Artist", [])

    assert result["energy"] == 1.0
    assert result["valence"] == 0.0
    assert result["melody"] == 0.5  # missing key defaults to 0.5


@respx.mock
def test_chat_turn_parses_reply_and_artists(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    payload = {
        "reply": "Sure, here are a few jangly picks:",
        "artists": [
            {"name": "Yo La Tengo", "reason": "Jangly guitars with a similar dreamy feel."},
            {"name": "The Feelies", "reason": "Chiming guitar tones in a similar vein."},
        ],
    }
    respx.post(f"{gemini.BASE_URL}/models/gemini-flash-latest:generateContent").mock(
        return_value=Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )
    )

    result = gemini.chat_turn([], "like Dinosaur Jr but janglier", count=5)

    assert result == payload


@respx.mock
def test_chat_turn_sends_history_as_alternating_roles(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    payload = {"reply": "It's more mellow than the others.", "artists": []}
    route = respx.post(f"{gemini.BASE_URL}/models/gemini-flash-latest:generateContent").mock(
        return_value=Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )
    )

    history = [
        {"role": "user", "content": "like Dinosaur Jr but janglier"},
        {"role": "assistant", "content": "Sure, here are a few jangly picks:"},
    ]
    result = gemini.chat_turn(history, "why the first one?")

    assert result == payload
    sent_contents = json.loads(route.calls[0].request.content)["contents"]
    assert [c["role"] for c in sent_contents] == ["user", "model", "user"]
    assert sent_contents[-1]["parts"][0]["text"] == "why the first one?"


@respx.mock
def test_chat_turn_includes_library_context_in_system_instruction(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    payload = {"reply": "From your library.", "artists": []}
    route = respx.post(f"{gemini.BASE_URL}/models/gemini-flash-latest:generateContent").mock(
        return_value=Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )
    )

    gemini.chat_turn([], "mellow", context="- Boards of Canada - genres: idm")

    system_text = json.loads(route.calls[0].request.content)["systemInstruction"]["parts"][0]["text"]
    assert "Boards of Canada" in system_text


@respx.mock
def test_chat_turn_truncates_artists_to_count(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    payload = {
        "reply": "Here you go:",
        "artists": [{"name": f"Artist {i}", "reason": "reason"} for i in range(5)],
    }
    respx.post(f"{gemini.BASE_URL}/models/gemini-flash-latest:generateContent").mock(
        return_value=Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )
    )

    result = gemini.chat_turn([], "anything", count=2)

    assert len(result["artists"]) == 2


def test_chat_turn_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", lambda: _settings(gemini_api_key=""))

    with pytest.raises(gemini.GeminiNotConfigured):
        gemini.chat_turn([], "anything")


@respx.mock
def test_embed_text_returns_vector(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    respx.post(f"{gemini.BASE_URL}/models/gemini-embedding-001:embedContent").mock(
        return_value=Response(200, json={"embedding": {"values": [0.1, 0.2, 0.3]}})
    )

    assert gemini.embed_text("Boards of Canada - genres: idm, ambient") == [0.1, 0.2, 0.3]


def test_embed_text_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", lambda: _settings(gemini_api_key=""))

    with pytest.raises(gemini.GeminiNotConfigured):
        gemini.embed_text("some text")


@respx.mock
def test_retries_on_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    monkeypatch.setattr(gemini.time, "sleep", lambda seconds: None)
    route = respx.post(f"{gemini.BASE_URL}/models/gemini-embedding-001:embedContent")
    route.side_effect = [
        Response(503, json={"error": {"message": "high demand"}}),
        Response(200, json={"embedding": {"values": [0.1, 0.2]}}),
    ]

    assert gemini.embed_text("some text") == [0.1, 0.2]
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_max_retries(monkeypatch):
    import httpx

    monkeypatch.setattr(gemini, "get_settings", _settings)
    monkeypatch.setattr(gemini.time, "sleep", lambda seconds: None)
    respx.post(f"{gemini.BASE_URL}/models/gemini-embedding-001:embedContent").mock(
        return_value=Response(503, json={"error": {"message": "high demand"}})
    )

    with pytest.raises(httpx.HTTPStatusError):
        gemini.embed_text("some text")


@respx.mock
def test_retries_on_read_timeout_then_succeeds(monkeypatch):
    import httpx

    monkeypatch.setattr(gemini, "get_settings", _settings)
    monkeypatch.setattr(gemini.time, "sleep", lambda seconds: None)
    route = respx.post(f"{gemini.BASE_URL}/models/gemini-embedding-001:embedContent")
    route.side_effect = [
        httpx.ReadTimeout("timed out"),
        Response(200, json={"embedding": {"values": [0.1, 0.2]}}),
    ]

    assert gemini.embed_text("some text") == [0.1, 0.2]
    assert route.call_count == 2


@respx.mock
def test_retries_on_429_honoring_retry_after(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    sleeps = []
    monkeypatch.setattr(gemini.time, "sleep", lambda seconds: sleeps.append(seconds))
    route = respx.post(f"{gemini.BASE_URL}/models/gemini-embedding-001:embedContent")
    route.side_effect = [
        Response(429, headers={"retry-after": "3"}, json={"error": {"message": "quota"}}),
        Response(200, json={"embedding": {"values": [0.1, 0.2]}}),
    ]

    assert gemini.embed_text("some text") == [0.1, 0.2]
    assert route.call_count == 2
    assert sleeps == [3.0]
