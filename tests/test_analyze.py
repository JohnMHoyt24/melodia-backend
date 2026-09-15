import pytest

from app.models import Artist, Genre
from app.services import analyze, gemini


@pytest.fixture(autouse=True)
def _mock_gemini(monkeypatch):
    monkeypatch.setattr(
        gemini,
        "classify_characteristics",
        lambda name, genres: {
            "energy": 0.5,
            "valence": 0.5,
            "melody": 0.5,
            "aggression": 0.5,
            "danceability": 0.5,
            "complexity": 0.5,
        },
    )
    monkeypatch.setattr(gemini, "embed_text", lambda text: [0.1] * 768)


def test_analyze_artist_stores_characteristics_and_embedding(db_session):
    artist = Artist(name="Boards of Canada")
    artist.genres.append(Genre(name="idm"))
    db_session.add(artist)
    db_session.commit()

    result = analyze.analyze_artist(db_session, artist)

    assert result.characteristics == {
        "energy": 0.5,
        "valence": 0.5,
        "melody": 0.5,
        "aggression": 0.5,
        "danceability": 0.5,
        "complexity": 0.5,
    }
    assert result.embedding == [0.1] * 768


def test_analyze_artist_uses_genre_names_in_summary(db_session, monkeypatch):
    captured = {}

    def fake_embed_text(text):
        captured["text"] = text
        return [0.0] * 768

    monkeypatch.setattr(gemini, "embed_text", fake_embed_text)

    artist = Artist(name="Autechre")
    artist.genres.append(Genre(name="idm"))
    artist.genres.append(Genre(name="glitch"))
    db_session.add(artist)
    db_session.commit()

    analyze.analyze_artist(db_session, artist)

    assert "Autechre" in captured["text"]
    assert "idm" in captured["text"]
    assert "glitch" in captured["text"]
