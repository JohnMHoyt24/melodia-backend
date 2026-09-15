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
