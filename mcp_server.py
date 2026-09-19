"""MCP server exposing Melodia's artist library to MCP clients (Claude Code, etc.).

Run over stdio from the melodia-backend directory (so `.env` and `app` resolve):

    .venv/Scripts/python.exe mcp_server.py

Every tool is a thin wrapper over the same service functions the FastAPI routes use
(app/services/), opening its own DB session per call. stdout is the MCP transport, so
never print() in here.
"""

from typing import Any

from mcp.server.mcpserver import MCPServer

from app.core.db import SessionLocal
from app.models.artist import Artist
from app.services import rag
from app.services.analyze import analyze_artist as run_analysis
from app.services.ingest import ArtistNotFound, ingest_artist as run_ingest
from app.services.similarity import ArtistNotAnalyzed, find_similar_artists as run_similar

mcp = MCPServer(
    "melodia",
    instructions=(
        "Melodia's music library. Ingest an artist first, analyze it (characteristic "
        "scores + embedding), then use find_similar_artists or ask_music_question - both "
        "only see analyzed artists."
    ),
)


def _artist_by_name(db, name: str) -> Artist:
    artist = db.query(Artist).filter(Artist.name.ilike(name)).first()
    if artist is None:
        raise ValueError(f"No artist named {name!r} in the library - ingest_artist it first")
    return artist


def _summary(artist: Artist) -> dict[str, Any]:
    return {
        "id": str(artist.id),
        "name": artist.name,
        "genres": [genre.name for genre in artist.genres],
        "characteristics": artist.characteristics,
        "analyzed": artist.embedding is not None,
    }


@mcp.tool()
def list_artists() -> list[dict[str, Any]]:
    """List every artist in the library with genres, characteristic scores and whether
    it has been analyzed."""
    with SessionLocal() as db:
        return [_summary(a) for a in db.query(Artist).order_by(Artist.name).all()]


@mcp.tool()
def get_artist(name: str) -> dict[str, Any]:
    """Get one library artist (case-insensitive exact name) with genres and albums."""
    with SessionLocal() as db:
        artist = _artist_by_name(db, name)
        return {
            **_summary(artist),
            "albums": [{"title": album.title} for album in artist.albums],
        }


@mcp.tool()
def ingest_artist(name: str, album_limit: int = 10) -> dict[str, Any]:
    """Fetch an artist from MusicBrainz (+ Last.fm tags) and upsert into the library.
    Slow (several seconds) because of MusicBrainz rate limits."""
    with SessionLocal() as db:
        try:
            return _summary(run_ingest(db, name, album_limit=album_limit))
        except ArtistNotFound as exc:
            raise ValueError(str(exc)) from exc


@mcp.tool()
def analyze_artist(name: str) -> dict[str, Any]:
    """Classify an ingested artist's characteristics and generate its embedding with
    Gemini. Required before the artist shows up in similarity or question answering."""
    with SessionLocal() as db:
        return _summary(run_analysis(db, _artist_by_name(db, name)))


@mcp.tool()
def find_similar_artists(name: str, limit: int = 10) -> list[dict[str, Any]]:
    """Find the library artists most similar to an analyzed artist, by embedding cosine
    similarity (1.0 = identical)."""
    with SessionLocal() as db:
        artist = _artist_by_name(db, name)
        try:
            results = run_similar(db, artist, limit=limit)
        except ArtistNotAnalyzed as exc:
            raise ValueError(str(exc)) from exc
        return [{"name": other.name, "similarity": round(sim, 4)} for other, sim in results]


@mcp.tool()
def ask_music_question(question: str, limit: int = 5) -> dict[str, Any]:
    """Answer a free-text music question (RAG) grounded in the analyzed artists most
    relevant to it, e.g. 'something mellow and melodic for studying'."""
    with SessionLocal() as db:
        result = rag.ask(db, question, limit=limit)
        return {
            "answer": result.answer,
            "sources": [
                {"name": a.name, "relevance": round(sim, 4)} for a, sim in result.sources
            ],
        }


@mcp.resource("melodia://artists/{name}")
def artist_profile(name: str) -> dict[str, Any]:
    """Profile (genres + characteristic scores) for one artist."""
    with SessionLocal() as db:
        return _summary(_artist_by_name(db, name))


if __name__ == "__main__":
    mcp.run()
