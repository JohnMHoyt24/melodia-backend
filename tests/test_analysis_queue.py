import uuid

import pytest

from app.models import Artist
from app.services import analysis_queue


@pytest.fixture(autouse=True)
def clean_queue_state():
    analysis_queue.wait_until_idle()
    analysis_queue._status.clear()
    analysis_queue._errors.clear()
    yield
    analysis_queue.wait_until_idle()
    analysis_queue._status.clear()
    analysis_queue._errors.clear()


def _artist(db_session, embedding=None):
    artist = Artist(name="Boards of Canada", embedding=embedding)
    db_session.add(artist)
    db_session.commit()
    return artist


def test_enqueue_processes_job_and_clears_status(monkeypatch):
    processed = []
    monkeypatch.setattr(analysis_queue, "_process", processed.append)
    artist_id = uuid.uuid4()

    assert analysis_queue.enqueue(artist_id) == "queued"
    analysis_queue.wait_until_idle()

    assert processed == [artist_id]
    assert analysis_queue.in_flight_status(artist_id) == (None, None)


def test_failed_job_is_recorded_and_worker_survives(monkeypatch):
    calls = []

    def flaky(artist_id):
        calls.append(artist_id)
        if len(calls) == 1:
            raise RuntimeError("quota exhausted")

    monkeypatch.setattr(analysis_queue, "_process", flaky)
    first, second = uuid.uuid4(), uuid.uuid4()

    analysis_queue.enqueue(first)
    analysis_queue.enqueue(second)
    analysis_queue.wait_until_idle()

    assert analysis_queue.in_flight_status(first) == ("failed", "quota exhausted")
    assert analysis_queue.in_flight_status(second) == (None, None)

    # A failed artist can be retried.
    assert analysis_queue.enqueue(first) == "queued"
    analysis_queue.wait_until_idle()
    assert analysis_queue.in_flight_status(first) == (None, None)


def test_enqueue_dedupes_queued_artist(monkeypatch):
    monkeypatch.setattr(analysis_queue, "_status", {})
    artist_id = uuid.uuid4()
    analysis_queue._status[artist_id] = "queued"

    assert analysis_queue.enqueue(artist_id) == "queued"
    assert analysis_queue._jobs.empty()
    analysis_queue._status.clear()


def test_maybe_enqueue_respects_setting_and_existing_embedding(db_session, monkeypatch):
    processed = []
    monkeypatch.setattr(analysis_queue, "_process", processed.append)
    unanalyzed = _artist(db_session)
    analyzed = Artist(name="Other", embedding=[0.1] * 768)
    db_session.add(analyzed)
    db_session.commit()

    # AUTO_ANALYZE=false under tests (conftest).
    analysis_queue.maybe_enqueue(unanalyzed)
    analysis_queue.wait_until_idle()
    assert processed == []

    class On:
        auto_analyze = True
        analysis_delay_seconds = 0

    monkeypatch.setattr(analysis_queue, "get_settings", lambda: On())
    analysis_queue.maybe_enqueue(analyzed)
    analysis_queue.maybe_enqueue(unanalyzed)
    analysis_queue.wait_until_idle()
    assert processed == [unanalyzed.id]


def test_analysis_endpoints(client, db_session, monkeypatch):
    processed = []
    monkeypatch.setattr(analysis_queue, "_process", processed.append)
    artist = _artist(db_session)

    assert client.get(f"/artists/{artist.id}/analysis").json() == {"status": "idle", "error": None}

    response = client.post(f"/artists/{artist.id}/analysis")
    assert response.status_code == 202
    assert response.json()["status"] in ("queued", "running")
    analysis_queue.wait_until_idle()
    assert processed == [artist.id]

    artist.embedding = [0.1] * 768
    db_session.commit()
    assert client.get(f"/artists/{artist.id}/analysis").json()["status"] == "done"
    assert client.post(f"/artists/{uuid.uuid4()}/analysis").status_code == 404
