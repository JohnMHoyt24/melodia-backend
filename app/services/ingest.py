"""Orchestrates artist ingestion: MusicBrainz for canonical metadata (artist, albums,
tracks), Last.fm for user-generated tags (stored as our own `genres`).

Runs synchronously on the request path for now - MusicBrainz's ~1 req/sec rate limit
means ingesting an artist with several albums can take several seconds. Milestone 6's
background worker is where this moves off the request path.
"""

from sqlalchemy.orm import Session

from app.models import Album, Artist, Genre, Track
from app.services import lastfm, musicbrainz
from app.services.lastfm import LastfmNotConfigured


class ArtistNotFound(Exception):
    pass


def _get_or_create_artist(db: Session, mb_artist: dict) -> Artist:
    artist = (
        db.query(Artist).filter(Artist.musicbrainz_id == mb_artist["id"]).one_or_none()
    )
    if artist is None:
        artist = Artist(name=mb_artist["name"], musicbrainz_id=mb_artist["id"])
        db.add(artist)
        db.flush()
    return artist


def _sync_genres(db: Session, artist: Artist, tags: list[dict]) -> None:
    artist.genres.clear()
    for tag in tags:
        genre = db.query(Genre).filter(Genre.name == tag["name"]).one_or_none()
        if genre is None:
            genre = Genre(name=tag["name"])
            db.add(genre)
            db.flush()
        artist.genres.append(genre)


def _sync_album(db: Session, artist: Artist, release_group: dict) -> Album:
    album = (
        db.query(Album)
        .filter(Album.musicbrainz_id == release_group["id"])
        .one_or_none()
    )
    if album is None:
        album = Album(
            artist_id=artist.id,
            title=release_group["title"],
            musicbrainz_id=release_group["id"],
        )
        db.add(album)

    album.primary_type = release_group.get("primary-type")
    album.first_release_date = release_group.get("first-release-date") or None
    db.flush()
    return album


def _sync_tracks(db: Session, album: Album, tracks: list[dict]) -> None:
    for position, track in enumerate(tracks, start=1):
        recording = track.get("recording", {})
        mbid = recording.get("id")
        existing = None
        if mbid:
            existing = (
                db.query(Track).filter(Track.musicbrainz_id == mbid).one_or_none()
            )
        if existing is None:
            existing = Track(album_id=album.id, musicbrainz_id=mbid)
            db.add(existing)

        existing.title = track.get("title", recording.get("title", "Unknown"))
        existing.track_number = position
        existing.length_ms = track.get("length") or recording.get("length")


def ingest_artist(db: Session, name: str, album_limit: int = 10) -> Artist:
    mb_artist = musicbrainz.search_artist(name)
    if mb_artist is None:
        raise ArtistNotFound(f"No MusicBrainz artist found for {name!r}")

    artist = _get_or_create_artist(db, mb_artist)

    try:
        tags = lastfm.get_top_tags(mb_artist["name"])
    except LastfmNotConfigured:
        tags = []
    _sync_genres(db, artist, tags)

    release_groups = musicbrainz.browse_release_groups(mb_artist["id"], limit=album_limit)
    for release_group in release_groups:
        album = _sync_album(db, artist, release_group)
        tracks = musicbrainz.get_release_group_tracks(release_group["id"])
        _sync_tracks(db, album, tracks)

    db.commit()
    db.refresh(artist)
    return artist
