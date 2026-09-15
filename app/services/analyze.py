"""Runs Gemini classification + embedding for an already-ingested artist.

Deliberately separate from app/services/ingest.py: ingestion (Milestone 2) pulls
canonical metadata from MusicBrainz/Last.fm, analysis (Milestone 3) is the LLM step
on top of it. Keeping them apart means an artist can be re-analyzed (e.g. after a
prompt change) without re-ingesting, and vice versa.
"""

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.services import gemini


def analyze_artist(db: Session, artist: Artist) -> Artist:
    genre_names = [genre.name for genre in artist.genres]

    characteristics = gemini.classify_characteristics(artist.name, genre_names)

    summary = artist.name
    if genre_names:
        summary = f"{artist.name} - genres: {', '.join(genre_names)}"
    embedding = gemini.embed_text(summary)

    artist.characteristics = characteristics
    artist.embedding = embedding
    db.commit()
    db.refresh(artist)
    return artist
