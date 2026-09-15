import uuid

from pydantic import BaseModel


class ArtistSearchResult(BaseModel):
    id: uuid.UUID
    name: str
    genres: list[str]
