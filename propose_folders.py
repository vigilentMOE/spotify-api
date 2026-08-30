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
from typing import Dict, List, Optional, Tuple

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
