import pytest

from app.models import Album, Artist, Track
from app.services import ingest, lastfm, musicbrainz


@pytest.fixture(autouse=True)
def _mock_external_apis(monkeypatch):
    monkeypatch.setattr(
        musicbrainz,
        "search_artist",
        lambda name: {"id": "mbid-artist-1", "name": "Boards of Canada"},
    )
    monkeypatch.setattr(
        musicbrainz,
        "browse_release_groups",
        lambda artist_mbid, limit=10: [
            {
                "id": "mbid-album-1",
                "title": "Music Has the Right to Children",
                "primary-type": "Album",
                "first-release-date": "1998-04-20",
            }
        ],
    )
    monkeypatch.setattr(
        musicbrainz,
        "get_release_group_tracks",
        lambda release_group_mbid: [
            {"title": "Wildlife Analysis", "recording": {"id": "mbid-track-1"}, "length": 111000}
        ],
    )
    monkeypatch.setattr(
        lastfm,
        "get_top_tags",
        lambda artist_name: [{"name": "idm", "count": 100}, {"name": "ambient", "count": 40}],
    )


def test_ingest_artist_creates_artist_albums_tracks(db_session):
    artist = ingest.ingest_artist(db_session, "Boards of Canada")

    assert artist.name == "Boards of Canada"
    assert artist.musicbrainz_id == "mbid-artist-1"
    assert {g.name for g in artist.genres} == {"idm", "ambient"}

    albums = db_session.query(Album).all()
    assert len(albums) == 1
    assert albums[0].title == "Music Has the Right to Children"

    tracks = db_session.query(Track).all()
    assert len(tracks) == 1
    assert tracks[0].title == "Wildlife Analysis"
    assert tracks[0].length_ms == 111000


def test_ingest_artist_is_idempotent(db_session):
    ingest.ingest_artist(db_session, "Boards of Canada")
    ingest.ingest_artist(db_session, "Boards of Canada")

    assert db_session.query(Artist).count() == 1
    assert db_session.query(Album).count() == 1
    assert db_session.query(Track).count() == 1


def test_ingest_artist_not_found(monkeypatch, db_session):
    monkeypatch.setattr(musicbrainz, "search_artist", lambda name: None)

    with pytest.raises(ingest.ArtistNotFound):
        ingest.ingest_artist(db_session, "Nonexistent Band")


def test_ingest_artist_without_lastfm_configured(monkeypatch, db_session):
    def raise_not_configured(artist_name):
        raise lastfm.LastfmNotConfigured("no key")

    monkeypatch.setattr(lastfm, "get_top_tags", raise_not_configured)

    artist = ingest.ingest_artist(db_session, "Boards of Canada")

    assert artist.genres == []


def test_ingest_artist_album_limit_zero_skips_albums(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        musicbrainz,
        "browse_release_groups",
        lambda artist_mbid, limit=10: calls.append(1) or [],
    )

    artist = ingest.ingest_artist(db_session, "Boards of Canada", album_limit=0)

    assert calls == []  # browse_release_groups never called
    assert {g.name for g in artist.genres} == {"idm", "ambient"}  # tags still fetched
    assert db_session.query(Album).count() == 0


def test_ingest_artist_cache_hit_skips_external_calls_when_no_albums_needed(
    db_session, monkeypatch
):
    search_calls = []
    monkeypatch.setattr(
        musicbrainz,
        "search_artist",
        lambda name: search_calls.append(1)
        or {"id": "mbid-artist-1", "name": "Boards of Canada"},
    )

    ingest.ingest_artist(db_session, "Boards of Canada", album_limit=0)
    assert len(search_calls) == 1

    second = ingest.ingest_artist(db_session, "Boards of Canada", album_limit=0)
    assert len(search_calls) == 1  # no second MusicBrainz call - served from cache
    assert second.musicbrainz_id == "mbid-artist-1"


def test_ingest_artist_cache_miss_when_albums_needed_but_not_yet_fetched(
    db_session, monkeypatch
):
    search_calls = []
    monkeypatch.setattr(
        musicbrainz,
        "search_artist",
        lambda name: search_calls.append(1)
        or {"id": "mbid-artist-1", "name": "Boards of Canada"},
    )

    ingest.ingest_artist(db_session, "Boards of Canada", album_limit=0)
    assert len(search_calls) == 1

    # Requesting albums this time should fall through to a real ingest, not the cache,
    # since the cached row has no albums yet (this is what the frontend's "Load
    # albums" button on ArtistPage relies on).
    second = ingest.ingest_artist(db_session, "Boards of Canada", album_limit=10)
    assert len(search_calls) == 2
    assert db_session.query(Album).count() == 1
    assert second.albums[0].title == "Music Has the Right to Children"
