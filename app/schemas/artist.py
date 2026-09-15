import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArtistCreate(BaseModel):
    name: str
    musicbrainz_id: str | None = None


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    musicbrainz_id: str | None
    created_at: datetime
