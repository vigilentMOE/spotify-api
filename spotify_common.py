"""Shared helpers for the Spotify CLI scripts.

The legacy scripts use hyphenated filenames and can't be imported as modules,
so any logic shared between scripts lives here instead.
"""
from dotenv import load_dotenv
import os
import sys
from typing import Callable, Dict, Iterator, List, Optional, Sequence

import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

ARTIST_BATCH = 50  # Spotify cap for sp.artists()

# Must exactly match a Redirect URI registered in the Spotify app dashboard.
# Spotify requires the loopback IP literal (127.0.0.1), not 'localhost'.
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"


def log(message: str) -> None:
    """Progress goes to stderr so stdout stays clean for pipeable output."""
    print(message, file=sys.stderr)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Set {name} in your .env file.")
    return value


def build_user_client(scope: str) -> spotipy.Spotify:
    """Authenticate with the user-scoped OAuth Authorization Code flow.

    First run opens a browser to authorize; the token is cached in `.cache`.
    Adding new scopes forces a one-time re-authorization.
    """
    auth = SpotifyOAuth(
        client_id=require_env("SPOTIFY_CLIENT_ID"),
        client_secret=require_env("SPOTIFY_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        scope=scope,
    )
    return spotipy.Spotify(auth_manager=auth)


def chunked(seq: Sequence, size: int) -> Iterator[Sequence]:
    for start in range(0, len(seq), size):
        yield seq[start:start + size]


def fetch_artist_genres(
    sp,
    artist_ids: Sequence[str],
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, List[str]]:
    """Batched artist-ID -> genre-list map (sp.artists caps at 50 IDs).

    Large libraries need hundreds of batches, so `on_progress(done, total)`
    is called after each one to let the caller show that work is happening.
    """
    genres: Dict[str, List[str]] = {}
    unique = sorted(set(artist_ids))
    for done, batch in enumerate(chunked(unique, ARTIST_BATCH), 1):
        resp = sp.artists(list(batch))
        for artist in resp.get("artists", []):
            if artist:  # Spotify returns null for invalid IDs
                genres[artist["id"]] = artist.get("genres", [])
        if on_progress:
            on_progress(min(done * ARTIST_BATCH, len(unique)), len(unique))
    return genres
