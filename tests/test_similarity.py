import pytest

from app.models import Artist
from app.services.similarity import ArtistNotAnalyzed, find_similar_artists


def test_find_similar_artists_requires_embedding(db_session):
    artist = Artist(name="Boards of Canada")
    db_session.add(artist)
    db_session.commit()

    with pytest.raises(ArtistNotAnalyzed):
        find_similar_artists(db_session, artist)
