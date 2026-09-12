# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A small collection of standalone Python CLI scripts for working with the Spotify Web API (via `spotipy`), owned by a single user and run against their personal Spotify account. There is no package structure, no build step, and no test suite — each script is self-contained and run directly.

## Commands

```sh
source .venv/bin/activate          # Python 3.11 venv already exists in-repo
pip install -r requirements.txt

python search-authors.py           # interactive: search artists by name -> artist IDs
python get-artist-genre.py         # interactive: artist ID -> genre list
python create-playlist.py <stats.fm profile URL or username> [--limit N] [--range weeks|months|lifetime] [--name X] [--public] [--dry-run]

python liked_songs.py [--output liked_songs.txt] [--limit N] [--max-genres N]

python playlist_snapshot.py [--folders folders.json] [--folder NAME] [--output snapshot.json]
python folder_inventory.py [--inventory folder_inventory.json] [--no-api]
python propose_folders.py [--snapshot snapshot.json] [--min-size 3] [--min-coverage 0.5]

pytest                             # full suite
pytest tests/test_propose_folders.py::test_classify_genre_matches_keyword_substring -v
```

`pytest` is the test runner; tests use in-memory fakes (`tests/fakes.py`) and never hit the network. `mypy` has been used ad hoc (`.mypy_cache` is present); code carries type hints, so keep new code typed.

## Architecture

Four scripts, two authentication flows — picking the right flow is the main architectural decision when adding a script:

- **Client-credentials flow** (`SpotifyClientCredentials`): used by `search-authors.py` and `get-artist-genre.py`. Read-only access to the public catalog. No browser, no user context.
- **OAuth Authorization Code flow** (`SpotifyOAuth`): used by `create-playlist.py`, `playlist_snapshot.py` and `liked_songs.py`. Required for anything touching the user's account (reading private playlists and the saved-track library, creating/modifying playlists). First run opens a browser; the token is cached in `.cache` (gitignored). Scopes are declared per-script (currently `playlist-modify-private playlist-modify-public`). The redirect URI must exactly match one registered in the Spotify app dashboard and must use `127.0.0.1`, not `localhost`.

Credentials come from `.env` (`SPOTIFY_CLIENT_ID`, `SPOTIFY_SECRET`, optional `SPOTIFY_REDIRECT_URI`) loaded with `python-dotenv`. `.env.example` documents the expected keys.

Conventions established by `create-playlist.py` (follow these in new scripts):

- Progress/log output goes to **stderr**; only machine-usable results (IDs, URLs) go to **stdout**, so output can be piped.
- Spotify batch limits are respected explicitly (100 track URIs per playlist-add request).
- External paginated APIs are fetched defensively: dedupe by ID, cap page counts to avoid infinite loops, over-fetch to compensate for items missing Spotify mappings.
- stats.fm API calls need a browser-like `User-Agent` (the default python-requests UA gets a 403) and use a shared `requests.Session`.

Script filenames use hyphens, so they cannot be imported as modules. If future work needs shared code (auth helpers, genre aggregation), extract it into an underscore-named module (e.g. `spotify_common.py`) rather than importing across hyphenated scripts.

## Liked Songs listing

`liked_songs.py` pages `current_user_saved_tracks`, batch-fetches artist
genres through `spotify_common.fetch_artist_genres`, and renders a fixed-width
table built to be read by a person and an LLM from the same file. No row
exceeds `MAX_ROW_WIDTH` (200).

**This script is slow by nature and that is not a bug.** Saved tracks page 50
at a time with no bulk endpoint, so a real library (11,560 tracks, measured)
is 230+ sequential requests, ~3.5 minutes. Because a silent multi-minute run
is indistinguishable from a hang, `fetch_saved_tracks` announces the library
total from the first response's `total` field and `report_progress` logs a
throttled `done/total` line every `PROGRESS_EVERY` (500) items; the artist
phase does the same through `fetch_artist_genres`'s `on_progress` callback.
Keep that instrumentation if you touch either loop.

Layout lives in one place: the `COLUMNS` tuple of `(header, width)` pairs, with
width `0` meaning the final unpadded column. `render_table` pads and truncates
straight from it, so changing a column means editing that tuple, not the
renderer — keep `MAX_ROW_WIDTH` in step (a test asserts they agree). Every
field falls back to `-` rather than dropping a row — local files have no ID,
no release date and no popularity, and ~28% of tracks in practice have no
genres at all because their artists carry none.

Genres are artist-level (Spotify has no track genre): `collect_genres` unions
the track's artists' genres, dedupes, and keeps first-appearance order so the
primary artist leads. Two caps keep the row on one line: `--max-genres`
(default 4) on the count, and `fit_genres`'s `GENRES_WIDTH` (52) on the
rendered width, which drops whole genres rather than cutting one mid-word.
`--max-genres 0` lifts both, for feeding an LLM the complete tag set.

`liked_songs.txt` is gitignored personal data.

## Playlist folder sorting

Implemented across three importable modules plus a shared helper:

- `spotify_common.py` — `log`, `require_env`, `build_user_client(scope)`, plus the batching helpers `chunked` and `fetch_artist_genres` (50-ID cap) shared by every script that needs artist genres.
- `playlist_snapshot.py` — reads the API: pages all playlists, fetches each one's tracks, batch-fetches artist genres, writes `snapshot.json`. `--folders`/`--folder` restrict it to a hand-built folder map (with prefix fallback for names transcribed from truncated UI labels).
- `folder_inventory.py` — the fallback source for playlists the API can't see (below). Emits the same snapshot shape.
- `propose_folders.py` — pure local analysis. Folds genre strings into ordered families (`GENRE_FAMILIES`, first match wins, specific before broad), groups playlists by source folder then dominant family, and renders a markdown report.

`snapshot.json`, `folders.json`, and `folder_inventory.json` are gitignored personal data.

**The hard constraint discovered in practice:** Spotify's personalised `"<Genre> Mix"` and `"<Song> Radio"` playlists are completely invisible to the Web API. They do not appear in `current_user_playlists` (verified: 149 playlists visible against a library containing hundreds of them) and cannot be found via `search`, so their tracks are unreadable. Genre for those comes from `folder_inventory.py` instead: the name itself for `"<Genre> Mix"`, and a seed-track search plus artist-genre lookup for `"<Song> Radio"`.

`GENRE_FAMILIES` has two tiers: genre families first, then mood/activity families (Workout, Focus, Sad, Night, …), so a name carrying a real genre files by genre and only mood-only names fall through. Tune the taxonomy by adding keywords with a matching test — don't restructure the pipeline.

Key Spotify API constraints (verify against current docs before building, but true as of mid-2026):

- **Playlist folders are invisible to the Web API.** There is no endpoint to list, create, or move playlist folders — folders exist only in the Spotify clients. Practical consequence: a script can read/analyze/rename playlists and reorder tracks, and can emit a *recommended* folder organization, but the user must apply folder moves manually in the Spotify app (or via unofficial means, which this repo does not use).
- **Genre is not a track attribute.** Genres live on *artists* (and sometimes albums). Aggregating a playlist's genre means: fetch playlist tracks → collect artist IDs → batch-fetch artists (`spotify.artists()` accepts up to 50 IDs per call) → tally genre frequencies. `get-artist-genre.py` is the single-artist prototype of this.
- **Audio features endpoints are deprecated** (`audio-features`, `audio-analysis`, recommendations, related-artists — restricted for apps since Nov 2024). Do not plan aggregation around danceability/energy/tempo from Spotify; genre + artist popularity + release dates are the reliable metadata.
- Reading the user's own playlists requires OAuth with `playlist-read-private` (and `playlist-read-collaborative` if applicable) — scopes beyond what `create-playlist.py` currently requests, so expect a re-authorization when first adding these. Liked Songs needs `user-library-read`, different again (`liked_songs.py`).
- **Liked Songs is not a playlist.** It has no playlist ID and is unreachable through `playlist_items`; read it with `current_user_saved_tracks`, which paginates at 50 and returns `added_at` alongside each track.
- Playlist track listings paginate at 100 items (`spotify.playlist_items` with `offset`), and `current_user_playlists` paginates at 50.
- A playlist that 404s or 403s on `playlist_items` is skipped rather than aborting the run — algorithmic playlists behave this way.

Keep analysis (read-only) separated from any mutation, and offer `--dry-run` on anything that writes, following `create-playlist.py`'s pattern.
