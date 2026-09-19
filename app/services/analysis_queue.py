"""In-process background queue that analyzes artists one at a time.

Analysis is two Gemini calls per artist (app/services/analyze.py) against a small
free-tier quota, so it can't run inline in a request or fan out in parallel. A single
worker thread drains a FIFO queue with a pause between jobs, which keeps us under the
per-minute limit; gemini._post already retries the 429s that still slip through.

Deliberately not Redis/RQ (PLAN.md's eventual answer): "needs analysis" is derivable
from the database (`artists.embedding IS NULL`), so nothing is lost when the process
restarts - the artist page or the next ingest simply re-enqueues. Status here is
in-memory only and covers queued / running / failed; done-ness comes from the DB.
"""

import logging
import queue
import threading
import time
import uuid

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.artist import Artist
from app.services.analyze import analyze_artist

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: queue.Queue[uuid.UUID] = queue.Queue()
_status: dict[uuid.UUID, str] = {}
_errors: dict[uuid.UUID, str] = {}
_worker: threading.Thread | None = None


def _process(artist_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        artist = db.get(Artist, artist_id)
        if artist is None or artist.embedding is not None:
            return
        analyze_artist(db, artist)


def _run() -> None:
    while True:
        artist_id = _jobs.get()
        with _lock:
            _status[artist_id] = "running"
        try:
            _process(artist_id)
        except Exception as exc:  # noqa: BLE001 - the worker must survive any one job
            logger.warning("analysis failed for artist %s", artist_id, exc_info=True)
            with _lock:
                _status[artist_id] = "failed"
                _errors[artist_id] = str(exc)
        else:
            with _lock:
                _status.pop(artist_id, None)
                _errors.pop(artist_id, None)
        finally:
            _jobs.task_done()
        time.sleep(get_settings().analysis_delay_seconds)


def _ensure_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_run, name="analysis-worker", daemon=True)
        _worker.start()


def enqueue(artist_id: uuid.UUID) -> str:
    """Queue an artist for analysis (retrying if it previously failed).

    Returns the artist's status: "queued" or "running".
    """
    with _lock:
        current = _status.get(artist_id)
        if current in ("queued", "running"):
            return current
        _status[artist_id] = "queued"
        _errors.pop(artist_id, None)
        _jobs.put(artist_id)
        _ensure_worker()
        return "queued"


def maybe_enqueue(artist: Artist) -> None:
    """Auto-analyze hook for ingest paths: queue unanalyzed artists when enabled."""
    if get_settings().auto_analyze and artist.embedding is None:
        enqueue(artist.id)


def in_flight_status(artist_id: uuid.UUID) -> tuple[str | None, str | None]:
    """(status, error) for a queued/running/failed artist, or (None, None)."""
    with _lock:
        return _status.get(artist_id), _errors.get(artist_id)


def wait_until_idle() -> None:
    """Block until every queued job has finished (used by tests)."""
    _jobs.join()
