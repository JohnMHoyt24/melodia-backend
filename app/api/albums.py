import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Album
from app.schemas.album import AlbumRead
from app.services.ingest import ingest_album_tracks

router = APIRouter(prefix="/albums", tags=["albums"])


@router.post("/{album_id}/tracks", response_model=AlbumRead)
def load_tracks(album_id: uuid.UUID, db: Session = Depends(get_db)) -> Album:
    """Fetch and store one album's tracklist from MusicBrainz. Idempotent - a repeat
    call for an album that already has tracks returns them without hitting MusicBrainz
    again. Meant to be called once per album shown, after POST /artists/{id}/albums,
    rather than fetching every album's tracklist upfront.
    """
    album = db.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return ingest_album_tracks(db, album)
