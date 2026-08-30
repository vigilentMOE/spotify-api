import playlist_snapshot
from tests.fakes import FakeSpotify


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


def _playlist(i):
    return {"id": f"pl{i}", "name": f"Playlist {i}", "tracks": {"total": 1}}


def _track_item(artist_ids):
    return {"track": {"artists": [{"id": a} for a in artist_ids]}}


def test_fetch_all_playlists_paginates_past_one_page():
    playlists = [_playlist(i) for i in range(75)]  # PLAYLIST_PAGE is 50
    sp = FakeSpotify(playlists=playlists)
    result = playlist_snapshot.fetch_all_playlists(sp)
    assert len(result) == 75
    assert result[0]["id"] == "pl0"
    assert result[74]["id"] == "pl74"


def test_fetch_track_artist_ids_paginates_and_skips_artistless():
    items = [_track_item(["a1"]) for _ in range(150)]  # TRACK_PAGE is 100
    items.append({"track": None})                        # removed/unavailable
    items.append({"track": {"artists": [{"id": None}]}})  # local file
    sp = FakeSpotify(tracks_by_playlist={"pl0": items})
    result = playlist_snapshot.fetch_track_artist_ids(sp, "pl0")
    assert result == [["a1"]] * 150


def test_fetch_track_artist_ids_returns_empty_for_unreadable_playlist():
    # Spotify's algorithmic "Made for you" mixes 404 via the Web API; a
    # single unreadable playlist must not abort the whole snapshot.
    sp = FakeSpotify(unreadable_playlists=["pl0"])
    assert playlist_snapshot.fetch_track_artist_ids(sp, "pl0") == []


def test_fetch_artist_genres_batches_and_dedupes():
    artists = {f"a{i}": ["rock"] for i in range(60)}
    sp = FakeSpotify(artists_by_id=artists)
    ids = list(artists) + list(artists)  # duplicates must collapse
    result = playlist_snapshot.fetch_artist_genres(sp, ids)
    assert result == artists
    assert all(len(call) <= 50 for call in sp.artists_calls)  # ARTIST_BATCH
    assert sum(len(call) for call in sp.artists_calls) == 60


def test_normalize_name_collapses_case_and_whitespace():
    assert playlist_snapshot.normalize_name("  Dark   Moody Mix ") == (
        playlist_snapshot.normalize_name("dark moody mix")
    )


def test_select_playlists_matches_names_and_tags_folder():
    playlists = [
        {"id": "p1", "name": "Dark Moody Mix"},
        {"id": "p2", "name": "Horrorcore Mix"},
        {"id": "p3", "name": "Unrelated Playlist"},
    ]
    folder_map = {"NICHE MIXES": ["dark moody mix"], "RADIO LAUNCHPAD": ["Horrorcore Mix"]}
    selected, unmatched = playlist_snapshot.select_playlists(playlists, folder_map)
    assert unmatched == []
    assert [(p["id"], p["source_folder"]) for p in selected] == [
        ("p1", "NICHE MIXES"),
        ("p2", "RADIO LAUNCHPAD"),
    ]


def test_select_playlists_prefix_matches_truncated_name():
    # Screenshot labels are truncated ("Dungeon Synth ..."), so a trailing
    # ellipsis must still resolve to the real playlist.
    playlists = [{"id": "p1", "name": "Dungeon Synth Mix"}]
    selected, unmatched = playlist_snapshot.select_playlists(
        playlists, {"NICHE MIXES": ["Dungeon Synth ..."]}
    )
    assert unmatched == []
    assert selected[0]["id"] == "p1"


def test_select_playlists_reports_unmatched_names():
    playlists = [{"id": "p1", "name": "Dark Moody Mix"}]
    selected, unmatched = playlist_snapshot.select_playlists(
        playlists, {"NICHE MIXES": ["Nonexistent Mix"]}
    )
    assert selected == []
    assert unmatched == ["NICHE MIXES: Nonexistent Mix"]


def test_select_playlists_does_not_duplicate_a_playlist():
    playlists = [{"id": "p1", "name": "Dark Moody Mix"}]
    selected, _ = playlist_snapshot.select_playlists(
        playlists, {"A": ["Dark Moody Mix"], "B": ["Dark Moody Mix"]}
    )
    assert len(selected) == 1
    assert selected[0]["source_folder"] == "A"  # first folder wins


def test_build_snapshot_aggregates_each_playlist():
    playlists = [
        {"id": "pl0", "name": "Rock Mix", "tracks": {"total": 2}},
        {"id": "pl1", "name": "Empty", "tracks": {"total": 0}},
    ]
    tracks = {
        "pl0": [_track_item(["a1"]), _track_item(["a2"])],
        "pl1": [],
    }
    artists = {"a1": ["rock"], "a2": ["rock", "pop"]}
    sp = FakeSpotify(
        playlists=playlists, tracks_by_playlist=tracks, artists_by_id=artists
    )

    snapshot = playlist_snapshot.build_snapshot(sp)

    assert snapshot["user_id"] == "testuser"
    assert "generated_at" in snapshot
    assert len(snapshot["playlists"]) == 2
    rock_mix = snapshot["playlists"][0]
    assert rock_mix == {
        "id": "pl0",
        "name": "Rock Mix",
        "source_folder": None,
        "total_tracks": 2,
        "tracks_with_artists": 2,
        "genre_counts": {"rock": 2, "pop": 1},
    }
    assert snapshot["playlists"][1]["genre_counts"] == {}


def test_build_snapshot_restricts_to_folder_map():
    playlists = [
        {"id": "pl0", "name": "Rock Mix", "tracks": {"total": 1}},
        {"id": "pl1", "name": "Other Mix", "tracks": {"total": 1}},
    ]
    tracks = {"pl0": [_track_item(["a1"])], "pl1": [_track_item(["a2"])]}
    sp = FakeSpotify(
        playlists=playlists,
        tracks_by_playlist=tracks,
        artists_by_id={"a1": ["rock"], "a2": ["pop"]},
    )

    snapshot = playlist_snapshot.build_snapshot(
        sp, folder_map={"NICHE MIXES": ["Rock Mix"]}
    )

    assert [p["id"] for p in snapshot["playlists"]] == ["pl0"]
    assert snapshot["playlists"][0]["source_folder"] == "NICHE MIXES"
    assert snapshot["unmatched_names"] == []
