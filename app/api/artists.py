import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.artist import Artist
from app.schemas.artist import ArtistCreate, ArtistRead

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


@router.get("/{artist_id}", response_model=ArtistRead)
def get_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)) -> Artist:
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist
