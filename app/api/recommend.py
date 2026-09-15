from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.recommend import RecommendedArtist, RecommendRequest
from app.services.recommend import recommend as recommend_service

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_model=list[RecommendedArtist])
def recommend(payload: RecommendRequest, db: Session = Depends(get_db)) -> list[RecommendedArtist]:
    """Free-text artist discovery, e.g. "like Dinosaur Jr but with more jangly guitars".

    Synchronous and can take a while - one Gemini call plus a MusicBrainz+Last.fm
    ingest per suggested artist (each subject to MusicBrainz's ~1 req/sec throttle).
    """
    results = recommend_service(db, payload.prompt, count=payload.count)
    return [
        RecommendedArtist(
            id=artist.id,
            name=artist.name,
            genres=[genre.name for genre in artist.genres],
            reason=reason,
        )
        for artist, reason in results
    ]
