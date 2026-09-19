"""Retrieval-augmented answers over the artists already analyzed in the database.

- Retrieve: embed the question with the same model used for artist embeddings and pull
  the nearest artists via pgvector (app/services/similarity.py).
- Augment: render each hit's genres + characteristic scores into a context block.
- Generate: one Gemini call that answers using only that context.

Two Gemini calls per question (one embedding, one generation) - see PLAN.md for why
call count matters on the free tier. Retrieval needs Postgres + pgvector, so like
similarity it's verified against real Supabase rather than the SQLite suite; the tests
stub the retrieval step.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.services import gemini
from app.services.similarity import find_nearest_artists


@dataclass
class RagAnswer:
    answer: str
    sources: list[tuple[Artist, float]]


def format_context(sources: list[tuple[Artist, float]]) -> str:
    lines = []
    for artist, similarity in sources:
        genres = ", ".join(genre.name for genre in artist.genres) or "unknown"
        scores = ", ".join(
            f"{name}={score:.2f}" for name, score in (artist.characteristics or {}).items()
        )
        lines.append(
            f"- {artist.name} (relevance {similarity:.2f}) - genres: {genres}; "
            f"characteristics: {scores or 'not analyzed'}"
        )
    return "\n".join(lines)


def retrieve(
    db: Session, text: str, limit: int = 5, user_id: uuid.UUID | None = None
) -> list[tuple[Artist, float]]:
    """Embed `text` and return the nearest analyzed artists as (artist, similarity).

    With `user_id`, only that user's personal library is searched.
    """
    return find_nearest_artists(db, gemini.embed_text(text), limit=limit, user_id=user_id)


def ask(db: Session, question: str, limit: int = 5) -> RagAnswer:
    sources = retrieve(db, question, limit=limit)
    if not sources:
        return RagAnswer(
            answer="No analyzed artists in the library yet, so I can't answer that.",
            sources=[],
        )

    answer = gemini.answer_with_context(question, format_context(sources))
    return RagAnswer(answer=answer, sources=sources)
