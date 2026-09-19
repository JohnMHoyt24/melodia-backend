import uuid

from app.api import library
from app.core.auth import get_current_user_id
from app.main import app
from app.models import Artist, Genre, UserArtist
from tests.conftest import TEST_USER_ID


def _artist(db_session, name="Boards of Canada", genres=("idm",)):
    artist = Artist(name=name, genres=[Genre(name=g) for g in genres])
    db_session.add(artist)
    db_session.commit()
    return artist


def test_library_requires_auth(client):
    assert client.get("/library").status_code == 401
    assert client.put(f"/library/{uuid.uuid4()}").status_code == 401


def test_add_list_and_remove(authed_client, db_session):
    artist = _artist(db_session)

    added = authed_client.put(f"/library/{artist.id}")
    assert added.status_code == 200
    assert added.json()["name"] == "Boards of Canada"
    assert added.json()["genres"] == ["idm"]

    listed = authed_client.get("/library").json()
    assert [a["id"] for a in listed] == [str(artist.id)]

    assert authed_client.delete(f"/library/{artist.id}").status_code == 204
    assert authed_client.get("/library").json() == []


def test_add_is_idempotent_and_remove_of_missing_is_ok(authed_client, db_session):
    artist = _artist(db_session)

    authed_client.put(f"/library/{artist.id}")
    authed_client.put(f"/library/{artist.id}")

    assert len(authed_client.get("/library").json()) == 1
    assert authed_client.delete(f"/library/{uuid.uuid4()}").status_code == 204


def test_add_unknown_artist_404(authed_client):
    assert authed_client.put(f"/library/{uuid.uuid4()}").status_code == 404


def test_libraries_are_per_user(authed_client, db_session):
    artist = _artist(db_session)
    other_user = uuid.uuid4()
    db_session.add(UserArtist(user_id=other_user, artist_id=artist.id))
    db_session.commit()

    assert authed_client.get("/library").json() == []

    app.dependency_overrides[get_current_user_id] = lambda: other_user
    try:
        assert len(authed_client.get("/library").json()) == 1
    finally:
        app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID


def test_similar_in_library_is_scoped_to_caller(authed_client, db_session, monkeypatch):
    artist = _artist(db_session)
    neighbour = _artist(db_session, name="Autechre", genres=())
    seen = {}

    def fake_similar(db, a, limit=10, user_id=None):
        seen.update(artist=a, limit=limit, user_id=user_id)
        return [(neighbour, 0.8)]

    monkeypatch.setattr(library, "find_similar_artists", fake_similar)

    response = authed_client.get(f"/library/{artist.id}/similar")

    assert response.status_code == 200
    assert response.json() == [
        {"id": str(neighbour.id), "name": "Autechre", "similarity": 0.8}
    ]
    assert seen["user_id"] == TEST_USER_ID
    assert seen["limit"] == 6
