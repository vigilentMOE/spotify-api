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
    ("Slowed / Reverb", ("slowed", "reverb", "sped up", "super slow")),
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
    ("Anime / J-Music / City Pop", (
        "anime", "otacore", "j-rock", "j-pop", "jpop", "city pop", "doujin",
        "japanese", "korean", "k-pop", "kpop", "cowboy bebop",
    )),
    ("Hip-Hop / Rap", (
        "hip hop", "hip-hop", "rap", "drill", "grime", "boom bap",
    )),
    # Before Rock so 'Indie Soul' and 'Indie R&B' keep their real genre.
    ("R&B / Soul / Funk", (
        "r&b", "soul", "funk", "motown", "new jack swing",
    )),
    ("Jazz / Blues", (
        "jazz", "bebop", "bossa nova", "swing", "big band", "blues",
    )),
    ("Rock", (
        "rock", "grunge", "britpop", "psychedelic", "bubblegrunge",
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
    # Mood and activity families. Ranked below every genre family, so a name
    # carrying a real genre ('Chill Jazz Mix') is filed by genre and only
    # mood-only names ('Bed Rotting Mix') land here. Many of this library's
    # playlists are named for a mood or an activity, not a genre.
    ("Workout / Hype", (
        "workout", "running", "hype", "gym", "weightlifting", "adrenaline",
        "pump up", "aggressive", "angry", "motivation", "energetic", "energy",
        "intense", "fast", "amped", "grind time",
    )),
    ("Focus / Study", (
        "focus", "study", "homework", "concentration", "productivity",
        "creative", "work",
    )),
    ("Romantic / Love", (
        "romantic", "love", "intimate", "relationship", "yearning", "cozy",
        "crush",
    )),
    ("Dark / Horror / Suspense", (
        "horror", "eerie", "spooky", "suspense", "dark", "gloomy",
        "apocalyptic", "vampire", "lovecraftian", "dungeon synth",
        "mysterious", "dread", "creepy", "sinister", "fantasy",
    )),
    ("Sad / Melancholy", (
        "sad", "melancholy", "crying", "lonely", "moody", "dissociation",
        "escapism", "bed rotting", "angst", "somber", "heartbreak",
        "depress", "tortured",
    )),
    ("Feel Good / Uplifting", (
        "feel good", "good vibes", "happy", "hopecore", "uplifting",
        "comforting", "groovy", "fun", "wholesome",
    )),
    ("Morning / Daytime", (
        "morning", "wake up", "breakfast", "sunday", "afternoon", "daytime",
        "coffee",
    )),
    ("Night / Late Night", ("night", "midnight", "evening", "nocturne")),
    ("Chores / Everyday", (
        "cooking", "baking", "walking", "driving", "cleaning", "elevator",
        "commute", "shower", "chores",
    )),
    ("Seasonal / Holiday", (
        "christmas", "halloween", "summer", "winter", "autumn", "spring",
        "holiday",
    )),
    ("Ambient / Chill", (
        "ambient", "chill", "calm", "sleep", "meditation", "new age",
        "downtempo", "quiet", "peaceful", "liminal", "drone", "atmospheric",
        "gentle", "soft", "relaxing", "background", "mellow", "serenity",
    )),
    # Broadest last: many micro-genres end in 'pop' ('art pop', 'indie pop').
    ("Pop", ("pop", "boy band", "girl group", "idol")),
    # After Pop so 'indie pop' files as Pop; catches bare 'indie'/'alt' names.
    ("Indie / Alternative", ("indie", "alternative")),
]

MIXED_FOLDER = "Mixed / Low Confidence"
UNKNOWN_FOLDER = "Unclassified"
MISC_FOLDER = "Misc (too few to split out)"


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
    snapshot: Dict, min_coverage: float = 0.5, min_size: int = 1
) -> Dict[str, Dict[str, List[Dict]]]:
    """Group playlists by source folder, then by dominant genre family.

    The result is the proposed structure: one subfolder per genre family
    inside each existing top-level folder. Families with fewer than
    `min_size` playlists are folded into a single Misc bucket, since a
    subfolder holding one playlist isn't worth creating.
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
        misc: List[Dict] = []
        kept: Dict[str, List[Dict]] = {}
        for bucket in bucket_order:
            entries = buckets.get(bucket)
            if not entries:
                continue
            # Mixed and Unclassified are already catch-alls; never fold them.
            if len(entries) < min_size and bucket not in (
                MIXED_FOLDER, UNKNOWN_FOLDER
            ):
                misc.extend(entries)
            else:
                kept[bucket] = entries
        if misc:
            kept[MISC_FOLDER] = misc

        ordered[source] = {
            bucket: sorted(entries, key=lambda e: (-e["coverage"], e["name"]))
            for bucket, entries in kept.items()
        }
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
        "--min-size", type=int, default=3,
        help="fold families with fewer than this many playlists into Misc "
             "(default: 3; use 1 to keep every family)",
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

    groups = propose(
        snapshot, min_coverage=args.min_coverage, min_size=args.min_size
    )
    log(f"Grouped {len(snapshot['playlists'])} playlists into "
        f"{sum(len(b) for b in groups.values())} proposed subfolder(s).")
    print(render_report(groups, snapshot.get("generated_at", "unknown")))


if __name__ == "__main__":
    main()
