"""Snapshot the current user's playlists with aggregated genre counts.

Read-only against Spotify. Writes a local snapshot.json cache (gitignored)
that propose_folders.py consumes, so the API-heavy aggregation runs once.
"""
import argparse
import json
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from spotipy.exceptions import SpotifyException

from spotify_common import build_user_client, log

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


def normalize_name(name: str) -> str:
    """Case- and whitespace-insensitive key for matching playlist names."""
    return " ".join(name.split()).casefold()


def select_playlists(
    playlists: List[Dict], folder_map: Dict[str, List[str]]
) -> Tuple[List[Dict], List[str]]:
    """Restrict `playlists` to the names listed in `folder_map`.

    The Web API cannot see playlist folders, so folder membership comes from
    a hand-built map of folder name -> playlist names (see folders.json).
    Names transcribed from the Spotify UI are often truncated, so a name that
    matches no playlist exactly falls back to a unique prefix match.

    Returns (selected playlists tagged with `source_folder`, unmatched names).
    A playlist listed under two folders is kept once, under the first.
    """
    by_norm: Dict[str, List[Dict]] = {}
    for playlist in playlists:
        by_norm.setdefault(normalize_name(playlist["name"]), []).append(playlist)

    selected: List[Dict] = []
    unmatched: List[str] = []
    seen_ids = set()

    for folder, wanted_names in folder_map.items():
        for wanted in wanted_names:
            key = normalize_name(wanted.rstrip(". …"))
            matches = by_norm.get(key, [])
            if not matches:
                matches = [
                    p for norm, group in by_norm.items() if norm.startswith(key)
                    for p in group
                ]
            if not matches:
                unmatched.append(f"{folder}: {wanted}")
                continue
            for playlist in matches:
                if playlist["id"] in seen_ids:
                    continue
                seen_ids.add(playlist["id"])
                selected.append({**playlist, "source_folder": folder})

    return selected, unmatched


def build_snapshot(
    sp, folder_map: Optional[Dict[str, List[str]]] = None
) -> Dict:
    """Fetch and aggregate playlists. API-heavy; run sparingly.

    With `folder_map`, only the playlists it names are fetched.
    """
    me = sp.current_user()
    playlists = fetch_all_playlists(sp)
    log(f"Found {len(playlists)} playlists in the library.")

    unmatched: List[str] = []
    if folder_map is not None:
        playlists, unmatched = select_playlists(playlists, folder_map)
        log(f"Scoped to {len(playlists)} playlists across "
            f"{len(folder_map)} folder(s).")
        for name in unmatched:
            log(f"  ! no playlist matched -> {name}")

    artist_cache: Dict[str, List[str]] = {}  # shared across playlists
    snapshot_playlists: List[Dict] = []
    for i, playlist in enumerate(playlists, 1):
        log(f"[{i}/{len(playlists)}] {playlist['name']}")
        track_artists = fetch_track_artist_ids(sp, playlist["id"])
        wanted = {a for ids in track_artists for a in ids}
        missing = sorted(wanted - artist_cache.keys())
        if missing:
            artist_cache.update(fetch_artist_genres(sp, missing))
        snapshot_playlists.append(
            {
                "id": playlist["id"],
                "name": playlist["name"],
                "source_folder": playlist.get("source_folder"),
                "total_tracks": (playlist.get("tracks") or {}).get(
                    "total", len(track_artists)
                ),
                "tracks_with_artists": len(track_artists),
                "genre_counts": aggregate_genres(track_artists, artist_cache),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": me["id"],
        "unmatched_names": unmatched,
        "playlists": snapshot_playlists,
    }


def load_folder_map(path: str) -> Dict[str, List[str]]:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(
            f"{path} not found. It maps folder name -> playlist names; "
            "see folders.example.json."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot playlists with aggregated genre counts."
    )
    parser.add_argument(
        "--output", default="snapshot.json",
        help="where to write the snapshot (default: snapshot.json)",
    )
    parser.add_argument(
        "--folders", default=None,
        help="JSON file mapping folder name -> playlist names; restricts the "
             "snapshot to those playlists (default: whole library)",
    )
    parser.add_argument(
        "--folder", action="append", default=None, metavar="NAME",
        help="only snapshot this folder from --folders (repeatable)",
    )
    args = parser.parse_args()

    folder_map = None
    if args.folders:
        folder_map = load_folder_map(args.folders)
        if args.folder:
            missing = [f for f in args.folder if f not in folder_map]
            if missing:
                raise SystemExit(
                    f"--folder not present in {args.folders}: "
                    f"{', '.join(missing)}"
                )
            folder_map = {f: folder_map[f] for f in args.folder}
    elif args.folder:
        raise SystemExit("--folder requires --folders")

    sp = build_user_client(SCOPE)
    snapshot = build_snapshot(sp, folder_map=folder_map)
    with open(args.output, "w") as f:
        json.dump(snapshot, f, indent=2)
    log(f"Wrote {len(snapshot['playlists'])} playlists to {args.output}.")
    print(args.output)


if __name__ == "__main__":
    main()
