"""Build a snapshot from a hand-transcribed folder inventory.

Spotify's personalised "Made for you" playlists - the "<Genre> Mix" and
"<Song> Radio" entries that fill this library's folders - are invisible to
the Web API: they never appear in current_user_playlists and cannot be
found via search, so their tracks can't be read. Verified against the live
account: 149 playlists visible to the API, none of them these.

Genre therefore has to come from somewhere else:

  - "<Genre> Mix"  -> the name *is* the genre ("Shoegaze Mix"), so the
    name is classified directly.
  - "<Song> Radio" -> the name is the seed song title, so the seed track is
    looked up via search and its artists' genres are used.

Both paths emit the same shape playlist_snapshot.py produces, so
propose_folders.py consumes either without changes.
"""
import argparse
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from spotipy.exceptions import SpotifyException

from propose_folders import classify_genre
from spotify_common import build_user_client, log

SCOPE = "playlist-read-private"
RADIO_SUFFIX = " Radio"


def is_radio_playlist(name: str) -> bool:
    """True for '<Song> Radio' playlists, whose name is a song, not a genre."""
    return name.endswith(RADIO_SUFFIX)


def seed_query(name: str) -> str:
    """The seed song title behind a '<Song> Radio' playlist name."""
    if is_radio_playlist(name):
        return name[: -len(RADIO_SUFFIX)].strip()
    return name.strip()


def genre_counts_from_name(name: str) -> Dict[str, int]:
    """Genre counts for a '<Genre> Mix' playlist, taken from its own name.

    Weight 1: the name yields exactly one family, so coverage is 100% when
    it classifies and the playlist is Unclassified when it doesn't.
    """
    return {name: 1} if classify_genre(name) else {}


def resolve_radio_genres(sp, name: str) -> Dict[str, int]:
    """Genres of the seed track's artists for a '<Song> Radio' playlist."""
    query = seed_query(name)
    if not query:
        return {}
    try:
        results = sp.search(q=query, type="track", limit=1)
    except SpotifyException as exc:
        log(f"  ! search failed for {query!r} ({exc.http_status})")
        return {}

    items = (results.get("tracks") or {}).get("items") or []
    if not items:
        return {}

    artist_ids = [a["id"] for a in items[0].get("artists", []) if a.get("id")]
    if not artist_ids:
        return {}

    try:
        artists = sp.artists(artist_ids).get("artists", [])
    except SpotifyException as exc:
        log(f"  ! artist lookup failed for {query!r} ({exc.http_status})")
        return {}

    counts: Dict[str, int] = {}
    for artist in artists:
        for genre in (artist or {}).get("genres", []):
            counts[genre] = counts.get(genre, 0) + 1
    return counts


def build_entries(sp, inventory: Dict[str, Dict[str, List[str]]]) -> List[Dict]:
    """Snapshot entries for every playlist in the inventory.

    `sp` may be None, in which case only name-derived genres are produced
    and radio playlists come back Unclassified.
    """
    entries: List[Dict] = []
    for top_folder, subfolders in inventory.items():
        for subfolder, names in subfolders.items():
            for name in names:
                radio = is_radio_playlist(name)
                if radio and sp is not None:
                    counts = resolve_radio_genres(sp, name)
                    method = "seed-track"
                elif radio:
                    counts = {}
                    method = "seed-track (skipped)"
                else:
                    counts = genre_counts_from_name(name)
                    method = "name"
                entries.append(
                    {
                        "id": "",  # these playlists have no API-visible ID
                        "name": name,
                        "source_folder": f"{top_folder} / {subfolder}",
                        "total_tracks": 0,
                        "tracks_with_artists": 0,
                        "method": method,
                        "genre_counts": counts,
                    }
                )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a snapshot from a transcribed folder inventory."
    )
    parser.add_argument(
        "--inventory", default="folder_inventory.json",
        help="JSON: {top folder: {subfolder: [playlist names]}}",
    )
    parser.add_argument(
        "--output", default="snapshot.json",
        help="where to write the snapshot (default: snapshot.json)",
    )
    parser.add_argument(
        "--no-api", action="store_true",
        help="skip seed-track lookups; classify by name only (no Spotify calls)",
    )
    args = parser.parse_args()

    with open(args.inventory) as f:
        inventory = json.load(f)

    sp = None if args.no_api else build_user_client(SCOPE)

    total = sum(len(n) for sub in inventory.values() for n in sub.values())
    log(f"Classifying {total} playlists from {args.inventory}...")

    entries: List[Dict] = []
    for top_folder, subfolders in inventory.items():
        for subfolder, names in subfolders.items():
            log(f"  {top_folder} / {subfolder} ({len(names)})")
            entries.extend(build_entries(sp, {top_folder: {subfolder: names}}))

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": "yurkoon",
        "source": args.inventory,
        "unmatched_names": [],
        "playlists": entries,
    }
    with open(args.output, "w") as f:
        json.dump(snapshot, f, indent=2)
    log(f"Wrote {len(entries)} playlists to {args.output}.")
    print(args.output)


if __name__ == "__main__":
    main()
