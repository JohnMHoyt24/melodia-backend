"""Conversational recommendation, with memory: each turn gets the thread's prior

messages as context (see gemini.chat_turn), then any newly suggested artists are
verified/enriched via the existing MusicBrainz+Last.fm ingest pipeline (no extra
Gemini calls) - same verify-then-cache approach as the old one-shot /recommend, now
scoped to a persisted, per-user chat thread instead of a single stateless request.
"""

import logging
import uuid

import httpx
from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.chat import ChatMessage, ChatThread
from app.services import analysis_queue, gemini, rag
from app.services.ingest import ArtistNotFound, ingest_artist


logger = logging.getLogger(__name__)

_RETRIEVAL_LIMIT = 5
# Follow-ups like "more like the first one" embed poorly on their own, so retrieval
# also sees the user's previous messages.
_RETRIEVAL_USER_TURNS = 3


def _retrieve_library_context(
    db: Session, user_id: uuid.UUID, history: list[dict[str, str]], message: str
) -> list[tuple[Artist, float]]:
    """RAG step for a chat turn: nearest analyzed artists in the user's own library, or
    [] on failure.

    Retrieval only enriches the turn, so a Gemini embedding failure (quota, outage)
    degrades to an ungrounded reply rather than failing the whole message.
    """
    recent_user_turns = [m["content"] for m in history if m["role"] == "user"]
    query = "\n".join([*recent_user_turns[-(_RETRIEVAL_USER_TURNS - 1) :], message])
    try:
        return rag.retrieve(db, query, limit=_RETRIEVAL_LIMIT, user_id=user_id)
    except httpx.HTTPError:
        logger.warning("chat retrieval failed; replying without library context", exc_info=True)
        return []


def create_thread(db: Session, user_id: uuid.UUID, message: str) -> ChatThread:
    thread = ChatThread(user_id=user_id)
    db.add(thread)
    db.flush()
    send_message(db, thread, message)
    return thread


def send_message(db: Session, thread: ChatThread, content: str) -> ChatMessage:
    history = [{"role": m.role, "content": m.content} for m in thread.messages]

    library_hits = _retrieve_library_context(db, thread.user_id, history, content)
    result = gemini.chat_turn(
        history,
        content,
        context=rag.format_context(library_hits) if library_hits else None,
    )

    resolved_artists = []
    for suggestion in result["artists"]:
        try:
            artist = ingest_artist(db, suggestion["name"], album_limit=0)
        except ArtistNotFound:
            continue
        analysis_queue.maybe_enqueue(artist)
        resolved_artists.append(
            {
                "id": str(artist.id),
                "name": artist.name,
                "genres": [genre.name for genre in artist.genres],
                "reason": suggestion["reason"],
            }
        )

    db.add(ChatMessage(thread_id=thread.id, role="user", content=content))
    assistant_message = ChatMessage(
        thread_id=thread.id,
        role="assistant",
        content=result["reply"],
        recommended_artists=resolved_artists or None,
        sources=[
            {"id": str(a.id), "name": a.name, "similarity": round(sim, 4)}
            for a, sim in library_hits
        ]
        or None,
    )
    db.add(assistant_message)

    if thread.title is None:
        thread.title = content[:60]

    db.commit()
    db.refresh(assistant_message)
    return assistant_message
