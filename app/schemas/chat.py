import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageCreate(BaseModel):
    message: str


class RecommendedArtistOut(BaseModel):
    id: uuid.UUID
    name: str
    genres: list[str]
    reason: str


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    recommended_artists: list[RecommendedArtistOut] | None
    created_at: datetime


class ChatThreadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatThreadDetail(ChatThreadSummary):
    messages: list[ChatMessageRead] = []
