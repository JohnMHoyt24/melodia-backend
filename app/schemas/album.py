import uuid

from pydantic import BaseModel, ConfigDict, computed_field

from app.schemas.track import TrackRead
from app.services.covers import cover_art_url


class AlbumRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    musicbrainz_id: str | None = None
    primary_type: str | None
    first_release_date: str | None
    tracks: list[TrackRead] = []

    @computed_field
    @property
    def cover_url(self) -> str | None:
        return cover_art_url(self.musicbrainz_id)
