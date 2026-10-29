import httpx

from app.models import Album, Artist, UserArtist
from app.schemas.artist import ArtistDetail
from app.services import analysis_queue
from app.services.covers import artist_cover_urls, cover_art_url, earliest_album_mbid
from tests.conftest import TEST_USER_ID

CAA = "https://coverartarchive.org/release-group"


def _artist_with_albums(db_session, name, albums):
    artist = Artist(name=name)
    db_session.add(artist)
    db_session.flush()
    for title, mbid, released in albums:
        db_session.add(
            Album(artist_id=artist.id, title=title, musicbrainz_id=mbid, first_release_date=released)
        )
    db_session.commit()
    db_session.refresh(artist)
    return artist


def test_cover_art_url():
    assert cover_art_url("rg-1") == f"{CAA}/rg-1/front-250"
    assert cover_art_url("rg-1", size=500) == f"{CAA}/rg-1/front-500"
    assert cover_art_url(None) is None


def test_earliest_album_prefers_oldest_and_puts_undated_last():
    assert earliest_album_mbid([("late", "2010"), ("early", "1998-04-20"), ("undated", None)]) == "early"
    assert earliest_album_mbid([("undated", None)]) == "undated"
    assert earliest_album_mbid([(None, "1990")]) is None
    assert earliest_album_mbid([]) is None


def test_artist_cover_urls_uses_one_cover_per_artist(db_session):
    boc = _artist_with_albums(
        db_session,
        "Boards of Canada",
        [("Geogaddi", "rg-geo", "2002-02-18"), ("Music Has the Right", "rg-mhtr", "1998-04-20")],
    )
    no_mbid = _artist_with_albums(db_session, "Unlinked", [("Demo", None, "2001")])
    no_albums = _artist_with_albums(db_session, "Brand New", [])

    covers = artist_cover_urls(db_session, [boc.id, no_mbid.id, no_albums.id])

    assert covers == {boc.id: f"{CAA}/rg-mhtr/front-250"}
    assert artist_cover_urls(db_session, []) == {}


def test_artist_detail_and_albums_include_covers(db_session):
    artist = _artist_with_albums(
        db_session, "Boards of Canada", [("Geogaddi", "rg-geo", "2002"), ("Demo", None, "1995")]
    )

    detail = ArtistDetail.model_validate(artist).model_dump()

    assert detail["cover_url"] == f"{CAA}/rg-geo/front-500"
    covers = {album["title"]: album["cover_url"] for album in detail["albums"]}
    assert covers == {"Geogaddi": f"{CAA}/rg-geo/front-250", "Demo": None}


def test_library_list_includes_cover(authed_client, db_session):
    artist = _artist_with_albums(db_session, "Boards of Canada", [("Geogaddi", "rg-geo", "2002")])
    db_session.add(UserArtist(user_id=TEST_USER_ID, artist_id=artist.id))
    db_session.commit()

    listed = authed_client.get("/library").json()

    assert listed[0]["cover_url"] == f"{CAA}/rg-geo/front-250"


def test_worker_fetches_albums_for_artists_without_any(db_session, monkeypatch):
    artist = Artist(name="Boards of Canada", musicbrainz_id="mb-boc")
    db_session.add(artist)
    db_session.commit()
    fetched = []
    monkeypatch.setattr(analysis_queue, "ingest_album_shells", lambda db, a: fetched.append(a.id))

    analysis_queue._fetch_album_shells(db_session, artist)

    assert fetched == [artist.id]


def test_worker_skips_album_fetch_when_albums_exist_or_unlinked(db_session, monkeypatch):
    has_albums = _artist_with_albums(db_session, "Has Albums", [("LP", "rg-lp", "2000")])
    has_albums.musicbrainz_id = "mb-has"
    unlinked = Artist(name="Unlinked")
    db_session.add(unlinked)
    db_session.commit()
    fetched = []
    monkeypatch.setattr(analysis_queue, "ingest_album_shells", lambda db, a: fetched.append(a.id))

    analysis_queue._fetch_album_shells(db_session, has_albums)
    analysis_queue._fetch_album_shells(db_session, unlinked)

    assert fetched == []


def test_worker_album_fetch_failure_is_not_fatal(db_session, monkeypatch):
    artist = Artist(name="Boards of Canada", musicbrainz_id="mb-boc")
    db_session.add(artist)
    db_session.commit()

    def boom(db, a):
        raise httpx.ConnectError("musicbrainz down")

    monkeypatch.setattr(analysis_queue, "ingest_album_shells", boom)

    analysis_queue._fetch_album_shells(db_session, artist)  # does not raise
