import uuid

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    prompt: str
    count: int = Field(default=5, ge=1, le=10)


class RecommendedArtist(BaseModel):
    id: uuid.UUID
    name: str
    genres: list[str]
    reason: str
