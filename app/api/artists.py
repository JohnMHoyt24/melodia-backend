import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.artist import Artist
from app.schemas.artist import ArtistCreate, ArtistDetail, ArtistIngestRequest, ArtistRead
from app.services.ingest import ArtistNotFound, ingest_artist

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
