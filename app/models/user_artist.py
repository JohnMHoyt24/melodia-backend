import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class UserArtist(Base):
    """An artist saved to one user's personal library.

    `artists` is a shared catalog (everything ever ingested); this table is what makes
    an artist part of *a particular user's* library. `user_id` is the Supabase auth uid
    - no FK, since auth.users isn't managed here (same as chat_threads.user_id).
    """

    __tablename__ = "user_artists"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    artist: Mapped["Artist"] = relationship()  # noqa: F821
