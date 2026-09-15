import uuid

from pydantic import BaseModel, ConfigDict


class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    track_number: int | None
    length_ms: int | None
