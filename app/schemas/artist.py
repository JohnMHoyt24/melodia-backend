import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.album import AlbumRead
from app.schemas.genre import GenreRead


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
