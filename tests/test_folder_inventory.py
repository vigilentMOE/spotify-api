import folder_inventory
from tests.fakes import FakeSpotify


def test_is_radio_playlist_detects_seed_radio_names():
    assert folder_inventory.is_radio_playlist("Nangs Radio") is True
    assert folder_inventory.is_radio_playlist("Shoegaze Mix") is False
    # 'Jet Set Radio' is a game soundtrack playlist, but the suffix rule is
    # purely syntactic; the caller scopes it to known-radio folders.
    assert folder_inventory.is_radio_playlist("Radio Ga Ga Radio") is True


def test_seed_query_strips_radio_suffix():
    assert folder_inventory.seed_query("Nangs Radio") == "Nangs"
    assert folder_inventory.seed_query("Body - slowed Radio") == "Body - slowed"


def test_genre_counts_from_name_uses_the_playlist_name():
    # "<Genre> Mix" playlists carry their genre in the name; weight 1 so a
    # name-derived playlist is 100% confident in its single family.
    assert folder_inventory.genre_counts_from_name("Shoegaze Mix") == {
        "Shoegaze Mix": 1
    }


def test_genre_counts_from_name_ignores_unclassifiable_name():
    assert folder_inventory.genre_counts_from_name("Ease") == {}


def test_resolve_radio_genres_uses_seed_track_artists():
    sp = FakeSpotify(artists_by_id={"a1": ["shoegaze", "dream pop"]})
    sp.search_results = {
        "Nangs": {
            "tracks": {"items": [{"artists": [{"id": "a1", "name": "Tame"}]}]}
        }
    }
    counts = folder_inventory.resolve_radio_genres(sp, "Nangs Radio")
    assert counts == {"shoegaze": 1, "dream pop": 1}


def test_resolve_radio_genres_handles_no_search_hit():
    sp = FakeSpotify()
    sp.search_results = {}
    assert folder_inventory.resolve_radio_genres(sp, "Nonexistent Radio") == {}


def test_build_snapshot_entries_marks_source_and_method():
    inventory = {"NICHE MIXES": {"Chill Mixes": ["Shoegaze Mix"]}}
    entries = folder_inventory.build_entries(None, inventory)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_folder"] == "NICHE MIXES / Chill Mixes"
    assert entry["name"] == "Shoegaze Mix"
    assert entry["method"] == "name"
    assert entry["genre_counts"] == {"Shoegaze Mix": 1}
