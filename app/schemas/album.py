import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.track import TrackRead


class AlbumRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    primary_type: str | None
    first_release_date: str | None
    tracks: list[TrackRead] = []
