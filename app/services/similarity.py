"""pgvector-backed "similar artists" lookup.

Requires a real Postgres + pgvector database - `Artist.embedding.cosine_distance()`
compiles to pgvector's `<=>` operator, which SQLite (used in the test suite) doesn't
understand. Verified against real Supabase instead of unit-tested; see PLAN.md.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.models.user_artist import UserArtist


class ArtistNotAnalyzed(Exception):
    pass


def find_nearest_artists(
    db: Session,
    embedding: list[float],
    limit: int = 10,
    exclude_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> list[tuple[Artist, float]]:
    """Nearest analyzed artists to an arbitrary vector, as (artist, cosine similarity).

    Shared by find_similar_artists (seeded from an artist's own embedding) and the RAG
    retriever in app/services/rag.py (seeded from an embedded free-text question).
    With `user_id`, candidates are limited to that user's personal library
    (app/models/user_artist.py) instead of the whole shared catalog.
    """
    distance = Artist.embedding.cosine_distance(embedding)
    query = db.query(Artist, distance.label("distance")).filter(Artist.embedding.isnot(None))
    if user_id is not None:
        query = query.join(UserArtist, UserArtist.artist_id == Artist.id).filter(
            UserArtist.user_id == user_id
        )
    if exclude_id is not None:
        query = query.filter(Artist.id != exclude_id)
    rows = query.order_by(distance).limit(limit).all()
    return [(other, 1.0 - dist) for other, dist in rows]


def find_similar_artists(
    db: Session, artist: Artist, limit: int = 10, user_id: uuid.UUID | None = None
) -> list[tuple[Artist, float]]:
    if artist.embedding is None:
        raise ArtistNotAnalyzed(f"{artist.name!r} has not been analyzed yet - no embedding")

    return find_nearest_artists(
        db, artist.embedding, limit=limit, exclude_id=artist.id, user_id=user_id
    )
