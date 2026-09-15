from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.artist import Artist
from app.schemas.search import ArtistSearchResult

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[ArtistSearchResult])
def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ArtistSearchResult]:
    artists = (
        db.query(Artist)
        .filter(Artist.name.ilike(f"%{q}%"))
        .order_by(Artist.name)
        .limit(limit)
        .all()
    )
    return [
        ArtistSearchResult(id=artist.id, name=artist.name, genres=[g.name for g in artist.genres])
        for artist in artists
    ]
