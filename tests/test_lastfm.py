from types import SimpleNamespace

import pytest
import respx
from httpx import Response

from app.services import lastfm


def test_get_top_tags_without_api_key_raises(monkeypatch):
    monkeypatch.setattr(lastfm, "get_settings", lambda: SimpleNamespace(lastfm_api_key=""))

    with pytest.raises(lastfm.LastfmNotConfigured):
        lastfm.get_top_tags("Boards of Canada")


@respx.mock
def test_get_top_tags_returns_tags(monkeypatch):
    monkeypatch.setattr(
        lastfm, "get_settings", lambda: SimpleNamespace(lastfm_api_key="test-key")
    )
    respx.get(lastfm.BASE_URL).mock(
        return_value=Response(
            200,
            json={"toptags": {"tag": [{"name": "idm", "count": "100"}, {"name": "ambient", "count": "50"}]}},
        )
    )

    tags = lastfm.get_top_tags("Boards of Canada")

    assert tags == [{"name": "idm", "count": 100}, {"name": "ambient", "count": 50}]


@respx.mock
def test_get_top_tags_handles_api_error(monkeypatch):
    monkeypatch.setattr(
        lastfm, "get_settings", lambda: SimpleNamespace(lastfm_api_key="test-key")
    )
    respx.get(lastfm.BASE_URL).mock(
        return_value=Response(200, json={"error": 6, "message": "not found"})
    )

    assert lastfm.get_top_tags("Nonexistent Band") == []
