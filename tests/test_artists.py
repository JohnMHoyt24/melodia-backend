def test_create_and_get_artist(client):
    create_response = client.post("/artists", json={"name": "Boards of Canada"})
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Boards of Canada"
    assert created["musicbrainz_id"] is None

    get_response = client.get(f"/artists/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Boards of Canada"


def test_list_artists(client):
    client.post("/artists", json={"name": "Aphex Twin"})
    client.post("/artists", json={"name": "Autechre"})

    response = client.get("/artists")
    assert response.status_code == 200
    names = [artist["name"] for artist in response.json()]
    assert names == ["Aphex Twin", "Autechre"]


def test_get_missing_artist_404(client):
    response = client.get("/artists/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_ingest_artist(client, monkeypatch):
    from app.api import artists as artists_api

    def fake_ingest_artist(db, name, album_limit=10):
        from app.models import Artist

        artist = Artist(name=name, musicbrainz_id="mbid-1")
        db.add(artist)
        db.commit()
        db.refresh(artist)
        return artist

    monkeypatch.setattr(artists_api, "ingest_artist", fake_ingest_artist)

    response = client.post("/artists/ingest", json={"name": "Boards of Canada"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Boards of Canada"
    assert body["musicbrainz_id"] == "mbid-1"
    assert body["genres"] == []
    assert body["albums"] == []


def test_ingest_artist_not_found(client, monkeypatch):
    from app.api import artists as artists_api
    from app.services.ingest import ArtistNotFound

    def fake_ingest_artist(db, name, album_limit=10):
        raise ArtistNotFound(f"No MusicBrainz artist found for {name!r}")

    monkeypatch.setattr(artists_api, "ingest_artist", fake_ingest_artist)

    response = client.post("/artists/ingest", json={"name": "Nonexistent Band"})

    assert response.status_code == 404


def test_analyze_artist(client, db_session, monkeypatch):
    from app.api import artists as artists_api
    from app.models import Artist

    artist = Artist(name="Boards of Canada")
    db_session.add(artist)
    db_session.commit()

    def fake_analyze_artist(db, artist):
        artist.characteristics = {"energy": 0.5}
        db.commit()
        db.refresh(artist)
        return artist

    monkeypatch.setattr(artists_api, "analyze_artist", fake_analyze_artist)

    response = client.post(f"/artists/{artist.id}/analyze")

    assert response.status_code == 200
    assert response.json()["characteristics"] == {"energy": 0.5}


def test_analyze_artist_not_found(client):
    response = client.post("/artists/00000000-0000-0000-0000-000000000000/analyze")
    assert response.status_code == 404


def test_analyze_artist_gemini_not_configured(client, db_session, monkeypatch):
    from app.api import artists as artists_api
    from app.models import Artist
    from app.services.gemini import GeminiNotConfigured

    artist = Artist(name="Boards of Canada")
    db_session.add(artist)
    db_session.commit()

    def fake_analyze_artist(db, artist):
        raise GeminiNotConfigured("GEMINI_API_KEY is not set")

    monkeypatch.setattr(artists_api, "analyze_artist", fake_analyze_artist)

    response = client.post(f"/artists/{artist.id}/analyze")

    assert response.status_code == 503


def test_load_albums(client, db_session, monkeypatch):
    from app.api import artists as artists_api
    from app.models import Artist, Album

    artist = Artist(name="Boards of Canada", musicbrainz_id="mbid-1")
    db_session.add(artist)
    db_session.commit()

    def fake_ingest_album_shells(db, artist, limit=10):
        album = Album(artist_id=artist.id, title="Geogaddi", musicbrainz_id="mbid-album-1")
        db.add(album)
        db.commit()
        return [album]

    monkeypatch.setattr(artists_api, "ingest_album_shells", fake_ingest_album_shells)

    response = client.post(f"/artists/{artist.id}/albums")

    assert response.status_code == 200
    body = response.json()
    assert len(body["albums"]) == 1
    assert body["albums"][0]["title"] == "Geogaddi"
    assert body["albums"][0]["tracks"] == []


def test_load_albums_artist_not_found(client):
    response = client.post("/artists/00000000-0000-0000-0000-000000000000/albums")
    assert response.status_code == 404


def test_load_albums_no_musicbrainz_link(client, db_session, monkeypatch):
    from app.api import artists as artists_api
    from app.models import Artist
    from app.services.ingest import ArtistNotFound

    artist = Artist(name="No MBID Artist")
    db_session.add(artist)
    db_session.commit()

    def fake_ingest_album_shells(db, artist, limit=10):
        raise ArtistNotFound(f"{artist.name!r} has no MusicBrainz link")

    monkeypatch.setattr(artists_api, "ingest_album_shells", fake_ingest_album_shells)

    response = client.post(f"/artists/{artist.id}/albums")

    assert response.status_code == 409


def test_load_tracks(client, db_session, monkeypatch):
    from app.api import albums as albums_api
    from app.models import Artist, Album, Track

    artist = Artist(name="Boards of Canada", musicbrainz_id="mbid-1")
    db_session.add(artist)
    db_session.commit()
    album = Album(artist_id=artist.id, title="Geogaddi", musicbrainz_id="mbid-album-1")
    db_session.add(album)
    db_session.commit()

    def fake_ingest_album_tracks(db, album):
        track = Track(album_id=album.id, title="1969", track_number=1)
        db.add(track)
        db.commit()
        db.refresh(album)
        return album

    monkeypatch.setattr(albums_api, "ingest_album_tracks", fake_ingest_album_tracks)

    response = client.post(f"/albums/{album.id}/tracks")

    assert response.status_code == 200
    body = response.json()
    assert body["tracks"] == [
        {"id": body["tracks"][0]["id"], "title": "1969", "track_number": 1, "length_ms": None}
    ]


def test_load_tracks_album_not_found(client):
    response = client.post("/albums/00000000-0000-0000-0000-000000000000/tracks")
    assert response.status_code == 404


def test_similar_artists(client, db_session, monkeypatch):
    from app.api import artists as artists_api
    from app.models import Artist

    artist = Artist(name="Boards of Canada")
    other = Artist(name="Autechre")
    db_session.add_all([artist, other])
    db_session.commit()

    monkeypatch.setattr(
        artists_api, "find_similar_artists", lambda db, a, limit=10: [(other, 0.92)]
    )

    response = client.get(f"/artists/{artist.id}/similar")

    assert response.status_code == 200
    assert response.json() == [{"id": str(other.id), "name": "Autechre", "similarity": 0.92}]


def test_similar_artists_not_analyzed(client, db_session):
    from app.models import Artist

    artist = Artist(name="Boards of Canada")
    db_session.add(artist)
    db_session.commit()

    response = client.get(f"/artists/{artist.id}/similar")

    assert response.status_code == 409


def test_similar_artists_not_found(client):
    response = client.get("/artists/00000000-0000-0000-0000-000000000000/similar")
    assert response.status_code == 404
