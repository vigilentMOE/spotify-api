"""Snapshot the current user's playlists with aggregated genre counts.

Read-only against Spotify. Writes a local snapshot.json cache (gitignored)
that propose_folders.py consumes, so the API-heavy aggregation runs once.
"""
from typing import Dict, Iterator, List, Sequence

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
