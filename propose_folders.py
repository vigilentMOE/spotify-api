"""Propose a granular playlist folder organization.

Pure local analysis - no Spotify calls. The Web API cannot create or move
playlist folders, so the output is a report the user applies manually in
the Spotify app.

Spotify genres are micro-genres ('progressive metalcore', 'art pop'), so
they are folded into families by ordered keyword matching. Order matters:
the first family whose keyword appears in the string wins, so specific
families (Vaporwave, Breakcore, Metal) come before broad ones (Rock, Pop).

The same matcher runs over two kinds of input:
  - genre strings aggregated from an artist's Spotify genres, and
  - playlist names, for Spotify's algorithmic "<Genre> Mix" playlists,
    whose names carry the genre but whose tracks the API will not serve.
"""
import argparse
import json
from typing import Dict, List, Optional, Tuple

from spotify_common import log

GENRE_FAMILIES: List[Tuple[str, Tuple[str, ...]]] = [
    ("Vaporwave / Synthwave", (
        "vaporwave", "synthwave", "retrowave", "chillwave", "mallsoft",
        "future funk", "vaportrap", "trillwave", "cyberpunk",
    )),
    ("Lo-Fi / Chillhop", (
        "lo-fi", "lofi", "chillhop", "jazzhop", "jazz hop", "jazz hip hop",
        "trip hop", "trip-hop",
    )),
    ("Breakcore / Jungle / DnB", (
        "breakcore", "jungle", "drum and bass", "dnb", "lolicore",
        "dariacore", "glitchcore", "sigilkore", "nightcore", "hardstyle",
        "gabber", "weirdcore",
    )),
    ("Phonk / Trap", ("phonk", "trap", "drift", "rage")),
    ("Metal", (
        "metal", "deathcore", "djent", "grindcore", "blackgaze", "sabbath",
    )),
    ("Punk / Emo / Hardcore", (
        "punk", "hardcore", "emo", "screamo", "ska", "angst",
    )),
    ("Shoegaze / Dream Pop", ("shoegaze", "dream pop", "dreamo")),
    ("Rock", (
        "rock", "grunge", "britpop", "psychedelic", "bubblegrunge",
    )),
    ("Anime / J-Music / City Pop", (
        "anime", "otacore", "j-rock", "j-pop", "jpop", "city pop", "doujin",
        "japanese", "korean", "k-pop", "kpop", "cowboy bebop",
    )),
    ("Hip-Hop / Rap", (
        "hip hop", "hip-hop", "rap", "drill", "grime", "boom bap",
    )),
    ("R&B / Soul / Funk", (
        "r&b", "soul", "funk", "motown", "new jack swing",
    )),
    ("Jazz / Blues", (
        "jazz", "bebop", "bossa nova", "swing", "big band", "blues",
    )),
    ("Electronic", (
        "electronic", "edm", "house", "techno", "trance", "dubstep",
        "garage", "electro", "idm", "breakbeat", "big beat", "rave",
        "jersey club", "plunderphonics", "industrial",
    )),
    ("Classical / Orchestral", (
        "classical", "orchestra", "orchestral", "baroque", "opera",
        "symphony", "piano",
    )),
    ("Soundtrack / Score", (
        "soundtrack", "score", "film", "movie", "video game", "cinematic",
        "television", "noir",
    )),
    ("Country / Folk", (
        "country", "folk", "americana", "bluegrass", "singer-songwriter",
        "cottagecore",
    )),
    ("Latin", (
        "latin", "reggaeton", "salsa", "bachata", "corrido", "cumbia",
        "mariachi", "brazilian",
    )),
    ("Ambient / Chill", (
        "ambient", "chill", "calm", "sleep", "meditation", "new age",
        "downtempo", "quiet", "peaceful", "liminal", "drone", "somber",
        "gentle", "soft", "relaxing", "background",
    )),
    # Broadest last: many micro-genres end in 'pop' ('art pop', 'indie pop').
    ("Pop", ("pop", "boy band", "girl group", "idol")),
]

MIXED_FOLDER = "Mixed / Low Confidence"
UNKNOWN_FOLDER = "Unclassified"


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


NO_FOLDER = "(no folder)"


def propose(
    snapshot: Dict, min_coverage: float = 0.5
) -> Dict[str, Dict[str, List[Dict]]]:
    """Group playlists by source folder, then by dominant genre family.

    The result is the proposed structure: one subfolder per genre family
    inside each existing top-level folder.
    """
    family_order = [name for name, _ in GENRE_FAMILIES]
    bucket_order = family_order + [MIXED_FOLDER, UNKNOWN_FOLDER]
    groups: Dict[str, Dict[str, List[Dict]]] = {}

    for playlist in snapshot["playlists"]:
        counts = playlist["genre_counts"]
        family, coverage = dominant_family(counts)
        if family is None:
            bucket = UNKNOWN_FOLDER
        elif coverage < min_coverage:
            bucket = MIXED_FOLDER
        else:
            bucket = family

        source = playlist.get("source_folder") or NO_FOLDER
        folder = groups.setdefault(source, {})
        folder.setdefault(bucket, []).append(
            {
                "name": playlist["name"],
                "id": playlist["id"],
                "coverage": coverage,
                "top_genres": sorted(
                    counts, key=lambda g: counts[g], reverse=True
                )[:3],
            }
        )

    # Order buckets by the family taxonomy, and playlists by confidence.
    ordered: Dict[str, Dict[str, List[Dict]]] = {}
    for source in sorted(groups):
        buckets = groups[source]
        ordered[source] = {}
        for bucket in bucket_order:
            if bucket in buckets:
                ordered[source][bucket] = sorted(
                    buckets[bucket], key=lambda e: (-e["coverage"], e["name"])
                )
    return ordered


def render_report(
    groups: Dict[str, Dict[str, List[Dict]]], generated_at: str
) -> str:
    total = sum(
        len(entries)
        for folder in groups.values()
        for entries in folder.values()
    )
    lines = [
        "# Proposed playlist folders",
        "",
        f"Snapshot taken: {generated_at}",
        f"{total} playlists across {len(groups)} existing folder(s).",
        "",
        "The Spotify API cannot create or move folders. Apply these groupings",
        "manually in the Spotify app by dragging playlists into subfolders.",
        "",
    ]
    for source, buckets in groups.items():
        lines.append(f"# {source}")
        lines.append("")
        for bucket, entries in buckets.items():
            plural = "playlist" if len(entries) == 1 else "playlists"
            lines.append(f"## {bucket} ({len(entries)} {plural})")
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
        f"{sum(len(b) for b in groups.values())} proposed subfolder(s).")
    print(render_report(groups, snapshot.get("generated_at", "unknown")))


if __name__ == "__main__":
    main()
