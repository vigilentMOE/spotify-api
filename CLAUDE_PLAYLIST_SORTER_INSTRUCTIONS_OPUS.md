# Playlist Sorter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Snapshot every playlist in the user's Spotify account with aggregated per-playlist genre data, then propose a granular folder organization grouped by dominant genre family.

**Architecture:** Two new importable modules plus one shared helper. `playlist_snapshot.py` is the read-only, API-heavy step: it OAuths with read scopes, pages through all playlists and their tracks, batch-fetches artist genres, and writes a local `snapshot.json` cache. `propose_folders.py` is pure local analysis: it reads the snapshot, maps Spotify's micro-genres into ordered genre families, assigns each playlist a dominant family with a confidence score, and prints a markdown report of proposed folders. The Spotify Web API cannot see or move playlist folders, so the report is the deliverable — the user applies folder moves manually in the Spotify app.

**Tech Stack:** Python 3.11, spotipy 2.23.0, python-dotenv, pytest (new dev dependency). Tests mock spotipy with plain fake classes — no network, no credentials needed.

**Spec:** `CLAUDE.md`, section "Planned direction: organizing playlists by aggregated metadata". Read it before starting; it records the API constraints this plan is built around.

## Global Constraints

- Python 3.11 via the existing `.venv` (`source .venv/bin/activate` before anything).
- Pinned deps stay pinned: `spotipy==2.23.0`, `python-dotenv==1.0.0`, `tabulate==0.9.0`, `requests==2.31.0`. Add only `pytest==8.2.0`.
- New shared/importable code uses underscore filenames (`spotify_common.py`, `playlist_snapshot.py`, `propose_folders.py`). Do NOT rename the existing hyphenated scripts and do not modify them.
- Progress/log output goes to **stderr**; only machine-usable results (JSON path, report text) go to **stdout**.
- Never read `.env` (permission-blocked; contains real secrets). `.env.example` is the only env file you may read.
- Do NOT attempt to create/move playlist folders via the API (no such endpoint exists) and do NOT use `audio-features`/`audio-analysis`/recommendations endpoints (deprecated/restricted).
- Spotify batch limits: `current_user_playlists` pages at 50, `playlist_items` at 100, `sp.artists()` accepts at most 50 IDs.
- `snapshot.json` is a local cache and must be gitignored.
- Commit after every task with the message given in that task.

---

### Task 1: Test infrastructure + shared auth module

**Files:**
- Create: `spotify_common.py`
- Create: `conftest.py` (empty — makes pytest add the repo root to `sys.path` so root-level modules import from `tests/`)
- Create: `tests/test_spotify_common.py`
- Modify: `requirements.txt` (append `pytest==8.2.0`)
- Modify: `.gitignore` (append `snapshot.json` and `__pycache__/`)

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `spotify_common.log(message: str) -> None` — prints to stderr.
  - `spotify_common.require_env(name: str) -> str` — returns the env var or raises `SystemExit` with the var name in the message.
  - `spotify_common.build_user_client(scope: str) -> spotipy.Spotify` — OAuth Authorization Code flow client.
  - `spotify_common.DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"`

- [ ] **Step 1: Add pytest to requirements and install**

Append to `requirements.txt`:

```
pytest==8.2.0
```

Run: `source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 2: Append cache entries to `.gitignore`**

Append these two lines to `.gitignore`:

```
snapshot.json
__pycache__/
```

- [ ] **Step 3: Create empty `conftest.py` at repo root**

```python
```

(An empty file is correct — its presence makes pytest insert the repo root into `sys.path`.)

- [ ] **Step 4: Write the failing tests**

Create `tests/test_spotify_common.py`:

```python
import pytest

import spotify_common


def test_log_writes_to_stderr(capsys):
    spotify_common.log("hello")
    captured = capsys.readouterr()
    assert captured.err == "hello\n"
    assert captured.out == ""


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "abc123")
    assert spotify_common.require_env("SPOTIFY_CLIENT_ID") == "abc123"


def test_require_env_missing_raises_systemexit(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with pytest.raises(SystemExit, match="SPOTIFY_CLIENT_ID"):
        spotify_common.require_env("SPOTIFY_CLIENT_ID")


def test_require_env_empty_string_raises_systemexit(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "")
    with pytest.raises(SystemExit, match="SPOTIFY_CLIENT_ID"):
        spotify_common.require_env("SPOTIFY_CLIENT_ID")
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `pytest tests/test_spotify_common.py -v`
Expected: FAIL (collection error: `ModuleNotFoundError: No module named 'spotify_common'`)

- [ ] **Step 6: Write `spotify_common.py`**

```python
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_spotify_common.py -v`
Expected: 4 passed

- [ ] **Step 8: Commit**

```bash
git add spotify_common.py conftest.py tests/test_spotify_common.py requirements.txt .gitignore
git commit -m "feat: add shared auth module and pytest infrastructure"
```

---

### Task 2: Pure aggregation helpers in `playlist_snapshot.py`

**Files:**
- Create: `playlist_snapshot.py` (helpers only; fetchers arrive in Task 3, CLI in Task 4)
- Create: `tests/test_playlist_snapshot.py`

**Interfaces:**
- Consumes: nothing from Task 1 yet (pure functions).
- Produces:
  - `playlist_snapshot.chunked(seq: Sequence, size: int) -> Iterator[Sequence]` — yields consecutive slices of at most `size`.
  - `playlist_snapshot.aggregate_genres(track_artist_ids: List[List[str]], artist_genres: Dict[str, List[str]]) -> Dict[str, int]` — per-playlist genre counts; each track contributes at most 1 per distinct genre.
  - Module constants: `SCOPE = "playlist-read-private playlist-read-collaborative"`, `PLAYLIST_PAGE = 50`, `TRACK_PAGE = 100`, `ARTIST_BATCH = 50`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_playlist_snapshot.py`:

```python
import playlist_snapshot


def test_chunked_splits_into_batches():
    assert list(playlist_snapshot.chunked(["a", "b", "c", "d", "e"], 2)) == [
        ["a", "b"], ["c", "d"], ["e"],
    ]


def test_chunked_empty_sequence_yields_nothing():
    assert list(playlist_snapshot.chunked([], 10)) == []


def test_aggregate_genres_counts_tracks_per_genre():
    track_artist_ids = [["a1"], ["a2"], ["a1", "a2"]]
    artist_genres = {"a1": ["rock"], "a2": ["rock", "pop"]}
    counts = playlist_snapshot.aggregate_genres(track_artist_ids, artist_genres)
    # rock: all 3 tracks; pop: the two tracks featuring a2.
    assert counts == {"rock": 3, "pop": 2}


def test_aggregate_genres_track_counts_shared_genre_once():
    # Two artists on one track sharing a genre must not double-count it.
    track_artist_ids = [["a1", "a2"]]
    artist_genres = {"a1": ["metal"], "a2": ["metal"]}
    assert playlist_snapshot.aggregate_genres(track_artist_ids, artist_genres) == {
        "metal": 1,
    }


def test_aggregate_genres_unknown_artist_ignored():
    track_artist_ids = [["a1", "missing"]]
    artist_genres = {"a1": ["jazz"]}
    assert playlist_snapshot.aggregate_genres(track_artist_ids, artist_genres) == {
        "jazz": 1,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_playlist_snapshot.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'playlist_snapshot'`)

- [ ] **Step 3: Write the helpers**

Create `playlist_snapshot.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_playlist_snapshot.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add playlist_snapshot.py tests/test_playlist_snapshot.py
git commit -m "feat: add genre aggregation helpers for playlist snapshot"
```

---

### Task 3: Paginated fetchers against a fake Spotify client

**Files:**
- Modify: `playlist_snapshot.py` (append fetchers)
- Create: `tests/fakes.py`
- Modify: `tests/test_playlist_snapshot.py` (append fetcher tests)

**Interfaces:**
- Consumes: `chunked`, `PLAYLIST_PAGE`, `TRACK_PAGE`, `ARTIST_BATCH` from Task 2.
- Produces:
  - `playlist_snapshot.fetch_all_playlists(sp) -> List[Dict]` — every playlist object from `sp.current_user_playlists`, all pages.
  - `playlist_snapshot.fetch_track_artist_ids(sp, playlist_id: str) -> List[List[str]]` — one inner list of artist IDs per track; tracks with no artist IDs (local files, removed tracks) are skipped.
  - `playlist_snapshot.fetch_artist_genres(sp, artist_ids: Sequence[str]) -> Dict[str, List[str]]` — batched, deduplicated artist-ID -> genres map.
  - `tests/fakes.py:FakeSpotify` — constructor `FakeSpotify(playlists=None, tracks_by_playlist=None, artists_by_id=None)` implementing `current_user()`, `current_user_playlists(limit, offset)`, `playlist_items(playlist_id, fields, limit, offset)`, `artists(ids)`; records batch sizes in `self.artists_calls`.

- [ ] **Step 1: Write the fake Spotify client**

Create `tests/fakes.py`:

```python
"""In-memory stand-in for spotipy.Spotify, mirroring the response shapes
the snapshot fetchers rely on. No network, no auth."""
from typing import Dict, List, Optional


class FakeSpotify:
    def __init__(
        self,
        playlists: Optional[List[Dict]] = None,
        tracks_by_playlist: Optional[Dict[str, List[Dict]]] = None,
        artists_by_id: Optional[Dict[str, List[str]]] = None,
    ):
        self._playlists = playlists or []
        self._tracks = tracks_by_playlist or {}
        self._artists = artists_by_id or {}
        self.artists_calls: List[List[str]] = []  # batch-size assertions

    def current_user(self) -> Dict:
        return {"id": "testuser", "display_name": "Test User"}

    def current_user_playlists(self, limit: int, offset: int) -> Dict:
        return {"items": self._playlists[offset:offset + limit]}

    def playlist_items(
        self, playlist_id: str, fields: str, limit: int, offset: int
    ) -> Dict:
        items = self._tracks.get(playlist_id, [])[offset:offset + limit]
        return {"items": items}

    def artists(self, ids: List[str]) -> Dict:
        self.artists_calls.append(list(ids))
        return {
            "artists": [
                {"id": i, "genres": self._artists.get(i, [])} for i in ids
            ]
        }
```

- [ ] **Step 2: Write the failing fetcher tests**

Append to `tests/test_playlist_snapshot.py`:

```python
from tests.fakes import FakeSpotify


def _playlist(i):
    return {"id": f"pl{i}", "name": f"Playlist {i}", "tracks": {"total": 1}}


def _track_item(artist_ids):
    return {"track": {"artists": [{"id": a} for a in artist_ids]}}


def test_fetch_all_playlists_paginates_past_one_page():
    playlists = [_playlist(i) for i in range(75)]  # PLAYLIST_PAGE is 50
    sp = FakeSpotify(playlists=playlists)
    result = playlist_snapshot.fetch_all_playlists(sp)
    assert len(result) == 75
    assert result[0]["id"] == "pl0"
    assert result[74]["id"] == "pl74"


def test_fetch_track_artist_ids_paginates_and_skips_artistless():
    items = [_track_item(["a1"]) for _ in range(150)]  # TRACK_PAGE is 100
    items.append({"track": None})                        # removed/unavailable
    items.append({"track": {"artists": [{"id": None}]}})  # local file
    sp = FakeSpotify(tracks_by_playlist={"pl0": items})
    result = playlist_snapshot.fetch_track_artist_ids(sp, "pl0")
    assert result == [["a1"]] * 150


def test_fetch_artist_genres_batches_and_dedupes():
    artists = {f"a{i}": ["rock"] for i in range(60)}
    sp = FakeSpotify(artists_by_id=artists)
    ids = list(artists) + list(artists)  # duplicates must collapse
    result = playlist_snapshot.fetch_artist_genres(sp, ids)
    assert result == artists
    assert all(len(call) <= 50 for call in sp.artists_calls)  # ARTIST_BATCH
    assert sum(len(call) for call in sp.artists_calls) == 60
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `pytest tests/test_playlist_snapshot.py -v`
Expected: earlier tests PASS; the 3 new tests FAIL with `AttributeError: module 'playlist_snapshot' has no attribute 'fetch_all_playlists'` (and similar)

- [ ] **Step 4: Implement the fetchers**

Append to `playlist_snapshot.py`:

```python
def fetch_all_playlists(sp) -> List[Dict]:
    """All playlists in the user's library (owned and followed)."""
    playlists: List[Dict] = []
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=PLAYLIST_PAGE, offset=offset)
        items = page.get("items", [])
        playlists.extend(items)
        if len(items) < PLAYLIST_PAGE:
            break  # short page means last page
        offset += PLAYLIST_PAGE
    return playlists


def fetch_track_artist_ids(sp, playlist_id: str) -> List[List[str]]:
    """Per-track lists of artist IDs for one playlist.

    Local files and removed tracks have no artist IDs and are skipped.
    The `fields` filter keeps the payload small.
    """
    tracks: List[List[str]] = []
    offset = 0
    fields = "items(track(artists(id)))"
    while True:
        page = sp.playlist_items(
            playlist_id, fields=fields, limit=TRACK_PAGE, offset=offset
        )
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_playlist_snapshot.py -v`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add playlist_snapshot.py tests/fakes.py tests/test_playlist_snapshot.py
git commit -m "feat: add paginated playlist/track/artist fetchers"
```

---

### Task 4: Snapshot orchestration + CLI

**Files:**
- Modify: `playlist_snapshot.py` (append `build_snapshot` and `main`)
- Modify: `tests/test_playlist_snapshot.py` (append `build_snapshot` test)

**Interfaces:**
- Consumes: all Task 2/3 functions; `spotify_common.log`, `spotify_common.build_user_client` from Task 1.
- Produces:
  - `playlist_snapshot.build_snapshot(sp) -> Dict` — the full snapshot dict.
  - Snapshot JSON schema (Task 5/6 depend on this exactly):

```json
{
  "generated_at": "2026-08-30T12:00:00+00:00",
  "user_id": "testuser",
  "playlists": [
    {
      "id": "pl0",
      "name": "Playlist 0",
      "total_tracks": 42,
      "tracks_with_artists": 40,
      "genre_counts": {"rock": 30, "pop": 12}
    }
  ]
}
```

  - CLI: `python playlist_snapshot.py [--output PATH]` (default `snapshot.json`); prints the output path to stdout on success.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_playlist_snapshot.py`:

```python
def test_build_snapshot_aggregates_each_playlist():
    playlists = [
        {"id": "pl0", "name": "Rock Mix", "tracks": {"total": 2}},
        {"id": "pl1", "name": "Empty", "tracks": {"total": 0}},
    ]
    tracks = {
        "pl0": [_track_item(["a1"]), _track_item(["a2"])],
        "pl1": [],
    }
    artists = {"a1": ["rock"], "a2": ["rock", "pop"]}
    sp = FakeSpotify(
        playlists=playlists, tracks_by_playlist=tracks, artists_by_id=artists
    )

    snapshot = playlist_snapshot.build_snapshot(sp)

    assert snapshot["user_id"] == "testuser"
    assert "generated_at" in snapshot
    assert len(snapshot["playlists"]) == 2
    rock_mix = snapshot["playlists"][0]
    assert rock_mix == {
        "id": "pl0",
        "name": "Rock Mix",
        "total_tracks": 2,
        "tracks_with_artists": 2,
        "genre_counts": {"rock": 2, "pop": 1},
    }
    assert snapshot["playlists"][1]["genre_counts"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_playlist_snapshot.py::test_build_snapshot_aggregates_each_playlist -v`
Expected: FAIL with `AttributeError: module 'playlist_snapshot' has no attribute 'build_snapshot'`

- [ ] **Step 3: Implement `build_snapshot` and `main`**

Append to `playlist_snapshot.py` (and add these imports at the top of the file: `import argparse`, `import json`, `from datetime import datetime, timezone`, `from spotify_common import build_user_client, log`):

```python
def build_snapshot(sp) -> Dict:
    """Fetch and aggregate every playlist. API-heavy; run sparingly."""
    me = sp.current_user()
    playlists = fetch_all_playlists(sp)
    log(f"Found {len(playlists)} playlists.")

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
                "total_tracks": playlist.get("tracks", {}).get(
                    "total", len(track_artists)
                ),
                "tracks_with_artists": len(track_artists),
                "genre_counts": aggregate_genres(track_artists, artist_cache),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": me["id"],
        "playlists": snapshot_playlists,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot all playlists with aggregated genre counts."
    )
    parser.add_argument(
        "--output", default="snapshot.json",
        help="where to write the snapshot (default: snapshot.json)",
    )
    args = parser.parse_args()

    sp = build_user_client(SCOPE)
    snapshot = build_snapshot(sp)
    with open(args.output, "w") as f:
        json.dump(snapshot, f, indent=2)
    log(f"Wrote {len(snapshot['playlists'])} playlists to {args.output}.")
    print(args.output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `pytest -v`
Expected: all tests pass (13 total so far)

- [ ] **Step 5: Commit**

```bash
git add playlist_snapshot.py tests/test_playlist_snapshot.py
git commit -m "feat: add snapshot orchestration and CLI"
```

---

### Task 5: Genre-family classification in `propose_folders.py`

**Files:**
- Create: `propose_folders.py` (classification only; grouping/report in Task 6)
- Create: `tests/test_propose_folders.py`

**Interfaces:**
- Consumes: the snapshot JSON schema from Task 4 (`genre_counts` dicts).
- Produces:
  - `propose_folders.GENRE_FAMILIES: List[Tuple[str, Tuple[str, ...]]]` — ordered (family name, keywords); **first match wins**, so specific families precede broad ones.
  - `propose_folders.classify_genre(genre: str) -> Optional[str]` — family name or `None` (case-insensitive substring match).
  - `propose_folders.family_profile(genre_counts: Dict[str, int]) -> Dict[str, int]` — family -> summed track counts (unclassified genres dropped).
  - `propose_folders.dominant_family(genre_counts: Dict[str, int]) -> Tuple[Optional[str], float]` — `(family, coverage)` where coverage is the dominant family's share of all classified counts, in `[0.0, 1.0]`; `(None, 0.0)` when nothing classifies.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_propose_folders.py`:

```python
import propose_folders


def test_classify_genre_matches_keyword_substring():
    assert propose_folders.classify_genre("progressive metalcore") == "Metal"
    assert propose_folders.classify_genre("Deep House") == "Electronic"
    assert propose_folders.classify_genre("gregorian chant") is None


def test_classify_genre_order_specific_before_broad():
    # 'pop punk' contains both 'punk' and 'pop'; Punk is listed first.
    assert propose_folders.classify_genre("pop punk") == "Punk"
    # 'indie rock' should land in Rock, not a generic bucket.
    assert propose_folders.classify_genre("indie rock") == "Rock"


def test_family_profile_sums_counts_per_family():
    counts = {"death metal": 5, "metalcore": 3, "pop": 2, "unknowncore": 9}
    profile = propose_folders.family_profile(counts)
    assert profile == {"Metal": 8, "Pop": 2}


def test_dominant_family_returns_family_and_coverage():
    counts = {"death metal": 6, "pop": 2}
    family, coverage = propose_folders.dominant_family(counts)
    assert family == "Metal"
    assert coverage == 0.75


def test_dominant_family_no_classified_genres():
    assert propose_folders.dominant_family({"unknowncore": 3}) == (None, 0.0)
    assert propose_folders.dominant_family({}) == (None, 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_propose_folders.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'propose_folders'`)

- [ ] **Step 3: Implement classification**

Create `propose_folders.py`:

```python
"""Propose a playlist folder organization from a snapshot.json.

Pure local analysis - no Spotify calls. The Web API cannot create or move
playlist folders, so the output is a report the user applies manually in
the Spotify app.

Spotify genres are micro-genres ('progressive metalcore', 'art pop'), so
they are folded into broad families by ordered keyword matching. Order
matters: the first family whose keyword appears in the genre string wins,
so specific families (Metal, Punk) come before broad ones (Rock, Pop).
"""
from typing import Dict, List, Optional, Tuple

GENRE_FAMILIES: List[Tuple[str, Tuple[str, ...]]] = [
    ("Metal", ("metal", "deathcore", "djent", "grindcore")),
    ("Punk", ("punk", "hardcore", "emo", "screamo", "ska")),
    ("Rock", ("rock", "grunge", "shoegaze", "britpop", "psychedelic")),
    ("Hip-Hop", ("hip hop", "hip-hop", "rap", "drill", "trap", "grime", "boom bap")),
    ("R&B / Soul", ("r&b", "soul", "funk", "motown", "new jack swing")),
    ("Electronic", (
        "electronic", "edm", "house", "techno", "trance", "dubstep",
        "drum and bass", "dnb", "garage", "synthwave", "electro", "idm",
        "breakbeat", "hardstyle",
    )),
    ("Country / Folk", (
        "country", "folk", "americana", "bluegrass", "singer-songwriter",
    )),
    ("Latin", (
        "latin", "reggaeton", "salsa", "bachata", "corrido", "cumbia",
        "mariachi",
    )),
    ("Jazz / Blues", ("jazz", "blues", "bossa nova", "swing", "big band")),
    ("Classical / Score", (
        "classical", "orchestra", "orchestral", "soundtrack", "score",
        "baroque", "romantic era", "opera",
    )),
    ("Ambient / Chill", (
        "ambient", "lo-fi", "lofi", "chill", "sleep", "meditation",
        "new age", "downtempo",
    )),
    # Broadest last: many micro-genres end in 'pop' ('art pop', 'indie pop').
    ("Pop", ("pop", "boy band", "girl group", "idol")),
]


def classify_genre(genre: str) -> Optional[str]:
    lowered = genre.lower()
    for family, keywords in GENRE_FAMILIES:
        if any(keyword in lowered for keyword in keywords):
            return family
    return None


def family_profile(genre_counts: Dict[str, int]) -> Dict[str, int]:
    profile: Dict[str, int] = {}
    for genre, count in genre_counts.items():
        family = classify_genre(genre)
        if family is not None:
            profile[family] = profile.get(family, 0) + count
    return profile


def dominant_family(genre_counts: Dict[str, int]) -> Tuple[Optional[str], float]:
    profile = family_profile(genre_counts)
    total = sum(profile.values())
    if total == 0:
        return None, 0.0
    family = max(profile, key=lambda f: profile[f])
    return family, profile[family] / total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_propose_folders.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add propose_folders.py tests/test_propose_folders.py
git commit -m "feat: add genre-family classification"
```

---

### Task 6: Folder proposal grouping + markdown report + CLI

**Files:**
- Modify: `propose_folders.py` (append grouping, report, `main`)
- Modify: `tests/test_propose_folders.py` (append tests)

**Interfaces:**
- Consumes: Task 5 functions; snapshot schema from Task 4; `spotify_common.log`.
- Produces:
  - `propose_folders.MIXED_FOLDER = "Mixed / Low Confidence"`, `propose_folders.UNKNOWN_FOLDER = "Unknown (no genre data)"`
  - `propose_folders.propose(snapshot: Dict, min_coverage: float = 0.5) -> Dict[str, List[Dict]]` — folder name -> playlist entries `{"name": str, "id": str, "coverage": float, "top_genres": List[str]}`, families ordered by `GENRE_FAMILIES` order, then `MIXED_FOLDER`, then `UNKNOWN_FOLDER` (empty folders omitted). `top_genres` = the playlist's 3 most frequent raw genres.
  - `propose_folders.render_report(groups: Dict[str, List[Dict]], generated_at: str) -> str` — markdown.
  - CLI: `python propose_folders.py [--snapshot PATH] [--min-coverage F]` — reads `snapshot.json` by default, prints the report to stdout.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_propose_folders.py`:

```python
def _snapshot(playlists):
    return {
        "generated_at": "2026-08-30T12:00:00+00:00",
        "user_id": "testuser",
        "playlists": playlists,
    }


def _pl(pid, name, genre_counts):
    return {
        "id": pid,
        "name": name,
        "total_tracks": sum(genre_counts.values()) or 1,
        "tracks_with_artists": sum(genre_counts.values()) or 1,
        "genre_counts": genre_counts,
    }


def test_propose_groups_by_dominant_family():
    snapshot = _snapshot([
        _pl("p1", "Heavy Stuff", {"death metal": 9, "pop": 1}),
        _pl("p2", "Beach Vibes", {"indie pop": 8, "dance pop": 4}),
    ])
    groups = propose_folders.propose(snapshot)
    assert list(groups) == ["Metal", "Pop"]
    assert groups["Metal"][0]["name"] == "Heavy Stuff"
    assert groups["Metal"][0]["coverage"] == 0.9
    assert groups["Metal"][0]["top_genres"] == ["death metal", "pop"]


def test_propose_low_coverage_goes_to_mixed():
    snapshot = _snapshot([
        _pl("p1", "Everything", {"rock": 3, "pop": 3, "trap": 3, "jazz": 1}),
    ])
    groups = propose_folders.propose(snapshot, min_coverage=0.5)
    assert list(groups) == [propose_folders.MIXED_FOLDER]


def test_propose_no_genre_data_goes_to_unknown():
    snapshot = _snapshot([_pl("p1", "Local Files", {})])
    groups = propose_folders.propose(snapshot)
    assert list(groups) == [propose_folders.UNKNOWN_FOLDER]
    assert groups[propose_folders.UNKNOWN_FOLDER][0]["coverage"] == 0.0


def test_render_report_contains_folders_and_playlists():
    snapshot = _snapshot([
        _pl("p1", "Heavy Stuff", {"death metal": 9, "pop": 1}),
    ])
    report = propose_folders.render_report(
        propose_folders.propose(snapshot), snapshot["generated_at"]
    )
    assert "## Metal (1 playlist" in report
    assert "Heavy Stuff" in report
    assert "90%" in report
    assert "death metal" in report
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/test_propose_folders.py -v`
Expected: Task 5 tests PASS; the 4 new tests FAIL with `AttributeError: module 'propose_folders' has no attribute 'propose'` (and similar)

- [ ] **Step 3: Implement grouping, report, and CLI**

Append to `propose_folders.py` (and add these imports at the top: `import argparse`, `import json`, `from spotify_common import log`):

```python
MIXED_FOLDER = "Mixed / Low Confidence"
UNKNOWN_FOLDER = "Unknown (no genre data)"


def propose(snapshot: Dict, min_coverage: float = 0.5) -> Dict[str, List[Dict]]:
    """Group playlists into proposed folders by dominant genre family."""
    family_order = [name for name, _ in GENRE_FAMILIES]
    groups: Dict[str, List[Dict]] = {
        name: [] for name in family_order + [MIXED_FOLDER, UNKNOWN_FOLDER]
    }

    for playlist in snapshot["playlists"]:
        counts = playlist["genre_counts"]
        family, coverage = dominant_family(counts)
        top_genres = sorted(counts, key=lambda g: counts[g], reverse=True)[:3]
        entry = {
            "name": playlist["name"],
            "id": playlist["id"],
            "coverage": coverage,
            "top_genres": top_genres,
        }
        if family is None:
            groups[UNKNOWN_FOLDER].append(entry)
        elif coverage < min_coverage:
            groups[MIXED_FOLDER].append(entry)
        else:
            groups[family].append(entry)

    for entries in groups.values():
        entries.sort(key=lambda e: e["coverage"], reverse=True)
    return {name: entries for name, entries in groups.items() if entries}


def render_report(groups: Dict[str, List[Dict]], generated_at: str) -> str:
    lines = [
        "# Proposed playlist folders",
        "",
        f"Snapshot taken: {generated_at}",
        "",
        "The Spotify API cannot move folders; apply these groupings",
        "manually in the Spotify app (drag playlists into folders).",
        "",
    ]
    for folder, entries in groups.items():
        plural = "playlist" if len(entries) == 1 else "playlists"
        lines.append(f"## {folder} ({len(entries)} {plural})")
        lines.append("")
        for e in entries:
            genres = ", ".join(e["top_genres"]) or "no genres found"
            lines.append(
                f"- **{e['name']}** — {e['coverage']:.0%} match ({genres})"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Propose playlist folders from a snapshot.json."
    )
    parser.add_argument(
        "--snapshot", default="snapshot.json",
        help="snapshot file from playlist_snapshot.py (default: snapshot.json)",
    )
    parser.add_argument(
        "--min-coverage", type=float, default=0.5,
        help="dominant-family share below which a playlist is Mixed "
             "(default: 0.5)",
    )
    args = parser.parse_args()

    try:
        with open(args.snapshot) as f:
            snapshot = json.load(f)
    except FileNotFoundError:
        raise SystemExit(
            f"{args.snapshot} not found - run 'python playlist_snapshot.py' first."
        )

    groups = propose(snapshot, min_coverage=args.min_coverage)
    log(f"Grouped {len(snapshot['playlists'])} playlists into "
        f"{len(groups)} folders.")
    print(render_report(groups, snapshot.get("generated_at", "unknown")))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`
Expected: all tests pass (22 total)

- [ ] **Step 5: Commit**

```bash
git add propose_folders.py tests/test_propose_folders.py
git commit -m "feat: add folder proposal grouping and markdown report"
```

---

### Task 7: Documentation + live smoke test

**Files:**
- Modify: `README.md` (new "Sort playlists into folders" section under Usage)
- Modify: `CLAUDE.md` (Commands section + replace the "Planned direction" framing with the implemented reality)

**Interfaces:**
- Consumes: the two CLIs from Tasks 4 and 6.
- Produces: user-facing docs; no code.

- [ ] **Step 1: Add a README usage section**

Append to `README.md` under Usage:

```markdown
### Sort playlists into folders (genre analysis)

Two steps: snapshot your library (API-heavy, cached locally), then generate
a proposed folder organization from the snapshot (instant, local).

```sh
# 1. Snapshot every playlist with aggregated genre counts.
#    First run re-authorizes in the browser (adds read scopes).
python playlist_snapshot.py

# 2. Propose folders grouped by dominant genre family.
python propose_folders.py > proposed-folders.md

# Tune how confident a playlist must be before leaving the Mixed bucket:
python propose_folders.py --min-coverage 0.6
```

The Spotify Web API cannot create or move playlist folders, so the report
is the deliverable — apply the groupings manually in the Spotify app.
Re-run `playlist_snapshot.py` whenever your library has changed enough to
matter; `propose_folders.py` reuses the cached `snapshot.json`.
```

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`: add `python playlist_snapshot.py`, `python propose_folders.py`, and `pytest` to the Commands section; in the "Planned direction" section, change the framing from planned to implemented (name the two modules and `spotify_common.py`, keep the API-constraint bullets — they remain true and load-bearing).

- [ ] **Step 3: Run the full test suite one final time**

Run: `pytest -v`
Expected: all tests pass

- [ ] **Step 4: Live smoke test (requires the user's credentials — cannot run in CI)**

Run: `python playlist_snapshot.py && python propose_folders.py | head -40`

Expected: a browser OAuth prompt on first run (new scopes), progress lines on stderr (`[1/N] <playlist name>`...), then the top of a markdown report listing real playlists under genre-family headers. If this cannot be run non-interactively, ask the user to run it and report the output — do not fake or skip verification silently.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document playlist sorter workflow"
```

---

## Notes for the executor

- **Rate limits:** `build_snapshot` makes roughly (playlists / 50) + (total tracks / 100) + (unique artists / 50) requests. spotipy retries 429s automatically; if a run is cut short, just re-run — the snapshot is written only at the end, so there is no partial-state cleanup.
- **Re-auth gotcha:** the cached token in `.cache` was issued for `create-playlist.py`'s write scopes. spotipy will detect the missing read scopes and re-open the browser once. Do not delete `.cache` manually unless auth is wedged.
- **Genre families are a starting vocabulary**, not gospel. If the live smoke test shows a big `Unknown (no genre data)` or `Mixed` bucket, the fix is adding keywords to `GENRE_FAMILIES` (with a matching test in `test_classify_genre_*`), not restructuring the pipeline.
