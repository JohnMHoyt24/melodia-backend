from app.models import Artist, Genre
from app.services import gemini, rag


def _artist(db_session):
    artist = Artist(
        name="Boards of Canada",
        characteristics={"energy": 0.3, "valence": 0.5},
        genres=[Genre(name="idm")],
    )
    db_session.add(artist)
    db_session.commit()
    return artist


def test_ask_retrieves_then_generates_with_context(db_session, monkeypatch):
    artist = _artist(db_session)
    captured = {}

    monkeypatch.setattr(gemini, "embed_text", lambda text: [0.1] * 768)
    monkeypatch.setattr(
        rag, "find_nearest_artists", lambda db, emb, limit, user_id=None: [(artist, 0.9)]
    )

    def fake_answer(question, context):
        captured["question"] = question
        captured["context"] = context
        return "Try Boards of Canada."

    monkeypatch.setattr(gemini, "answer_with_context", fake_answer)

    result = rag.ask(db_session, "something mellow")

    assert result.answer == "Try Boards of Canada."
    assert result.sources == [(artist, 0.9)]
    assert "Boards of Canada" in captured["context"]
    assert "idm" in captured["context"]
    assert "energy=0.30" in captured["context"]


def test_ask_with_no_analyzed_artists_skips_generation(db_session, monkeypatch):
    monkeypatch.setattr(gemini, "embed_text", lambda text: [0.1] * 768)
    monkeypatch.setattr(rag, "find_nearest_artists", lambda db, emb, limit, user_id=None: [])

    def boom(*args):
        raise AssertionError("generation should not run without context")

    monkeypatch.setattr(gemini, "answer_with_context", boom)

    result = rag.ask(db_session, "anything")

    assert result.sources == []


def test_ask_endpoint(client, db_session, monkeypatch):
    artist = _artist(db_session)
    monkeypatch.setattr(gemini, "embed_text", lambda text: [0.1] * 768)
    monkeypatch.setattr(
        rag, "find_nearest_artists", lambda db, emb, limit, user_id=None: [(artist, 0.9)]
    )
    monkeypatch.setattr(gemini, "answer_with_context", lambda q, c: "Boards of Canada.")

    response = client.post("/artists/ask", json={"question": "mellow?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Boards of Canada."
    assert body["sources"][0]["name"] == "Boards of Canada"
