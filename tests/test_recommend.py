import pytest

from app.services import gemini, ingest, recommend
from app.services.ingest import ArtistNotFound


def _fake_ingest_artist(names_and_genres):
    def _ingest(db, name, album_limit=10):
        from app.models import Artist, Genre

        if name not in names_and_genres:
            raise ArtistNotFound(f"No MusicBrainz artist found for {name!r}")
        artist = Artist(name=name)
        for genre_name in names_and_genres[name]:
            artist.genres.append(Genre(name=genre_name))
        db.add(artist)
        db.commit()
        db.refresh(artist)
        return artist

    return _ingest


def test_recommend_verifies_and_enriches_suggestions(db_session, monkeypatch):
    monkeypatch.setattr(
        gemini,
        "suggest_artists",
        lambda prompt, count=5: [
            {"name": "Yo La Tengo", "reason": "Jangly guitars, dreamy feel."},
            {"name": "The Feelies", "reason": "Chiming guitar tones."},
        ],
    )
    monkeypatch.setattr(
        recommend,
        "ingest_artist",
        _fake_ingest_artist(
            {"Yo La Tengo": ["indie rock"], "The Feelies": ["jangle pop"]}
        ),
    )

    results = recommend.recommend(db_session, "like Dinosaur Jr but janglier")

    assert [artist.name for artist, _ in results] == ["Yo La Tengo", "The Feelies"]
    assert results[0][1] == "Jangly guitars, dreamy feel."
    assert [g.name for g in results[0][0].genres] == ["indie rock"]


def test_recommend_skips_unresolvable_suggestions(db_session, monkeypatch):
    monkeypatch.setattr(
        gemini,
        "suggest_artists",
        lambda prompt, count=5: [
            {"name": "Totally Made Up Band Xyz", "reason": "does not exist"},
            {"name": "Yo La Tengo", "reason": "Jangly guitars."},
        ],
    )
    monkeypatch.setattr(
        recommend, "ingest_artist", _fake_ingest_artist({"Yo La Tengo": ["indie rock"]})
    )

    results = recommend.recommend(db_session, "like Dinosaur Jr but janglier")

    assert [artist.name for artist, _ in results] == ["Yo La Tengo"]


def test_recommend_endpoint(client, db_session, monkeypatch):
    from app.api import recommend as recommend_api
    from app.models import Artist, Genre

    def fake_recommend_service(db, prompt, count=5):
        artist = Artist(name="Yo La Tengo")
        artist.genres.append(Genre(name="indie rock"))
        db.add(artist)
        db.commit()
        db.refresh(artist)
        return [(artist, "Jangly guitars, dreamy feel.")]

    monkeypatch.setattr(recommend_api, "recommend_service", fake_recommend_service)

    response = client.post("/recommend", json={"prompt": "like Dinosaur Jr but janglier"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Yo La Tengo"
    assert body[0]["genres"] == ["indie rock"]
    assert body[0]["reason"] == "Jangly guitars, dreamy feel."


def test_recommend_endpoint_validates_count(client):
    response = client.post("/recommend", json={"prompt": "anything", "count": 20})
    assert response.status_code == 422
