import uuid
from datetime import datetime

from pydantic import BaseModel


class LibraryArtist(BaseModel):
    id: uuid.UUID
    name: str
    genres: list[str]
    characteristics: dict[str, float] | None
    added_at: datetime
