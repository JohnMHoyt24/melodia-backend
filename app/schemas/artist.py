import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.schemas.album import AlbumRead
from app.schemas.genre import GenreRead
from app.services.covers import cover_art_url, earliest_album_mbid


class ArtistCreate(BaseModel):
    name: str
    musicbrainz_id: str | None = None


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    musicbrainz_id: str | None
    created_at: datetime


class ArtistIngestRequest(BaseModel):
    name: str
    album_limit: int = 10


class ArtistDetail(ArtistRead):
    genres: list[GenreRead] = []
    albums: list[AlbumRead] = []
    characteristics: dict[str, float] | None = None

    @computed_field
    @property
    def cover_url(self) -> str | None:
        """Larger than list thumbnails: the artist page shows it as its hero image."""
        mbid = earliest_album_mbid((a.musicbrainz_id, a.first_release_date) for a in self.albums)
        return cover_art_url(mbid, size=500)


class SimilarArtist(BaseModel):
    id: uuid.UUID
    name: str
    similarity: float
    cover_url: str | None = None


class AskRequest(BaseModel):
    question: str
    limit: int = 5


class AskResponse(BaseModel):
    answer: str
    sources: list[SimilarArtist]


class AnalysisStatus(BaseModel):
    # "done" | "queued" | "running" | "failed" | "idle" (not analyzed, not queued)
    status: str
    error: str | None = None
