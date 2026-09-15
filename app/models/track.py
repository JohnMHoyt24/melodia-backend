import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    album_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("albums.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    length_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    album: Mapped["Album"] = relationship(back_populates="tracks")
