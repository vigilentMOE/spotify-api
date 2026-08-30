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
