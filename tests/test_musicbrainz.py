import pytest
import respx
from httpx import Response

from app.services import musicbrainz


@pytest.fixture(autouse=True)
def _reset_throttle():
    musicbrainz._last_request_at = 0.0
    yield


@respx.mock
def test_search_artist_returns_best_match():
    respx.get(f"{musicbrainz.BASE_URL}/artist").mock(
        return_value=Response(
            200, json={"artists": [{"id": "abc-123", "name": "Boards of Canada"}]}
        )
    )

    result = musicbrainz.search_artist("Boards of Canada")

    assert result == {"id": "abc-123", "name": "Boards of Canada"}


@respx.mock
def test_search_artist_no_results():
    respx.get(f"{musicbrainz.BASE_URL}/artist").mock(
        return_value=Response(200, json={"artists": []})
    )

    assert musicbrainz.search_artist("Nonexistent Band") is None


@respx.mock
def test_browse_release_groups():
    respx.get(f"{musicbrainz.BASE_URL}/release-group").mock(
        return_value=Response(
            200,
            json={
                "release-groups": [
                    {"id": "rg-1", "title": "Music Has the Right to Children", "primary-type": "Album"}
                ]
            },
        )
    )

    groups = musicbrainz.browse_release_groups("abc-123")

    assert groups[0]["title"] == "Music Has the Right to Children"


@respx.mock
def test_get_release_group_tracks_flattens_media():
    respx.get(f"{musicbrainz.BASE_URL}/release").mock(
        return_value=Response(
            200,
            json={
                "releases": [
                    {
                        "media": [
                            {"tracks": [{"title": "Wildlife Analysis", "recording": {"id": "rec-1"}}]}
                        ]
                    }
                ]
            },
        )
    )

    tracks = musicbrainz.get_release_group_tracks("rg-1")

    assert tracks == [{"title": "Wildlife Analysis", "recording": {"id": "rec-1"}}]


@respx.mock
def test_get_release_group_tracks_no_releases():
    respx.get(f"{musicbrainz.BASE_URL}/release").mock(
        return_value=Response(200, json={"releases": []})
    )

    assert musicbrainz.get_release_group_tracks("rg-1") == []


@respx.mock
def test_get_retries_on_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(musicbrainz.time, "sleep", lambda seconds: None)
    route = respx.get(f"{musicbrainz.BASE_URL}/artist")
    route.side_effect = [
        Response(503, json={"error": "busy"}),
        Response(503, json={"error": "busy"}),
        Response(200, json={"artists": [{"id": "abc-123", "name": "Boards of Canada"}]}),
    ]

    result = musicbrainz.search_artist("Boards of Canada")

    assert result == {"id": "abc-123", "name": "Boards of Canada"}
    assert route.call_count == 3


@respx.mock
def test_get_gives_up_after_max_retries(monkeypatch):
    import httpx

    monkeypatch.setattr(musicbrainz.time, "sleep", lambda seconds: None)
    respx.get(f"{musicbrainz.BASE_URL}/artist").mock(
        return_value=Response(503, json={"error": "busy"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        musicbrainz.search_artist("Boards of Canada")


@respx.mock
def test_get_retries_on_read_timeout_then_succeeds(monkeypatch):
    import httpx

    monkeypatch.setattr(musicbrainz.time, "sleep", lambda seconds: None)
    route = respx.get(f"{musicbrainz.BASE_URL}/artist")
    route.side_effect = [
        httpx.ReadTimeout("timed out"),
        Response(200, json={"artists": [{"id": "abc-123", "name": "Boards of Canada"}]}),
    ]

    result = musicbrainz.search_artist("Boards of Canada")

    assert result == {"id": "abc-123", "name": "Boards of Canada"}
    assert route.call_count == 2
