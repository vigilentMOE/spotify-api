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
