import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.artist import Artist
from app.schemas.artist import (
    ArtistCreate,
    ArtistDetail,
    ArtistIngestRequest,
    ArtistRead,
    SimilarArtist,
)
from app.services.analyze import analyze_artist
from app.services.gemini import GeminiNotConfigured
from app.services.ingest import ArtistNotFound, ingest_artist
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


@router.post("/ingest", response_model=ArtistDetail)
def ingest(payload: ArtistIngestRequest, db: Session = Depends(get_db)) -> Artist:
    """Fetch an artist from MusicBrainz (+ Last.fm tags), upsert into the DB.

    Synchronous and can take several seconds (MusicBrainz rate limit + one call per
    album for tracks) - see app/services/ingest.py.
    """
    try:
        return ingest_artist(db, payload.name, album_limit=payload.album_limit)
    except ArtistNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{artist_id}", response_model=ArtistDetail)
def get_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)) -> Artist:
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
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
