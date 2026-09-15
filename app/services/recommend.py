"""Conversational recommendation: one Gemini call to suggest real artists for a
free-text prompt, then local verification/enrichment (MusicBrainz + Last.fm, no extra
Gemini calls) via the existing ingest pipeline.

Deliberately does not run app/services/analyze.py's characteristic/embedding analysis
on suggested artists - that's 2 more Gemini calls per artist, which would blow the
free-tier daily quota on a single conversation. See PLAN.md for the quota finding that
drove this design and the tool-calling agent loop it explicitly does not implement yet.
"""

from sqlalchemy.orm import Session

from app.models.artist import Artist
from app.services import gemini
from app.services.ingest import ArtistNotFound, ingest_artist


def recommend(db: Session, prompt: str, count: int = 5) -> list[tuple[Artist, str]]:
    suggestions = gemini.suggest_artists(prompt, count=count)

    results: list[tuple[Artist, str]] = []
    for suggestion in suggestions:
        try:
            artist = ingest_artist(db, suggestion["name"], album_limit=0)
        except ArtistNotFound:
            continue
        results.append((artist, suggestion["reason"]))
    return results
