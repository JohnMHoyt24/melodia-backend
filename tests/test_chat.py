import uuid

from app.services import chat, gemini
from app.services.ingest import ArtistNotFound
from tests.conftest import TEST_USER_ID


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


def test_start_thread_endpoint(authed_client, db_session, monkeypatch):
    monkeypatch.setattr(
        gemini,
        "chat_turn",
        lambda history, message, count=5: {
            "reply": "Sure, jangly picks incoming:",
            "artists": [{"name": "Yo La Tengo", "reason": "Jangly guitars."}],
        },
    )
    monkeypatch.setattr(
        chat, "ingest_artist", _fake_ingest_artist({"Yo La Tengo": ["indie rock"]})
    )

    response = authed_client.post(
        "/chat/threads", json={"message": "like Dinosaur Jr but janglier"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "like Dinosaur Jr but janglier"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assistant = body["messages"][1]
    assert assistant["content"] == "Sure, jangly picks incoming:"
    assert assistant["recommended_artists"] == [
        {
            "id": assistant["recommended_artists"][0]["id"],
            "name": "Yo La Tengo",
            "genres": ["indie rock"],
            "reason": "Jangly guitars.",
        }
    ]


def test_start_thread_drops_unresolvable_suggestions(authed_client, monkeypatch):
    monkeypatch.setattr(
        gemini,
        "chat_turn",
        lambda history, message, count=5: {
            "reply": "Here's one:",
            "artists": [
                {"name": "Totally Made Up Band Xyz", "reason": "does not exist"},
                {"name": "Yo La Tengo", "reason": "Jangly guitars."},
            ],
        },
    )
    monkeypatch.setattr(
        chat, "ingest_artist", _fake_ingest_artist({"Yo La Tengo": ["indie rock"]})
    )

    response = authed_client.post("/chat/threads", json={"message": "anything"})

    names = [a["name"] for a in response.json()["messages"][1]["recommended_artists"]]
    assert names == ["Yo La Tengo"]


def test_follow_up_message_uses_thread_history(authed_client, monkeypatch):
    monkeypatch.setattr(
        gemini,
        "chat_turn",
        lambda history, message, count=5: {"reply": "First reply", "artists": []},
    )
    thread_id = authed_client.post("/chat/threads", json={"message": "hi"}).json()["id"]

    seen_history = {}

    def fake_chat_turn(history, message, count=5):
        seen_history["history"] = history
        return {"reply": "It's more mellow.", "artists": []}

    monkeypatch.setattr(gemini, "chat_turn", fake_chat_turn)

    response = authed_client.post(
        f"/chat/threads/{thread_id}/messages", json={"message": "why that one?"}
    )

    assert response.status_code == 200
    assert response.json()["content"] == "It's more mellow."
    assert [m["role"] for m in seen_history["history"]] == ["user", "assistant"]


def test_list_and_get_thread(authed_client, monkeypatch):
    monkeypatch.setattr(
        gemini, "chat_turn", lambda history, message, count=5: {"reply": "hey", "artists": []}
    )
    created = authed_client.post("/chat/threads", json={"message": "hi there"}).json()

    listed = authed_client.get("/chat/threads").json()
    assert [t["id"] for t in listed] == [created["id"]]

    fetched = authed_client.get(f"/chat/threads/{created['id']}")
    assert fetched.status_code == 200
    assert len(fetched.json()["messages"]) == 2


def test_delete_thread(authed_client, monkeypatch):
    monkeypatch.setattr(
        gemini, "chat_turn", lambda history, message, count=5: {"reply": "hey", "artists": []}
    )
    thread_id = authed_client.post("/chat/threads", json={"message": "hi"}).json()["id"]

    delete_response = authed_client.delete(f"/chat/threads/{thread_id}")
    assert delete_response.status_code == 204
    assert authed_client.get(f"/chat/threads/{thread_id}").status_code == 404


def test_thread_not_visible_to_other_user(authed_client, client, db_session, monkeypatch):
    from app.core.auth import get_current_user_id
    from app.main import app

    monkeypatch.setattr(
        gemini, "chat_turn", lambda history, message, count=5: {"reply": "hey", "artists": []}
    )
    thread_id = authed_client.post("/chat/threads", json={"message": "hi"}).json()["id"]

    other_user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: other_user_id
    try:
        response = client.get(f"/chat/threads/{thread_id}")
    finally:
        app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID

    assert response.status_code == 404


def test_chat_endpoints_require_auth(client):
    assert client.get("/chat/threads").status_code == 401
    assert client.post("/chat/threads", json={"message": "hi"}).status_code == 401


def test_chat_endpoint_rejects_garbage_token(client):
    response = client.get(
        "/chat/threads", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert response.status_code == 401
