from app.models import Artist, Genre


def test_search_matches_by_name(client, db_session):
    artist = Artist(name="Boards of Canada")
    artist.genres.append(Genre(name="idm"))
    db_session.add(artist)
    db_session.add(Artist(name="Autechre"))
    db_session.commit()

    response = client.get("/search", params={"q": "boards"})
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["name"] == "Boards of Canada"
    assert results[0]["genres"] == ["idm"]


def test_search_no_match(client, db_session):
    db_session.add(Artist(name="Autechre"))
    db_session.commit()

    response = client.get("/search", params={"q": "nonexistent"})
    assert response.status_code == 200
    assert response.json() == []


def test_search_requires_query(client):
    response = client.get("/search")
    assert response.status_code == 422
