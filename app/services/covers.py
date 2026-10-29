"""Cover art for albums and artists, via the Cover Art Archive (https://coverartarchive.org).

The archive is keyed by MusicBrainz release-group id, which albums already store, so no
extra API calls are needed: we only build URLs. An artist's cover is its earliest album
that has art. The archive 404s for release groups without art; the frontend falls back to
generated art when an image fails to load.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.album import Album

_BASE_URL = "https://coverartarchive.org/release-group"


def cover_art_url(release_group_mbid: str | None, size: int = 250) -> str | None:
    """`size` is one of the archive's thumbnail sizes: 250, 500 or 1200."""
    if not release_group_mbid:
        return None
    return f"{_BASE_URL}/{release_group_mbid}/front-{size}"


def _release_sort_key(first_release_date: str | None) -> str:
    # Undated albums sort last ("~" is after every digit).
    return first_release_date or "~"


def earliest_album_mbid(albums: Iterable[tuple[str | None, str | None]]) -> str | None:
    """From (musicbrainz_id, first_release_date) pairs, the earliest album's id."""
    dated = [(_release_sort_key(released), mbid) for mbid, released in albums if mbid]
    return min(dated)[1] if dated else None


def artist_cover_urls(db: Session, artist_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Cover URL per artist (see earliest_album_mbid), in one query.

    Artists with no album that has a MusicBrainz id are absent from the result.
    """
    ids = set(artist_ids)
    if not ids:
        return {}
    rows = (
        db.query(Album.artist_id, Album.musicbrainz_id, Album.first_release_date)
        .filter(Album.artist_id.in_(ids), Album.musicbrainz_id.is_not(None))
        .all()
    )
    albums_by_artist: dict[uuid.UUID, list[tuple[str, str | None]]] = {}
    for artist_id, mbid, released in rows:
        albums_by_artist.setdefault(artist_id, []).append((mbid, released))
    return {
        artist_id: cover_art_url(earliest_album_mbid(albums))
        for artist_id, albums in albums_by_artist.items()
    }
