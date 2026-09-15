from sqlalchemy import Column, ForeignKey, Integer, Table

from app.core.db import Base

artist_genres = Table(
    "artist_genres",
    Base.metadata,
    Column("artist_id", ForeignKey("artists.id"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id"), primary_key=True),
    Column("weight", Integer, nullable=False, default=0),
)
