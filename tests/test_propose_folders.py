import propose_folders


def test_classify_genre_matches_keyword_substring():
    assert propose_folders.classify_genre("progressive metalcore") == "Metal"
    assert propose_folders.classify_genre("Deep House") == "Electronic"
    assert propose_folders.classify_genre("gregorian chant") is None


def test_classify_genre_order_specific_before_broad():
    # 'pop punk' contains both 'punk' and 'pop'; the punk family is first.
    assert propose_folders.classify_genre("pop punk") == "Punk / Emo / Hardcore"
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


def _snapshot(playlists):
    return {
        "generated_at": "2026-08-30T12:00:00+00:00",
        "user_id": "testuser",
        "unmatched_names": [],
        "playlists": playlists,
    }


def _pl(pid, name, genre_counts, source_folder="NICHE MIXES"):
    return {
        "id": pid,
        "name": name,
        "source_folder": source_folder,
        "total_tracks": sum(genre_counts.values()) or 1,
        "tracks_with_artists": sum(genre_counts.values()) or 1,
        "genre_counts": genre_counts,
    }


def test_propose_groups_by_source_folder_then_family():
    snapshot = _snapshot([
        _pl("p1", "Heavy Stuff", {"death metal": 9, "pop": 1}),
        _pl("p2", "Beach Vibes", {"indie pop": 8, "dance pop": 4}),
        _pl("p3", "Nangs Radio", {"psychedelic rock": 5}, source_folder="RADIO LAUNCHPAD"),
    ])
    groups = propose_folders.propose(snapshot)
    assert list(groups) == ["NICHE MIXES", "RADIO LAUNCHPAD"]
    assert list(groups["NICHE MIXES"]) == ["Metal", "Pop"]
    assert groups["NICHE MIXES"]["Metal"][0]["name"] == "Heavy Stuff"
    assert groups["NICHE MIXES"]["Metal"][0]["coverage"] == 0.9
    assert groups["RADIO LAUNCHPAD"]["Rock"][0]["name"] == "Nangs Radio"


def test_propose_low_coverage_goes_to_mixed():
    snapshot = _snapshot([
        _pl("p1", "Everything", {"rock": 3, "hip hop": 3, "jazz": 3}),
    ])
    groups = propose_folders.propose(snapshot, min_coverage=0.5)
    assert list(groups["NICHE MIXES"]) == [propose_folders.MIXED_FOLDER]


def test_propose_no_genre_data_goes_to_unclassified():
    snapshot = _snapshot([_pl("p1", "Local Files", {})])
    groups = propose_folders.propose(snapshot)
    assert list(groups["NICHE MIXES"]) == [propose_folders.UNKNOWN_FOLDER]
    assert groups["NICHE MIXES"][propose_folders.UNKNOWN_FOLDER][0]["coverage"] == 0.0


def test_propose_handles_ungrouped_playlists():
    snapshot = _snapshot([_pl("p1", "Loose", {"death metal": 2}, source_folder=None)])
    groups = propose_folders.propose(snapshot)
    assert list(groups) == ["(no folder)"]


def test_render_report_contains_folders_and_playlists():
    snapshot = _snapshot([
        _pl("p1", "Heavy Stuff", {"death metal": 9, "pop": 1}),
    ])
    report = propose_folders.render_report(
        propose_folders.propose(snapshot), snapshot["generated_at"]
    )
    assert "# NICHE MIXES" in report
    assert "## Metal (1 playlist" in report
    assert "Heavy Stuff" in report
    assert "90%" in report
    assert "death metal" in report


def test_propose_folds_small_buckets_into_misc():
    # A one-playlist subfolder is not worth creating; min_size merges it.
    snapshot = _snapshot([
        _pl("p1", "A", {"death metal": 5}),
        _pl("p2", "B", {"death metal": 5}),
        _pl("p3", "C", {"death metal": 5}),
        _pl("p4", "D", {"bossa nova": 5}),
    ])
    groups = propose_folders.propose(snapshot, min_size=3)
    assert list(groups["NICHE MIXES"]) == ["Metal", propose_folders.MISC_FOLDER]
    assert [e["name"] for e in groups["NICHE MIXES"][propose_folders.MISC_FOLDER]] == ["D"]


def test_propose_min_size_one_keeps_every_bucket():
    snapshot = _snapshot([
        _pl("p1", "A", {"death metal": 5}),
        _pl("p2", "D", {"bossa nova": 5}),
    ])
    groups = propose_folders.propose(snapshot, min_size=1)
    assert list(groups["NICHE MIXES"]) == ["Metal", "Jazz / Blues"]
