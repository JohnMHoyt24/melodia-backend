"""pgvector-backed "similar artists" lookup.

Requires a real Postgres + pgvector database - `Artist.embedding.cosine_distance()`
compiles to pgvector's `<=>` operator, which SQLite (used in the test suite) doesn't
understand. Verified against real Supabase instead of unit-tested; see PLAN.md.
"""

from sqlalchemy.orm import Session

from app.models.artist import Artist


class ArtistNotAnalyzed(Exception):
    pass


def find_similar_artists(db: Session, artist: Artist, limit: int = 10) -> list[tuple[Artist, float]]:
    if artist.embedding is None:
        raise ArtistNotAnalyzed(f"{artist.name!r} has not been analyzed yet - no embedding")

    distance = Artist.embedding.cosine_distance(artist.embedding)
    rows = (
        db.query(Artist, distance.label("distance"))
        .filter(Artist.id != artist.id, Artist.embedding.isnot(None))
        .order_by(distance)
        .limit(limit)
        .all()
    )
    return [(other, 1.0 - dist) for other, dist in rows]
