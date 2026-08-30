"""Snapshot the current user's playlists with aggregated genre counts.

Read-only against Spotify. Writes a local snapshot.json cache (gitignored)
that propose_folders.py consumes, so the API-heavy aggregation runs once.
"""
from typing import Dict, Iterator, List, Sequence

from spotipy.exceptions import SpotifyException

from spotify_common import log

# Reading the user's own playlists needs scopes beyond what
# create-playlist.py requests, so the first run re-authorizes.
SCOPE = "playlist-read-private playlist-read-collaborative"
PLAYLIST_PAGE = 50   # Spotify page cap for current_user_playlists
TRACK_PAGE = 100     # Spotify page cap for playlist_items
ARTIST_BATCH = 50    # Spotify cap for sp.artists()


def chunked(seq: Sequence, size: int) -> Iterator[Sequence]:
    for start in range(0, len(seq), size):
        yield seq[start:start + size]


def aggregate_genres(
    track_artist_ids: List[List[str]],
    artist_genres: Dict[str, List[str]],
) -> Dict[str, int]:
    """Count how many tracks exhibit each genre.

    A track contributes at most 1 per distinct genre, even when several of
    its artists share that genre. Artists missing from `artist_genres`
    (or with empty genre lists) contribute nothing.
    """
    counts: Dict[str, int] = {}
    for artist_ids in track_artist_ids:
        genres = set()
        for artist_id in artist_ids:
            genres.update(artist_genres.get(artist_id, []))
        for genre in genres:
            counts[genre] = counts.get(genre, 0) + 1
    return counts


def fetch_all_playlists(sp) -> List[Dict]:
    """All playlists in the user's library (owned and followed)."""
    playlists: List[Dict] = []
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=PLAYLIST_PAGE, offset=offset)
        items = [p for p in page.get("items", []) if p]
        playlists.extend(items)
        if len(items) < PLAYLIST_PAGE:
            break  # short page means last page
        offset += PLAYLIST_PAGE
    return playlists


def fetch_track_artist_ids(sp, playlist_id: str) -> List[List[str]]:
    """Per-track lists of artist IDs for one playlist.

    Local files and removed tracks have no artist IDs and are skipped.
    The `fields` filter keeps the payload small.

    Spotify's algorithmic "Made for you" mixes (Daily Mix, genre mixes, etc.)
    are not readable through the Web API and answer 404. Treat those as
    empty rather than aborting the whole snapshot.
    """
    tracks: List[List[str]] = []
    offset = 0
    fields = "items(track(artists(id)))"
    while True:
        try:
            page = sp.playlist_items(
                playlist_id, fields=fields, limit=TRACK_PAGE, offset=offset
            )
        except SpotifyException as exc:
            if exc.http_status in (403, 404):
                log(f"  ! playlist {playlist_id} is not readable via the API "
                    f"({exc.http_status}); skipping")
                return []
            raise
        items = page.get("items", [])
        for item in items:
            track = item.get("track") or {}
            ids = [a["id"] for a in track.get("artists", []) if a.get("id")]
            if ids:
                tracks.append(ids)
        if len(items) < TRACK_PAGE:
            break
        offset += TRACK_PAGE
    return tracks


def fetch_artist_genres(sp, artist_ids: Sequence[str]) -> Dict[str, List[str]]:
    """Batched artist-ID -> genre-list map (sp.artists caps at 50 IDs)."""
    genres: Dict[str, List[str]] = {}
    unique = sorted(set(artist_ids))
    for batch in chunked(unique, ARTIST_BATCH):
        resp = sp.artists(list(batch))
        for artist in resp.get("artists", []):
            if artist:  # Spotify returns null for invalid IDs
                genres[artist["id"]] = artist.get("genres", [])
    return genres
