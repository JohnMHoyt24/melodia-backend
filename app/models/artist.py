import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.associations import artist_genres


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    albums: Mapped[list["Album"]] = relationship(  # noqa: F821
        back_populates="artist", cascade="all, delete-orphan"
    )
    genres: Mapped[list["Genre"]] = relationship(  # noqa: F821
        secondary=artist_genres, back_populates="artists"
    )
