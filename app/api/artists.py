import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.artist import Artist
from app.schemas.artist import (
    AnalysisStatus,
    ArtistCreate,
    ArtistDetail,
    ArtistIngestRequest,
    ArtistRead,
    AskRequest,
    AskResponse,
    SimilarArtist,
)
from app.services import analysis_queue, rag
from app.services.analyze import analyze_artist
from app.services.gemini import GeminiNotConfigured
from app.services.ingest import ArtistNotFound, ingest_album_shells, ingest_artist
from app.services.similarity import ArtistNotAnalyzed, find_similar_artists

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("", response_model=list[ArtistRead])
def list_artists(db: Session = Depends(get_db)) -> list[Artist]:
    return list(db.query(Artist).order_by(Artist.name).all())


@router.post("", response_model=ArtistRead, status_code=201)
def create_artist(payload: ArtistCreate, db: Session = Depends(get_db)) -> Artist:
    artist = Artist(**payload.model_dump())
    db.add(artist)
    db.commit()
    db.refresh(artist)
    return artist


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    """RAG: answer a free-text question grounded in the analyzed artists most relevant
    to it - see app/services/rag.py."""
    try:
        result = rag.ask(db, payload.question, limit=payload.limit)
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AskResponse(
        answer=result.answer,
        sources=[
            SimilarArtist(id=a.id, name=a.name, similarity=similarity)
            for a, similarity in result.sources
        ],
    )


@router.post("/ingest", response_model=ArtistDetail)
def ingest(payload: ArtistIngestRequest, db: Session = Depends(get_db)) -> Artist:
    """Fetch an artist from MusicBrainz (+ Last.fm tags), upsert into the DB.

    Synchronous and can take several seconds (MusicBrainz rate limit + one call per
    album for tracks) - see app/services/ingest.py.
    """
    try:
        artist = ingest_artist(db, payload.name, album_limit=payload.album_limit)
    except ArtistNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    analysis_queue.maybe_enqueue(artist)
    return artist


@router.get("/{artist_id}", response_model=ArtistDetail)
def get_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)) -> Artist:
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist


@router.post("/{artist_id}/albums", response_model=ArtistDetail)
def load_albums(
    artist_id: uuid.UUID, limit: int = 10, db: Session = Depends(get_db)
) -> Artist:
    """Fetch this artist's album list (titles/years only, no tracklists yet) - fast,
    a single MusicBrainz call regardless of album count. Fetch each album's tracklist
    separately via POST /albums/{album_id}/tracks, on demand, rather than blocking on
    all of them here - see app/services/ingest.py for why.
    """
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    try:
        ingest_album_shells(db, artist, limit=limit)
    except ArtistNotFound as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(artist)
    return artist


@router.post("/{artist_id}/analyze", response_model=ArtistDetail)
def analyze(artist_id: uuid.UUID, db: Session = Depends(get_db)) -> Artist:
    """Classify characteristics + generate an embedding for an already-ingested artist."""
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    try:
        return analyze_artist(db, artist)
    except GeminiNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{artist_id}/similar", response_model=list[SimilarArtist])
def similar(
    artist_id: uuid.UUID, limit: int = 10, db: Session = Depends(get_db)
) -> list[SimilarArtist]:
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    try:
        results = find_similar_artists(db, artist, limit=limit)
    except ArtistNotAnalyzed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [
        SimilarArtist(id=other.id, name=other.name, similarity=similarity)
        for other, similarity in results
    ]


def _analysis_status(artist: Artist) -> AnalysisStatus:
    if artist.embedding is not None:
        return AnalysisStatus(status="done")
    status, error = analysis_queue.in_flight_status(artist.id)
    return AnalysisStatus(status=status or "idle", error=error)


@router.get("/{artist_id}/analysis", response_model=AnalysisStatus)
def analysis_status(artist_id: uuid.UUID, db: Session = Depends(get_db)) -> AnalysisStatus:
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    return _analysis_status(artist)


@router.post("/{artist_id}/analysis", response_model=AnalysisStatus, status_code=202)
def request_analysis(artist_id: uuid.UUID, db: Session = Depends(get_db)) -> AnalysisStatus:
    """Queue background analysis (retrying a failed one); poll GET for the outcome.

    Unlike POST /{id}/analyze this returns immediately - see app/services/analysis_queue.py.
    """
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    if artist.embedding is None:
        analysis_queue.enqueue(artist.id)
    return _analysis_status(artist)
