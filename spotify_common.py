"""Shared helpers for the Spotify CLI scripts.

The legacy scripts use hyphenated filenames and can't be imported as modules,
so any logic shared between scripts lives here instead.
"""
from dotenv import load_dotenv
import os
import sys

import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

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
