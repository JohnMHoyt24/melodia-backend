import json
from types import SimpleNamespace

import pytest
import respx
from httpx import Response

from app.services import gemini


def _settings(**overrides):
    defaults = dict(
        gemini_api_key="test-key",
        gemini_generation_model="gemini-2.0-flash",
        gemini_embedding_model="text-embedding-004",
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
    respx.post(f"{gemini.BASE_URL}/models/gemini-2.0-flash:generateContent").mock(
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
    respx.post(f"{gemini.BASE_URL}/models/gemini-2.0-flash:generateContent").mock(
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
def test_embed_text_returns_vector(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", _settings)
    respx.post(f"{gemini.BASE_URL}/models/text-embedding-004:embedContent").mock(
        return_value=Response(200, json={"embedding": {"values": [0.1, 0.2, 0.3]}})
    )

    assert gemini.embed_text("Boards of Canada - genres: idm, ambient") == [0.1, 0.2, 0.3]


def test_embed_text_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(gemini, "get_settings", lambda: _settings(gemini_api_key=""))

    with pytest.raises(gemini.GeminiNotConfigured):
        gemini.embed_text("some text")
