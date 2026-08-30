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
```

There is no configured linter or test runner. `mypy` has been used ad hoc (`.mypy_cache` is present); scripts carry type hints, so keep new code typed.

## Architecture

Three scripts, two authentication flows — picking the right flow is the main architectural decision when adding a script:

- **Client-credentials flow** (`SpotifyClientCredentials`): used by `search-authors.py` and `get-artist-genre.py`. Read-only access to the public catalog. No browser, no user context.
- **OAuth Authorization Code flow** (`SpotifyOAuth`): used by `create-playlist.py`. Required for anything touching the user's account (reading private playlists, creating/modifying playlists). First run opens a browser; the token is cached in `.cache` (gitignored). Scopes are declared per-script (currently `playlist-modify-private playlist-modify-public`). The redirect URI must exactly match one registered in the Spotify app dashboard and must use `127.0.0.1`, not `localhost`.

Credentials come from `.env` (`SPOTIFY_CLIENT_ID`, `SPOTIFY_SECRET`, optional `SPOTIFY_REDIRECT_URI`) loaded with `python-dotenv`. `.env.example` documents the expected keys.

Conventions established by `create-playlist.py` (follow these in new scripts):

- Progress/log output goes to **stderr**; only machine-usable results (IDs, URLs) go to **stdout**, so output can be piped.
- Spotify batch limits are respected explicitly (100 track URIs per playlist-add request).
- External paginated APIs are fetched defensively: dedupe by ID, cap page counts to avoid infinite loops, over-fetch to compensate for items missing Spotify mappings.
- stats.fm API calls need a browser-like `User-Agent` (the default python-requests UA gets a 403) and use a shared `requests.Session`.

Script filenames use hyphens, so they cannot be imported as modules. If future work needs shared code (auth helpers, genre aggregation), extract it into an underscore-named module (e.g. `spotify_common.py`) rather than importing across hyphenated scripts.

## Planned direction: organizing playlists by aggregated metadata

The next body of work is sorting/organizing the user's many playlists (currently spread across playlist folders) more granularly, based on aggregated per-playlist track metadata — primarily genre.

Key Spotify API constraints that shape this work (verify against current docs before building, but true as of mid-2026):

- **Playlist folders are invisible to the Web API.** There is no endpoint to list, create, or move playlist folders — folders exist only in the Spotify clients. Practical consequence: a script can read/analyze/rename playlists and reorder tracks, and can emit a *recommended* folder organization, but the user must apply folder moves manually in the Spotify app (or via unofficial means, which this repo does not use).
- **Genre is not a track attribute.** Genres live on *artists* (and sometimes albums). Aggregating a playlist's genre means: fetch playlist tracks → collect artist IDs → batch-fetch artists (`spotify.artists()` accepts up to 50 IDs per call) → tally genre frequencies. `get-artist-genre.py` is the single-artist prototype of this.
- **Audio features endpoints are deprecated** (`audio-features`, `audio-analysis`, recommendations, related-artists — restricted for apps since Nov 2024). Do not plan aggregation around danceability/energy/tempo from Spotify; genre + artist popularity + release dates are the reliable metadata.
- Reading the user's own playlists requires OAuth with `playlist-read-private` (and `playlist-read-collaborative` if applicable) — scopes beyond what `create-playlist.py` currently requests, so expect a re-authorization when first adding these.
- Playlist track listings paginate at 100 items (`spotify.playlist_items` with `offset`), and `current_user_playlists` paginates at 50.

A sensible shape for this feature: one script/module that snapshots all user playlists with aggregated genre profiles (cache the results locally — full aggregation is API-call heavy), and a separate step that proposes groupings from that snapshot. Keep analysis (read-only) separated from any mutation, and offer `--dry-run` on anything that writes, following `create-playlist.py`'s pattern.
