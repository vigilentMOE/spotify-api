# Spotify API Tools

This project provides tools to interact with the Spotify API, allowing users to search for artists and retrieve their genres.

## Features

- **Search Artists**: Search for artists by name and display their details (such as artist ID) in a tabulated format.
- **Get Artist Genres**: Retrieve and display the genres associated with a specific artist. Requires artist ID
- **Create Playlist from stats.fm**: Read a public [stats.fm](https://stats.fm) profile and build a Spotify playlist of that user's top tracks in *your* account.
- **List Liked Songs**: Dump your entire Liked Songs library to a fixed-width table — one aligned row per track, with genre tags — readable by you and by an LLM.

## Requirements

- Python 3.6+
- Spotipy
- Python-dotenv
- Tabulate

## Setup

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/spotify-api-tools.git
    cd spotify-api-tools
    ```

2. Create a virtual environment and activate it:
    ```sh
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```

3. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```

4. Create a `.env` file in the root directory and add your Spotify API credentials:
    ```env
    SPOTIFY_CLIENT_ID="your_client_id"
    SPOTIFY_SECRET="your_client_secret"
    ```

## Usage

### Search Artists

Run the `search-authors.py` script to search for artists by name and get their ID:

```sh
python search-authors.py
```

#### Example Usage

```sh
python search-authors.py                                                                                                                                                                ─╯
Spotify Artist Search Tool
-------------------------

Enter artist name to search (or 'q' to quit): Taylor Swift
+-----+----------------------------------------+------------------------+-------------+--------------+
|   # | Artist Name                            | Artist ID              | Followers   |   Popularity |
+=====+========================================+========================+=============+==============+
|   1 | Taylor Swift                           | 06HL4z0CvFAxyc27GXpf02 | 126,340,960 |          100 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   2 | Salish Matter                          | 4CB8mmEbDXVxkzNpJgkj65 | 243,719     |           34 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   3 | Taylor Swift Piano Covers              | 0DwbGCdaD8YLRiVUEiV70Q | 3,970       |           33 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   4 | Olivia Rodrigo                         | 1McMsnEElThX1knmY4oliG | 41,413,747  |           89 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   5 | Taylor Swift - Evermore - Piano Covers | 3vZoN5cnYOycsJ5KsFkjo5 | 200         |            5 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   6 | Tate McRae                             | 45dkTj5sMRSjrmBSBeiHym | 6,234,266   |           86 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   7 | taylorr swiftt                         | 7oW3aIseIypoEqcOqvzUfS | 126         |            7 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   8 | Kidz Bop Kids                          | 1Vvvx45Apu6dQqwuZQxtgW | 1,268,993   |           68 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   9 | Brandon Taylor Smith                   | 0CkM1sLkP3yQW8I7ja51am | 95          |           35 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|  10 | Adele                                  | 4dpARuHxo51G3z768sgnrY | 60,292,280  |           87 |
+-----+----------------------------------------+------------------------+-------------+--------------+
```

### Get Artist Genres

Use IDs from `search-authors.py` as input to this script

```sh
# Provide desired artist ID
python get-artist-genre.py
```

#### Example Usage

```sh
python get-artist-genre.py                                                                                                                                                              ─╯
Spotify Artist Genre Lookup
-------------------------

Enter Spotify Artist ID (or 'q' to quit): 06HL4z0CvFAxyc27GXpf02

Artist: Taylor Swift
+-----+---------+
|   # | Genre   |
+=====+=========+
|   1 | pop     |
+-----+---------+
```

### Create Playlist from a stats.fm profile

`create-playlist.py` reads a **public** stats.fm profile (no auth) and creates a
playlist in your own Spotify account from that user's top tracks.

Because writing to your account requires user authorization, this script uses the
OAuth Authorization Code flow (not the client-credentials flow the other scripts
use). One-time setup:

1. In the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard),
   open your app and add a Redirect URI that matches `SPOTIFY_REDIRECT_URI`
   (default `http://127.0.0.1:8888/callback`).
2. Ensure your `.env` has `SPOTIFY_CLIENT_ID`, `SPOTIFY_SECRET`, and optionally
   `SPOTIFY_REDIRECT_URI`.

The first run opens a browser to authorize; the token is cached locally for
subsequent runs.

```sh
# Create a playlist of 200 all-time top tracks (default), private:
python create-playlist.py https://stats.fm/chamerence/tracks

# A bare username also works, plus options:
python create-playlist.py chamerence --limit 200 --range lifetime --public --name "Chamerence All-Time"

# Preview which tracks would be added without touching Spotify:
python create-playlist.py chamerence --dry-run
```

Options:

| Flag | Default | Description |
| --- | --- | --- |
| `--limit` | `200` | Number of top tracks to add |
| `--range` | `lifetime` | `weeks`, `months`, or `lifetime` (all time) |
| `--name` | auto | Playlist name |
| `--public` | off (private) | Make the playlist public |
| `--dry-run` | off | Print track IDs only; don't create a playlist |

Notes: only public profiles work (stats.fm lets users hide top tracks); tracks
in the stats.fm catalog with no Spotify match are skipped, so the script
over-fetches to still reach your requested count. The created playlist's URL is
printed to stdout on success.
### List Liked Songs

Dumps every track in your **Liked Songs** to a fixed-width table: one row per
track, columns aligned so the file scans vertically in a full-screen text view.
Rows land under ~190 characters.

```sh
# Straight to the terminal (or a pipe):
python liked_songs.py

# To a file, which prints only the path on stdout:
python liked_songs.py --output liked_songs.txt

# A quick look at your 20 most recent likes, all genres shown:
python liked_songs.py --limit 20 --max-genres 0
```

```text
# Liked Songs — 1847 tracks — generated 2026-09-12T12:21Z
# genres are artist-level (Spotify has no track genre); ADDED is when you liked it
ADDED       TRACK                               ARTIST                    ALBUM                           YEAR  LEN    POP  ID                      GENRES
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
2024-03-11  Runaway                             Kanye West                My Beautiful Dark Twisted Fan…  2010  9:08   78   4Ye8jGrfoshkKZUM6s2Sa4  hip hop; rap; chicago rap
2019-07-02  Weightless                          Marconi Union             Weightless                      2012  8:10   41   2ZlKh1kMJptDvbPWNK5Y5V  ambient; drone; sleep
2021-12-25  Black Hole Sun                      Soundgarden               Superunknown                    1994  5:20   72   2EoOZnxNgtmZaD8uUmz2nD  grunge; alternative metal; rock
```

| Flag | Default | Description |
| --- | --- | --- |
| `--output` | *(stdout)* | Write the table to this file and print only the path |
| `--limit` | *(all)* | Only the N most recently liked tracks |
| `--max-genres` | `4` | Genres per row; `0` shows every one |

Notes: **GENRES is artist-level** — Spotify has no track genre, so a track's
tags are the union of its artists' genres, deduped, primary artist first.
Fields too long for their column are cut with `…`; the untruncated values are
still in Spotify. Local files and tracks pulled from the catalogue show `-`
for whatever metadata is missing. This is the first script to need the
`user-library-read` scope, so the first run re-opens the browser to authorize.

### Sort playlist folders by genre

Two steps: build a snapshot with per-playlist genre data, then generate a
proposed folder organization from it.

**Important:** the Spotify Web API cannot see, create, or move playlist
folders — folders exist only in the Spotify clients. The output is a report
you apply by hand in the app.

For your own playlists, snapshot straight from the API:

```sh
# Whole library:
python playlist_snapshot.py

# Or restrict to named folders (folders.json maps folder -> playlist names):
python playlist_snapshot.py --folders folders.json --folder "NICHE MIXES"
```

Spotify's personalised **"<Genre> Mix"** and **"<Song> Radio"** playlists are
invisible to the Web API — they never appear in `current_user_playlists` and
can't be found by search, so their tracks can't be read. For those, transcribe
the folder contents into `folder_inventory.json` and classify them without
reading tracks:

```sh
# '<Genre> Mix' -> genre from the name; '<Song> Radio' -> genre of the seed
# track's artists, looked up via search.
python folder_inventory.py --inventory folder_inventory.json

# Name-only, no Spotify calls at all:
python folder_inventory.py --no-api
```

Either way, the snapshot feeds the same report generator:

```sh
python propose_folders.py --min-size 3 > PROPOSED_FOLDERS.md
```

| Flag | Default | Description |
| --- | --- | --- |
| `--snapshot` | `snapshot.json` | Snapshot file to read |
| `--min-size` | `3` | Families smaller than this fold into one Misc bucket |
| `--min-coverage` | `0.5` | Dominant-family share below which a playlist is "Mixed" |

Run the tests with `pytest`.
