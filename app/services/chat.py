"""Conversational recommendation, with memory: each turn gets the thread's prior

messages as context (see gemini.chat_turn), then any newly suggested artists are
verified/enriched via the existing MusicBrainz+Last.fm ingest pipeline (no extra
Gemini calls) - same verify-then-cache approach as the old one-shot /recommend, now
scoped to a persisted, per-user chat thread instead of a single stateless request.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatThread
from app.services import gemini
from app.services.ingest import ArtistNotFound, ingest_artist


def create_thread(db: Session, user_id: uuid.UUID, message: str) -> ChatThread:
    thread = ChatThread(user_id=user_id)
    db.add(thread)
    db.flush()
    send_message(db, thread, message)
    return thread


def send_message(db: Session, thread: ChatThread, content: str) -> ChatMessage:
    history = [{"role": m.role, "content": m.content} for m in thread.messages]

    result = gemini.chat_turn(history, content)

    resolved_artists = []
    for suggestion in result["artists"]:
        try:
            artist = ingest_artist(db, suggestion["name"], album_limit=0)
        except ArtistNotFound:
            continue
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
    )
    db.add(assistant_message)

    if thread.title is None:
        thread.title = content[:60]

    db.commit()
    db.refresh(assistant_message)
    return assistant_message
