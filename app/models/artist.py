import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EMBEDDING_DIM
from app.core.db import Base
from app.models.associations import artist_genres

# pgvector's Vector type is Postgres-only; SQLite (used in tests) falls back to
# storing the same list[float] as JSON so the ORM layer works identically either way.
EmbeddingType = Vector(EMBEDDING_DIM).with_variant(JSON(), "sqlite")


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), index=True)
    musicbrainz_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    characteristics: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)

    albums: Mapped[list["Album"]] = relationship(  # noqa: F821
        back_populates="artist", cascade="all, delete-orphan"
    )
    genres: Mapped[list["Genre"]] = relationship(  # noqa: F821
        secondary=artist_genres, back_populates="artists"
    )
