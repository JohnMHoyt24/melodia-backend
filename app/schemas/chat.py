import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageCreate(BaseModel):
    message: str


# cover_url isn't stored with the message: albums (and so covers) can arrive after the
# message was written, so app/api/chat.py fills it in at read time.
class RecommendedArtistOut(BaseModel):
    id: uuid.UUID
    name: str
    genres: list[str]
    reason: str
    cover_url: str | None = None


class ChatSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    similarity: float
    cover_url: str | None = None


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    recommended_artists: list[RecommendedArtistOut] | None
    sources: list[ChatSourceOut] | None = None
    created_at: datetime


class ChatThreadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatThreadDetail(ChatThreadSummary):
    messages: list[ChatMessageRead] = []
