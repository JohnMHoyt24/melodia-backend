import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artists.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    primary_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_release_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    artist: Mapped["Artist"] = relationship(back_populates="albums")  # noqa: F821
    tracks: Mapped[list["Track"]] = relationship(  # noqa: F821
        back_populates="album", cascade="all, delete-orphan"
    )
