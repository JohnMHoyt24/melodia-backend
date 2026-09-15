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
    """`album_limit=0` skips album/track ingestion entirely (only the artist search +
    Last.fm tags), cutting MusicBrainz calls for this artist from up to 1 + 2*N (N
    albums) down to 1. Used by the recommend flow (app/services/recommend.py), where
    5 suggested artists at the full album_limit each meant 30-90s of sequential,
    throttled MusicBrainz calls (~1 req/sec) before anything could be shown - see
    PLAN.md. Full ingestion still happens on demand via POST /artists/ingest.

    Also skips all external calls entirely if an artist with this name is already in
    our DB and already satisfies what's being asked for (has albums, or none were
    requested) - this is what makes repeat recommendations of a popular artist across
    different prompts fast: the "organic infinite catalog" (see PLAN.md, Milestone 4)
    only pays the MusicBrainz/Last.fm cost once per artist, not once per mention.
    """
    cached = db.query(Artist).filter(Artist.name.ilike(name)).one_or_none()
    if cached is not None and (album_limit == 0 or len(cached.albums) > 0):
        return cached

    mb_artist = musicbrainz.search_artist(name)
    if mb_artist is None:
        raise ArtistNotFound(f"No MusicBrainz artist found for {name!r}")

    artist = _get_or_create_artist(db, mb_artist)

    try:
        tags = lastfm.get_top_tags(mb_artist["name"])
    except LastfmNotConfigured:
        tags = []
    _sync_genres(db, artist, tags)

    if album_limit > 0:
        release_groups = musicbrainz.browse_release_groups(mb_artist["id"], limit=album_limit)
        for release_group in release_groups:
            album = _sync_album(db, artist, release_group)
            tracks = musicbrainz.get_release_group_tracks(release_group["id"])
            _sync_tracks(db, album, tracks)

    db.commit()
    db.refresh(artist)
    return artist


def ingest_album_shells(db: Session, artist: Artist, limit: int = 10) -> list[Album]:
    """Fetch this artist's albums (title/year/type only, no tracklists) - a single
    MusicBrainz call no matter how many albums come back, since fetching each album's
    tracklist is the expensive part (one throttled call per album, the dominant cost
    in ingest_artist() above). Pair with ingest_album_tracks() per album, on demand,
    instead of blocking on every album's tracklist before showing anything - see
    PLAN.md for the "Load albums" latency this was written to fix.
    """
    if not artist.musicbrainz_id:
        raise ArtistNotFound(f"{artist.name!r} has no MusicBrainz link")

    release_groups = musicbrainz.browse_release_groups(artist.musicbrainz_id, limit=limit)
    albums = [_sync_album(db, artist, release_group) for release_group in release_groups]
    db.commit()
    for album in albums:
        db.refresh(album)
    return albums


def ingest_album_tracks(db: Session, album: Album) -> Album:
    """Fetch and store one album's tracklist. Idempotent/fast on repeat - does nothing
    if the album already has tracks."""
    if album.tracks:
        return album

    tracks = musicbrainz.get_release_group_tracks(album.musicbrainz_id)
    _sync_tracks(db, album, tracks)
    db.commit()
    db.refresh(album)
    return album
