"""Search the public Spotify catalogue and rank the hits by popularity.

Built for an agent working in this repo: given a phrase like "super smash
brothers soundtrack", it queries the Web API (not the local Liked Songs
dumps), pages through every result Spotify will hand over, and prints the
most popular matches as one aligned row per track.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import liked_songs
from liked_songs import (
    DEFAULT_MAX_GENRES,
    collect_genres,
    fit_genres,
    format_duration,
    release_year,
    truncate,
)
from spotify_common import build_public_client, fetch_artist_genres, log

# Words that describe the *kind* of thing being searched for rather than
# naming it. They rarely appear in a track, album or artist name, so
# requiring them would throw away every real hit.
SEARCH_PAGE = 50  # Spotify's per-page cap for /search
# Spotify rejects limit + offset > 1000, so one query can never surface more
# than 1000 tracks however many there are -- narrow the query to go deeper.
OFFSET_CEILING = 1000
MAX_PAGES = OFFSET_CEILING // SEARCH_PAGE
# Search results are market-scoped; without one, hits can be unplayable.
DEFAULT_MARKET = "US"

STOPWORDS = frozenset({
    "a", "album", "albums", "an", "and", "bgm", "by", "feat", "for", "from",
    "ft", "in", "music", "of", "on", "or", "original", "ost", "score", "song",
    "songs", "soundtrack", "soundtracks", "the", "theme", "themes", "track",
    "tracks", "version", "versions",
})
# Spotify search field filters whose values are free text that shows up in
# the metadata we match against; year:/tag:/isrc:/upc: values do not.
TEXT_FILTERS = frozenset({"track", "artist", "album", "genre"})
FILTER_RE = re.compile(r'(\w+):("[^"]*"|\S+)')
# A query word and a metadata word count as the same word when one is a
# prefix of the other (zelda/zeldas) from PREFIX_MATCH characters up, or when
# one is a short abbreviation of the other: "Super Smash Brothers" has to find
# the catalogue's "Super Smash Bros.", where neither word is the other's
# prefix. The abbreviation rule stays deliberately tight -- a shared stem of
# ABBREV_STEM, a short form of at most ABBREV_MAX characters, and a length gap
# of at least ABBREV_GAP -- so smash/smart and resident/resistance stay apart.
PREFIX_MATCH = 4
ABBREV_STEM = 3
ABBREV_MAX = 5
ABBREV_GAP = 2


def normalize(text: str) -> str:
    """Fold to lowercase alphanumeric words: 'Super Smash Bros.' ->
    'super smash bros'. Non-Latin scripts survive (str.isalnum is unicode
    aware), so Japanese VGM titles still match."""
    folded = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    return " ".join(folded.split())


def query_terms(query: str) -> List[str]:
    """The words a hit has to contain to count as on-target.

    Field filters are unwrapped (`album:"Resident Evil 4"` contributes its
    three words), non-text filters are dropped, and generic music words are
    stripped so they are not treated as requirements.
    """
    text_parts: List[str] = []
    for field, value in FILTER_RE.findall(query):
        if field.lower() in TEXT_FILTERS:
            text_parts.append(value.strip('"'))
    free_text = FILTER_RE.sub(" ", query)
    terms: List[str] = []
    for word in normalize(" ".join([free_text] + text_parts)).split():
        if word not in STOPWORDS and word not in terms:
            terms.append(word)
    return terms


def common_prefix(left: str, right: str) -> str:
    """The characters two words start with in common."""
    shared = 0
    for a, b in zip(left, right):
        if a != b:
            break
        shared += 1
    return left[:shared]


def term_matches(term: str, words: Sequence[str]) -> bool:
    """Does `term` name one of `words`? Exactly, by prefix, or as an
    abbreviation of it."""
    for word in words:
        if word == term:
            return True
        short, long = sorted((word, term), key=len)
        if len(short) >= PREFIX_MATCH and long.startswith(short):
            return True
        stem = common_prefix(short, long)
        if (
            len(stem) >= ABBREV_STEM
            and len(short) <= ABBREV_MAX
            and len(long) - len(short) >= ABBREV_GAP
        ):
            return True
    return False


def track_words(track: Dict) -> List[str]:
    """Everything nameable about a track: its title, album and artists."""
    parts = [track.get("name") or ""]
    parts.append((track.get("album") or {}).get("name") or "")
    parts.extend(a.get("name") or "" for a in track.get("artists") or [])
    return normalize(" ".join(parts)).split()


def relevance(track: Dict, terms: Sequence[str]) -> float:
    """Fraction of the query's terms this track's metadata accounts for.

    A query with no terms of its own (all stopwords) scores everything 1.0,
    which leaves the ranking to popularity alone.
    """
    if not terms:
        return 1.0
    words = track_words(track)
    hits = sum(1 for term in terms if term_matches(term, words))
    return hits / len(terms)


def filter_relevant(
    tracks: Sequence[Dict],
    terms: Sequence[str],
    min_relevance: float = 1.0,
) -> Tuple[List[Dict], List[Dict]]:
    """Split hits into (on-target, off-target).

    Spotify's relevance ranking is loose, so a bare popularity sort promotes
    unrelated tracks that merely share a word with the query. Requiring the
    query's terms to actually appear keeps the ranking honest; the rejects
    are returned rather than discarded so they can be reported.
    """
    kept: List[Dict] = []
    dropped: List[Dict] = []
    for track in tracks:
        target = kept if relevance(track, terms) >= min_relevance else dropped
        target.append(track)
    return kept, dropped


def collapse_versions(tracks: Sequence[Dict]) -> List[Dict]:
    """One row per recording: same title and lead artist means the single,
    the album cut and the compilation re-release are the same song, and only
    the most popular copy is worth ranking."""
    best: Dict[Tuple[str, str], Dict] = {}
    for track in tracks:
        artists = track.get("artists") or []
        lead = normalize(artists[0].get("name") or "") if artists else ""
        key = (normalize(track.get("name") or ""), lead)
        current = best.get(key)
        if current is None or (track.get("popularity") or 0) > (
            current.get("popularity") or 0
        ):
            best[key] = track
    return list(best.values())


def rank_by_popularity(tracks: Sequence[Dict]) -> List[Dict]:
    """Most popular first. Popularity is 0-100, track-level, and the only
    ranking signal Spotify still exposes (audio-features is deprecated);
    title breaks ties so repeated runs agree."""
    return sorted(
        tracks,
        key=lambda t: (-(t.get("popularity") or 0), normalize(t.get("name") or "")),
    )


def search_all_pages(
    sp,
    query: str,
    market: Optional[str] = DEFAULT_MARKET,
    max_pages: int = MAX_PAGES,
) -> List[Dict]:
    """Every track Spotify will return for `query`, deduped by ID.

    Paging stops on a short or empty page, or at the API's 1000-item
    ceiling. The response's `total` is deliberately ignored: it is an
    estimate that routinely understates what paging actually returns (a
    query reporting 485 still served a full page at offset 950), so trusting
    it would cut the result set short.
    """
    found: Dict[str, Dict] = {}
    pages = 0
    for page in range(max_pages):
        offset = page * SEARCH_PAGE
        if offset + SEARCH_PAGE > OFFSET_CEILING:
            log(f"  ! stopping at Spotify's {OFFSET_CEILING}-result ceiling.")
            break
        response = sp.search(
            q=query, type="track", limit=SEARCH_PAGE, offset=offset,
            market=market,
        )
        items = (response.get("tracks") or {}).get("items") or []
        pages += 1
        if not items:
            break
        for track in items:
            # Null entries and local files carry no ID and nothing to rank.
            if track and track.get("id") and track["id"] not in found:
                found[track["id"]] = track
        if len(items) < SEARCH_PAGE:
            break
    log(f"Searched {query!r}: {len(found)} unique tracks over {pages} page(s).")
    return list(found.values())


# Relevance is a blunt instrument, so it is applied in tiers: everything the
# query asked for, then progressively looser, stopping as soon as a tier
# yields a usable number of rows. 0.0 keeps every hit -- the honest answer
# when a query's words appear nowhere in the catalogue's metadata.
RELEVANCE_TIERS = (1.0, 0.75, 0.5, 0.0)
MIN_RESULTS = 5
DEFAULT_LIMIT = 25


def select_relevant(
    tracks: Sequence[Dict],
    terms: Sequence[str],
    min_results: int = MIN_RESULTS,
) -> Tuple[List[Dict], float]:
    """The on-target hits, plus the relevance threshold they were kept at.

    Strict matching first; if it leaves too little to rank, the tightest
    threshold that still finds something wins. The threshold is returned so
    the report can say how loose it had to get.
    """
    fallback: List[Dict] = []
    fallback_threshold = 0.0
    for threshold in RELEVANCE_TIERS:
        kept, _ = filter_relevant(tracks, terms, threshold)
        if len(kept) >= min_results:
            return kept, threshold
        if kept and not fallback:
            fallback, fallback_threshold = kept, threshold
    if fallback:
        return fallback, fallback_threshold
    return list(tracks), 0.0


# Same shape as liked_songs.py's table, minus ADDED (a catalogue hit was
# never "added") and with the freed width given to TRACK and ALBUM, which
# search results fill with "(From \"...\")" suffixes.
COLUMNS: Tuple[Tuple[str, int], ...] = (
    ("TRACK", 40),
    ("ARTIST", 24),
    ("ALBUM", 36),
    ("YEAR", 4),
    ("LEN", 5),
    ("POP", 3),
    ("ID", 22),      # Spotify IDs are 22 base62 chars
    ("GENRES", 0),   # 0 = last column, never padded
)
GENRES_WIDTH = liked_songs.GENRES_WIDTH
MAX_ROW_WIDTH = 200
GUTTER = "  "
HEADER_LINES = 4  # title comment, preamble, column header, rule


def build_row(
    track: Dict,
    artist_genres: Dict[str, List[str]],
    max_genres: int,
) -> Dict[str, str]:
    """One search hit -> its untruncated column values, '-' where Spotify
    has nothing (covers are routinely missing dates, genres and popularity)."""
    album = track.get("album") or {}
    artists = track.get("artists") or []
    genres = collect_genres(
        [a["id"] for a in artists if a.get("id")], artist_genres, max_genres
    )
    if max_genres:  # 0 means "everything", width budget included
        genres = fit_genres(genres, GENRES_WIDTH)
    popularity = track.get("popularity")
    return {
        "TRACK": track.get("name") or "-",
        "ARTIST": ", ".join(a["name"] for a in artists if a.get("name")) or "-",
        "ALBUM": album.get("name") or "-",
        "YEAR": release_year(album.get("release_date")),
        "LEN": format_duration(track.get("duration_ms")),
        "POP": "-" if popularity is None else str(popularity),
        "ID": track.get("id") or "-",
        "GENRES": "; ".join(genres) or "-",
    }


def render_table(
    rows: List[Dict[str, str]],
    query: str,
    hits: int,
    threshold: float,
    generated_at: str,
    columns: Tuple[Tuple[str, int], ...] = COLUMNS,
) -> List[str]:
    """The finished report: title, preamble, header, rule, one row per track."""
    header = GUTTER.join(
        name.ljust(width) if width else name for name, width in columns
    ).rstrip()
    match = (
        "every query term matched" if threshold >= 1.0
        else f"relaxed to {threshold:.0%} of query terms matched"
    )
    notes = ["ranked by Spotify popularity (0-100, track-level)", match]
    if any(name == "GENRES" for name, _ in columns):
        notes.append("genres are artist-level")
    lines = [
        f"# Spotify search — {query!r} — {len(rows)} of {hits} hits — "
        f"generated {generated_at}",
        "# " + "; ".join(notes),
        header,
        "─" * len(header),
    ]
    for row in rows:
        cells = []
        for name, width in columns:
            value = row.get(name, "-")
            cells.append(truncate(value, width).ljust(width) if width else value)
        lines.append(GUTTER.join(cells).rstrip())
    return lines


def as_records(
    tracks: Sequence[Dict],
    artist_genres: Dict[str, List[str]],
    max_genres: int,
) -> List[Dict]:
    """The same ranking as a list of JSON-ready dicts, for piping onward
    (the URI is what create-playlist.py-style writes consume)."""
    records = []
    for rank, track in enumerate(tracks, 1):
        artists = track.get("artists") or []
        album = track.get("album") or {}
        records.append({
            "rank": rank,
            "name": track.get("name"),
            "artists": [a.get("name") for a in artists],
            "album": album.get("name"),
            "release_date": album.get("release_date"),
            "duration_ms": track.get("duration_ms"),
            "popularity": track.get("popularity"),
            "id": track.get("id"),
            "uri": track.get("uri") or f"spotify:track:{track.get('id')}",
            "genres": collect_genres(
                [a["id"] for a in artists if a.get("id")],
                artist_genres,
                max_genres,
            ),
        })
    return records


def gather(
    sp,
    query: str,
    limit: int = DEFAULT_LIMIT,
    market: Optional[str] = DEFAULT_MARKET,
    max_pages: int = MAX_PAGES,
    with_genres: bool = True,
    max_genres: int = DEFAULT_MAX_GENRES,
) -> Tuple[List[Dict], Dict[str, List[str]], float, int]:
    """Search, filter, dedupe, rank, then look up genres for the survivors.

    Returns (ranked tracks, artist-ID -> genres, relevance threshold, hits).
    Genres are fetched last so the artist lookup only covers the rows that
    made the cut -- one batched request instead of twenty.
    """
    hits = search_all_pages(sp, query, market=market, max_pages=max_pages)
    terms = query_terms(query)
    kept, threshold = select_relevant(hits, terms)
    off_target = [t for t in hits if t not in kept]
    if off_target:
        loudest = rank_by_popularity(off_target)[0]
        log(
            f"  {len(off_target)} off-target hit(s) dropped "
            f"(most popular: {loudest.get('name')!r} by "
            f"{(loudest.get('artists') or [{}])[0].get('name')}, "
            f"pop {loudest.get('popularity')})"
        )
    if threshold < 1.0:
        log(
            f"  ! only {threshold:.0%} of query terms matched — "
            "results may be loose; try a narrower query"
        )
    ranked = rank_by_popularity(collapse_versions(kept))[:limit]
    artist_genres: Dict[str, List[str]] = {}
    if with_genres and ranked:
        artist_ids = {
            artist["id"]
            for track in ranked
            for artist in track.get("artists") or []
            if artist.get("id")
        }
        log(f"Looking up genres for {len(artist_ids)} artists.")
        artist_genres = fetch_artist_genres(sp, sorted(artist_ids))
    return ranked, artist_genres, threshold, len(hits)


def build_report(
    sp,
    query: str,
    limit: int = DEFAULT_LIMIT,
    market: Optional[str] = DEFAULT_MARKET,
    max_pages: int = MAX_PAGES,
    max_genres: int = DEFAULT_MAX_GENRES,
    with_genres: bool = True,
) -> List[str]:
    """The whole pipeline, rendered as the table's lines."""
    ranked, artist_genres, threshold, hits = gather(
        sp, query, limit=limit, market=market, max_pages=max_pages,
        with_genres=with_genres, max_genres=max_genres,
    )
    rows = [build_row(track, artist_genres, max_genres) for track in ranked]
    columns = COLUMNS if with_genres else tuple(
        column for column in COLUMNS if column[0] != "GENRES"
    )
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return render_table(
        rows, query, hits, threshold, generated_at, columns=columns
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search Spotify's catalogue and rank the hits by "
                    "popularity. Read-only; no OAuth, no user library.",
    )
    parser.add_argument(
        "query", nargs="+", metavar="QUERY",
        help='what to search for, e.g. super smash brothers soundtrack. '
             'Spotify field filters work too: album:"Resident Evil 4", '
             'artist:"Capcom Sound Team", year:2005',
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, metavar="N",
        help=f"rows to report (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--market", default=DEFAULT_MARKET, metavar="CC",
        help="ISO country code scoping availability, empty for none "
             f"(default: {DEFAULT_MARKET})",
    )
    parser.add_argument(
        "--max-pages", type=int, default=MAX_PAGES, metavar="N",
        help=f"pages of {SEARCH_PAGE} to fetch, capped by Spotify's "
             f"{OFFSET_CEILING}-result ceiling (default: {MAX_PAGES})",
    )
    parser.add_argument(
        "--max-genres", type=int, default=DEFAULT_MAX_GENRES, metavar="N",
        help=f"genres per row, 0 for all (default: {DEFAULT_MAX_GENRES})",
    )
    parser.add_argument(
        "--no-genres", action="store_true",
        help="skip the artist-genre lookup and its column (one fewer "
             "request; search hits often carry no genres anyway)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit JSON records (name, artists, popularity, id, uri, genres) "
             "instead of the table",
    )
    parser.add_argument(
        "--output", default=None, metavar="FILE",
        help="write the results here and print only the path "
             "(default: the results themselves on stdout)",
    )
    args = parser.parse_args()

    query = " ".join(args.query)
    sp = build_public_client()
    common = dict(
        limit=args.limit,
        market=args.market or None,
        max_pages=args.max_pages,
        max_genres=args.max_genres,
        with_genres=not args.no_genres,
    )
    if args.json:
        ranked, artist_genres, _, _ = gather(sp, query, **common)
        text = json.dumps(
            as_records(ranked, artist_genres, args.max_genres),
            indent=2, ensure_ascii=False,
        ) + "\n"
        count = len(ranked)
    else:
        lines = build_report(sp, query, **common)
        text = "\n".join(lines) + "\n"
        count = len(lines) - HEADER_LINES

    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
        log(f"Wrote {count} tracks to {args.output}.")
        print(args.output)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
