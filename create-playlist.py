"""Build a Spotify playlist from a public stats.fm user's top tracks.

Reads a public stats.fm profile (no auth required) and creates a playlist in
*your* Spotify account from that user's top tracks. Creating a playlist writes
to your account, so this uses the OAuth Authorization Code flow (unlike the
other scripts in this repo, which only read the public catalog via the
client-credentials flow).

Example:
    python create-playlist.py https://stats.fm/chamerence/tracks
    python create-playlist.py chamerence --limit 200 --range lifetime --public
"""
from dotenv import load_dotenv
import argparse
import os
import re
import sys
from typing import Dict, List, Optional

import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

STATSFM_API = "https://api.stats.fm/api/v1"
# stats.fm exposes "weeks" | "months" | "lifetime"; "lifetime" == all time.
VALID_RANGES = ("weeks", "months", "lifetime")
# stats.fm caps a single page; 100 keeps us well under that and is also the
# Spotify add-tracks batch size, so the two halves line up neatly.
PAGE_SIZE = 100
# Spotify accepts at most 100 track URIs per add-to-playlist request.
SPOTIFY_BATCH = 100

# OAuth scopes needed to create a playlist and add tracks to it.
SCOPE = "playlist-modify-private playlist-modify-public"

# stats.fm's API rejects the default python-requests User-Agent with 403, so we
# present a browser-like one and reuse a session across calls.
session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
)


def log(message: str) -> None:
    """Progress goes to stderr so stdout stays clean (e.g. the playlist URL)."""
    print(message, file=sys.stderr)


def parse_target(raw: str) -> str:
    """Extract the stats.fm username/slug from a URL or bare handle.

    Accepts 'chamerence', 'https://stats.fm/chamerence',
    'https://stats.fm/chamerence/tracks', or an '@handle'.
    """
    raw = raw.strip()
    match = re.search(r"stats\.fm/(?:user/)?([^/?#]+)", raw)
    if match:
        return match.group(1).lstrip("@")
    return raw.lstrip("@")


def fetch_user(target: str) -> Dict:
    """Resolve the stats.fm profile and verify top tracks are public."""
    resp = session.get(f"{STATSFM_API}/users/{target}", timeout=30)
    if resp.status_code == 404:
        raise SystemExit(f"stats.fm user '{target}' not found.")
    resp.raise_for_status()
    item = resp.json().get("item")
    if not item:
        raise SystemExit(f"Unexpected stats.fm response for '{target}'.")

    privacy = item.get("privacySettings", {})
    if privacy.get("topTracks") is False:
        raise SystemExit(
            f"'{target}' has set their top tracks to private; nothing to read."
        )
    return item


def fetch_top_track_ids(user_id: str, target_range: str, want: int) -> List[str]:
    """Page through top tracks, collecting unique Spotify track IDs.

    Tracks in the stats.fm catalog may lack a Spotify mapping
    (track.externalIds.spotify can be empty), so we over-fetch until we either
    reach `want` IDs or run out of items.
    """
    ids: List[str] = []
    seen_spotify = set()
    seen_tracks = set()  # stats.fm internal track ids, to detect repeated pages
    offset = 0
    skipped_no_spotify = 0
    # Backstop: some profiles (e.g. accounts without imported history) ignore
    # `offset` and return the same page forever. Cap the number of requests so
    # we can never loop indefinitely.
    max_pages = max(1, (want // PAGE_SIZE) + 5)

    for _ in range(max_pages):
        if len(ids) >= want:
            break
        resp = session.get(
            f"{STATSFM_API}/users/{user_id}/top/tracks",
            params={"range": target_range, "limit": PAGE_SIZE, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            break  # no more data available

        page_new_tracks = 0  # genuinely new entries this page (Spotify or not)
        for entry in items:
            track = entry.get("track", {})
            track_key = track.get("id")
            if track_key is not None:
                if track_key in seen_tracks:
                    continue  # already processed this exact track
                seen_tracks.add(track_key)
            page_new_tracks += 1

            spotify_ids = track.get("externalIds", {}).get("spotify", [])
            if not spotify_ids:
                skipped_no_spotify += 1
                continue
            track_id = spotify_ids[0]
            if track_id in seen_spotify:
                continue
            seen_spotify.add(track_id)
            ids.append(track_id)
            if len(ids) >= want:
                break

        # No new tracks at all means the API is repeating pages (offset ignored)
        # or we've exhausted the profile's catalog -> stop.
        if page_new_tracks == 0:
            break

        offset += PAGE_SIZE
        log(f"  ...collected {len(ids)}/{want} tracks (offset {offset})")

    if skipped_no_spotify:
        log(f"  (skipped {skipped_no_spotify} track(s) with no Spotify match)")
    return ids[:want]


def prompt_playlist_name(default: str) -> str:
    """Ask for the playlist name interactively; Enter accepts the default.

    Falls back to the default if there's no interactive terminal (e.g. piped
    input) or the user cancels with Ctrl-D/Ctrl-C.
    """
    if not sys.stdin.isatty():
        log(f"No interactive terminal; using default name '{default}'.")
        return default
    try:
        entered = input(f"Name this playlist [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return default
    return entered or default


def build_spotify_client() -> spotipy.Spotify:
    """Authenticate against Spotify with the user-scoped OAuth flow."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_SECRET")
    # Must exactly match a Redirect URI registered in your Spotify app
    # dashboard. Spotify now requires the loopback IP literal (127.0.0.1)
    # rather than 'localhost' for new apps.
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    if not client_id or not client_secret:
        raise SystemExit(
            "Set SPOTIFY_CLIENT_ID and SPOTIFY_SECRET in your .env file."
        )

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
    )
    return spotipy.Spotify(auth_manager=auth)


def create_playlist_with_tracks(
    spotify: spotipy.Spotify,
    track_ids: List[str],
    name: str,
    description: str,
    public: bool,
) -> Dict:
    """Create a playlist in the current user's account and add the tracks."""
    me = spotify.current_user()
    user_id = me["id"]
    log(f"Authenticated as Spotify user '{me.get('display_name') or user_id}'.")

    playlist = spotify.user_playlist_create(
        user=user_id, name=name, public=public, description=description
    )
    playlist_id = playlist["id"]

    uris = [f"spotify:track:{tid}" for tid in track_ids]
    for start in range(0, len(uris), SPOTIFY_BATCH):
        batch = uris[start:start + SPOTIFY_BATCH]
        spotify.playlist_add_items(playlist_id, batch)
        log(f"  added {min(start + len(batch), len(uris))}/{len(uris)} tracks")

    return playlist


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a Spotify playlist from a public stats.fm profile."
    )
    parser.add_argument(
        "profile",
        help="stats.fm profile URL or username (e.g. https://stats.fm/chamerence/tracks)",
    )
    parser.add_argument(
        "--limit", type=int, default=200,
        help="number of top tracks to add (default: 200)",
    )
    parser.add_argument(
        "--range", dest="range", choices=VALID_RANGES, default="lifetime",
        help="time range for top tracks (default: lifetime / all time)",
    )
    parser.add_argument(
        "--name", default=None,
        help="playlist name (default: \"<user>'s top tracks (<range>)\")",
    )
    parser.add_argument(
        "--public", action="store_true",
        help="make the playlist public (default: private)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="fetch and report tracks but do not touch Spotify",
    )
    args = parser.parse_args()

    target = parse_target(args.profile)
    log(f"Resolving stats.fm user '{target}'...")
    user = fetch_user(target)
    user_id = user["id"]
    display = user.get("displayName") or target

    log(f"Fetching up to {args.limit} top tracks ({args.range})...")
    track_ids = fetch_top_track_ids(user_id, args.range, args.limit)
    if not track_ids:
        raise SystemExit("No Spotify-matched tracks found; nothing to add.")
    if len(track_ids) < args.limit:
        log(
            f"Only {len(track_ids)} tracks available for this profile "
            f"(requested {args.limit}); continuing with what was found."
        )
    else:
        log(f"Found {len(track_ids)} tracks with a Spotify match.")

    default_name = f"{display}'s top tracks ({args.range})"

    if args.dry_run:
        log("Dry run - not creating a playlist. Track IDs:")
        for tid in track_ids:
            print(tid)
        return

    # Prompt for the playlist name now that we know how many tracks we got,
    # unless --name was supplied. Pressing Enter accepts the default.
    name = args.name or prompt_playlist_name(default_name)
    description = (
        f"Top {len(track_ids)} tracks ({args.range}) from stats.fm/{target}, "
        "built with create-playlist.py."
    )

    spotify = build_spotify_client()
    playlist = create_playlist_with_tracks(
        spotify, track_ids, name, description, args.public
    )

    url = playlist.get("external_urls", {}).get("spotify", playlist["id"])
    log(f"Done. Created '{name}' with {len(track_ids)} tracks.")
    print(url)


if __name__ == "__main__":
    main()
