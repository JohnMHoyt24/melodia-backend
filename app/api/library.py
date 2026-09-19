"""A signed-in user's personal library: the artists they've chosen to keep.

Everything here is scoped to the caller's Supabase user id. Similar-artist lookups and
chat grounding draw only from this library (see app/services/similarity.py).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.db import get_db
from app.models.artist import Artist
from app.models.user_artist import UserArtist
from app.schemas.artist import SimilarArtist
from app.schemas.library import LibraryArtist
from app.services import analysis_queue
from app.services.similarity import ArtistNotAnalyzed, find_similar_artists

router = APIRouter(prefix="/library", tags=["library"])


def _to_schema(entry: UserArtist) -> LibraryArtist:
    artist = entry.artist
    return LibraryArtist(
        id=artist.id,
        name=artist.name,
        genres=[genre.name for genre in artist.genres],
        characteristics=artist.characteristics,
        added_at=entry.added_at,
    )


@router.get("", response_model=list[LibraryArtist])
def list_library(
    db: Session = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user_id)
) -> list[LibraryArtist]:
    entries = (
        db.query(UserArtist)
        .filter(UserArtist.user_id == user_id)
        .order_by(UserArtist.added_at.desc())
        .all()
    )
    return [_to_schema(entry) for entry in entries]


@router.put("/{artist_id}", response_model=LibraryArtist)
def add_to_library(
    artist_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> LibraryArtist:
    """Add an artist to the caller's library. Idempotent."""
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")

    entry = db.get(UserArtist, (user_id, artist_id))
    if entry is None:
        entry = UserArtist(user_id=user_id, artist_id=artist_id)
        db.add(entry)
        db.commit()
        db.refresh(entry)
    # Only analyzed artists can show up in similarity/grounding, so make sure it gets analyzed.
    analysis_queue.maybe_enqueue(artist)
    return _to_schema(entry)


@router.delete("/{artist_id}", status_code=204)
def remove_from_library(
    artist_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> None:
    entry = db.get(UserArtist, (user_id, artist_id))
    if entry is not None:
        db.delete(entry)
        db.commit()


@router.get("/{artist_id}/similar", response_model=list[SimilarArtist])
def similar_in_library(
    artist_id: uuid.UUID,
    limit: int = 6,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[SimilarArtist]:
    """Artists in the caller's library most similar to `artist_id` (itself excluded)."""
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    try:
        results = find_similar_artists(db, artist, limit=limit, user_id=user_id)
    except ArtistNotAnalyzed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [
        SimilarArtist(id=other.id, name=other.name, similarity=similarity)
        for other, similarity in results
    ]
