"""List every track in the user's Liked Songs as one aligned row per track.

Read-only against Spotify. Emits a fixed-width table sized to sit on a single
line in a full-screen text view, readable by a person and by an LLM alike.
"""
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from spotify_common import build_user_client, fetch_artist_genres, log

# Liked Songs live in the user's library, which needs a scope neither
# create-playlist.py nor playlist_snapshot.py requests -- expect a one-time
# re-authorization on first run.
SCOPE = "user-library-read"
DEFAULT_MAX_GENRES = 4

# Column widths chosen so a full row lands near 200 characters: wide enough
# for real track and album names, narrow enough to sit on one line in a
# full-screen text view. GENRES is last and unpadded, so it absorbs the slack.
COLUMNS: Tuple[Tuple[str, int], ...] = (
    ("ADDED", 10),   # YYYY-MM-DD
    ("TRACK", 34),
    ("ARTIST", 24),
    ("ALBUM", 30),
    ("YEAR", 4),
    ("LEN", 5),
    ("POP", 3),
    ("ID", 22),      # Spotify IDs are 22 base62 chars
    ("GENRES", 0),   # 0 = last column, never padded
)
# GENRES is unpadded but still bounded, so a track carrying four long
# subgenres cannot run the row off the screen. 52 caps a full row at exactly
# MAX_ROW_WIDTH; measured against a real 11.5k library, ~1% of rows lose a
# genre to it. `--max-genres 0` lifts the budget for LLM consumption.
GENRES_WIDTH = 52
MAX_ROW_WIDTH = 200
SAVED_PAGE = 50  # Spotify page cap for current_user_saved_tracks
# An 11k-track library is 230+ sequential pages and takes minutes. Report
# progress this often so a slow run is never mistaken for a hung one.
PROGRESS_EVERY = 500
GUTTER = "  "
PREAMBLE = (
    "# genres are artist-level (Spotify has no track genre); "
    "ADDED is when you liked it"
)
HEADER_LINES = 4  # title comment, preamble, column header, rule


def format_duration(duration_ms: Optional[int]) -> str:
    """m:ss. Minutes are not wrapped into hours -- a 62-minute mix reads
    '62:03', which sorts and scans better than '1:02:03' in a fixed column."""
    if not duration_ms:
        return "-"
    total_seconds = round(duration_ms / 1000)
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def release_year(release_date: Optional[str]) -> str:
    """Year from a Spotify release_date, whose precision may be
    year ('1994'), month ('2012-05') or day ('2010-11-22')."""
    if not release_date:
        return "-"
    return release_date.split("-")[0]


def truncate(text: str, width: int) -> str:
    """Clip to `width` columns, marking the clip with a trailing ellipsis."""
    if len(text) <= width:
        return text
    return text[:width - 1] + "…"


def fit_genres(genres: List[str], width: int) -> List[str]:
    """Drop trailing genres until the rendered list fits `width`.

    Whole genres go rather than characters -- a row ending 'boom bap; old
    school hip ho…' reads worse, and parses worse, than one genre fewer.
    The first genre is always kept, clipped only if it alone overflows.
    """
    kept: List[str] = []
    for genre in genres:
        candidate = kept + [genre]
        if len("; ".join(candidate)) > width:
            break
        kept = candidate
    if not kept and genres:
        return [truncate(genres[0], width)]
    return kept


def collect_genres(
    artist_ids: Sequence[str],
    artist_genres: Dict[str, List[str]],
    max_genres: int,
) -> List[str]:
    """The track's genres: the union over its artists, deduped, in the order
    they first appear (so the primary artist's genres lead).

    Spotify has no track-level genre -- genre lives on the artist -- so this
    is the closest thing to a genre tag a single track can carry.
    `max_genres` of 0 means no cap.
    """
    ordered: List[str] = []
    for artist_id in artist_ids:
        for genre in artist_genres.get(artist_id, []):
            if genre not in ordered:
                ordered.append(genre)
    return ordered[:max_genres] if max_genres else ordered


def build_row(
    item: Dict,
    artist_genres: Dict[str, List[str]],
    max_genres: int,
) -> Dict[str, str]:
    """One saved-track item -> its untruncated column values.

    Everything is optional in practice: local files carry no ID, no release
    date and no popularity, so each field falls back to '-' rather than
    dropping the row.
    """
    track = item.get("track") or {}
    album = track.get("album") or {}
    artists = track.get("artists") or []
    genres = collect_genres(
        [a["id"] for a in artists if a.get("id")], artist_genres, max_genres
    )
    if max_genres:  # 0 means "everything", width budget included
        genres = fit_genres(genres, GENRES_WIDTH)
    popularity = track.get("popularity")
    return {
        "ADDED": (item.get("added_at") or "-")[:10],
        "TRACK": track.get("name") or "-",
        "ARTIST": ", ".join(a["name"] for a in artists if a.get("name")) or "-",
        "ALBUM": album.get("name") or "-",
        "YEAR": release_year(album.get("release_date")),
        "LEN": format_duration(track.get("duration_ms")),
        "POP": "-" if popularity is None else str(popularity),
        "ID": track.get("id") or "-",
        "GENRES": "; ".join(genres) or "-",
    }


def render_table(rows: List[Dict[str, str]], generated_at: str) -> List[str]:
    """The finished report: two comment lines, a header, a rule, then one
    padded line per track. Columns line up so the file scans vertically."""
    header = GUTTER.join(
        name.ljust(width) if width else name for name, width in COLUMNS
    ).rstrip()
    lines = [
        f"# Liked Songs — {len(rows)} tracks — generated {generated_at}",
        PREAMBLE,
        header,
        "─" * len(header),
    ]
    for row in rows:
        cells = []
        for name, width in COLUMNS:
            value = row.get(name, "-")
            cells.append(truncate(value, width).ljust(width) if width else value)
        lines.append(GUTTER.join(cells).rstrip())
    return lines


def report_progress(done: int, total: int, unit: str, last: int) -> int:
    """Log a throttled 'done/total' line. Returns the new watermark, so the
    caller only reports every PROGRESS_EVERY items plus the final tally."""
    if done != last and (done - last >= PROGRESS_EVERY or done == total):
        log(f"  … {done}/{total} {unit}")
        return done
    return last


def fetch_saved_tracks(sp, limit: Optional[int] = None) -> List[Dict]:
    """Every item in Liked Songs, most recently liked first (Spotify's order).

    Items whose track is null -- removed from the catalogue -- are dropped,
    since there is nothing left to describe.

    Paging is sequential and the library can be huge, so the total is
    announced from the first response and progress reported as it goes.
    """
    items: List[Dict] = []
    offset = 0
    target: Optional[int] = None
    logged = 0
    while True:
        page_size = SAVED_PAGE
        if limit is not None:
            remaining = limit - len(items)
            if remaining <= 0:
                break
            page_size = min(SAVED_PAGE, remaining)
        page = sp.current_user_saved_tracks(limit=page_size, offset=offset)
        if target is None:
            total = page.get("total", 0)
            target = min(limit, total) if limit is not None else total
            scope = f" Fetching the {target} most recent." if limit else ""
            log(f"Liked Songs: {total} tracks.{scope}")
        got = page.get("items", [])
        items.extend(item for item in got if item and item.get("track"))
        logged = report_progress(len(items), target, "tracks", logged)
        if len(got) < page_size:
            break  # short page means last page
        offset += page_size
    if target:
        report_progress(len(items), target, "tracks", logged)
    return items


def build_report(
    sp,
    limit: Optional[int] = None,
    max_genres: int = DEFAULT_MAX_GENRES,
) -> List[str]:
    """Fetch Liked Songs and render the table. API-heavy; run sparingly."""
    items = fetch_saved_tracks(sp, limit=limit)
    log(f"Fetched {len(items)} liked tracks.")

    artist_ids = {
        artist["id"]
        for item in items
        for artist in (item.get("track") or {}).get("artists", [])
        if artist.get("id")
    }
    log(f"Looking up genres for {len(artist_ids)} artists.")
    logged = 0

    def on_progress(done: int, total: int) -> None:
        nonlocal logged
        logged = report_progress(done, total, "artists", logged)

    artist_genres = fetch_artist_genres(
        sp, sorted(artist_ids), on_progress=on_progress
    )

    rows = [build_row(item, artist_genres, max_genres) for item in items]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return render_table(rows, generated_at=generated_at)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List Liked Songs as one aligned row per track.",
    )
    parser.add_argument(
        "--output", default=None, metavar="FILE",
        help="write the table here and print only the path "
             "(default: the table itself on stdout)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="only the N most recently liked tracks (default: all)",
    )
    parser.add_argument(
        "--max-genres", type=int, default=DEFAULT_MAX_GENRES, metavar="N",
        help="genres per row, 0 for all "
             f"(default: {DEFAULT_MAX_GENRES})",
    )
    args = parser.parse_args()

    sp = build_user_client(SCOPE)
    lines = build_report(sp, limit=args.limit, max_genres=args.max_genres)
    text = "\n".join(lines) + "\n"

    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
        log(f"Wrote {len(lines) - HEADER_LINES} tracks to {args.output}.")
        print(args.output)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
