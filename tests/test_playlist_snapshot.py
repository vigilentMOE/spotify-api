import playlist_snapshot


def test_chunked_splits_into_batches():
    assert list(playlist_snapshot.chunked(["a", "b", "c", "d", "e"], 2)) == [
        ["a", "b"], ["c", "d"], ["e"],
    ]


def test_chunked_empty_sequence_yields_nothing():
    assert list(playlist_snapshot.chunked([], 10)) == []


def test_aggregate_genres_counts_tracks_per_genre():
    track_artist_ids = [["a1"], ["a2"], ["a1", "a2"]]
    artist_genres = {"a1": ["rock"], "a2": ["rock", "pop"]}
    counts = playlist_snapshot.aggregate_genres(track_artist_ids, artist_genres)
    # rock: all 3 tracks; pop: the two tracks featuring a2.
    assert counts == {"rock": 3, "pop": 2}


def test_aggregate_genres_track_counts_shared_genre_once():
    # Two artists on one track sharing a genre must not double-count it.
    track_artist_ids = [["a1", "a2"]]
    artist_genres = {"a1": ["metal"], "a2": ["metal"]}
    assert playlist_snapshot.aggregate_genres(track_artist_ids, artist_genres) == {
        "metal": 1,
    }


def test_aggregate_genres_unknown_artist_ignored():
    track_artist_ids = [["a1", "missing"]]
    artist_genres = {"a1": ["jazz"]}
    assert playlist_snapshot.aggregate_genres(track_artist_ids, artist_genres) == {
        "jazz": 1,
    }
