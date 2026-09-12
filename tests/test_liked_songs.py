import liked_songs
from tests.fakes import FakeSpotify


def test_format_duration_renders_minutes_and_zero_padded_seconds():
    assert liked_songs.format_duration(548_000) == "9:08"


def test_format_duration_renders_hours_for_long_tracks():
    assert liked_songs.format_duration(3_723_000) == "62:03"


def test_format_duration_missing_value_renders_placeholder():
    assert liked_songs.format_duration(None) == "-"


def test_release_year_extracts_year_from_full_date():
    assert liked_songs.release_year("2010-11-22") == "2010"


def test_release_year_accepts_year_only_precision():
    # Spotify's release_date_precision can be year, month or day.
    assert liked_songs.release_year("1994") == "1994"


def test_release_year_accepts_year_month_precision():
    assert liked_songs.release_year("2012-05") == "2012"


def test_release_year_missing_date_renders_placeholder():
    assert liked_songs.release_year(None) == "-"


def test_truncate_leaves_short_text_untouched():
    assert liked_songs.truncate("Runaway", 10) == "Runaway"


def test_truncate_ellipsizes_text_over_width():
    # The ellipsis occupies the final column, so the result is exactly width.
    assert liked_songs.truncate("My Beautiful Dark Twisted Fantasy", 12) == (
        "My Beautifu…"
    )


def test_truncate_result_never_exceeds_width():
    assert len(liked_songs.truncate("x" * 99, 8)) == 8


def test_collect_genres_unions_all_artists_on_the_track():
    genres = liked_songs.collect_genres(
        ["a1", "a2"], {"a1": ["hip hop"], "a2": ["rap"]}, max_genres=0
    )
    assert genres == ["hip hop", "rap"]


def test_collect_genres_dedupes_keeping_first_appearance_order():
    genres = liked_songs.collect_genres(
        ["a1", "a2"], {"a1": ["rap", "trap"], "a2": ["trap", "drill"]},
        max_genres=0,
    )
    assert genres == ["rap", "trap", "drill"]


def test_collect_genres_caps_at_max_genres():
    genres = liked_songs.collect_genres(
        ["a1"], {"a1": ["one", "two", "three", "four", "five"]}, max_genres=3
    )
    assert genres == ["one", "two", "three"]


def test_collect_genres_max_zero_means_unlimited():
    all_genres = ["g%d" % i for i in range(9)]
    genres = liked_songs.collect_genres(["a1"], {"a1": all_genres}, max_genres=0)
    assert genres == all_genres


def test_collect_genres_unknown_artist_contributes_nothing():
    assert liked_songs.collect_genres(["missing"], {}, max_genres=0) == []


def _saved_item(**overrides):
    item = {
        "added_at": "2024-03-11T09:41:07Z",
        "track": {
            "id": "4Ye8jGrfoshkKZUM6s2Sa4",
            "name": "Runaway",
            "artists": [{"id": "a1", "name": "Kanye West"}],
            "album": {
                "name": "My Beautiful Dark Twisted Fantasy",
                "release_date": "2010-11-22",
            },
            "duration_ms": 548_000,
            "popularity": 78,
        },
    }
    item.update(overrides)
    return item


def test_build_row_maps_every_column_from_the_saved_item():
    row = liked_songs.build_row(
        _saved_item(), {"a1": ["hip hop", "rap"]}, max_genres=4
    )
    assert row == {
        "ADDED": "2024-03-11",
        "TRACK": "Runaway",
        "ARTIST": "Kanye West",
        "ALBUM": "My Beautiful Dark Twisted Fantasy",
        "YEAR": "2010",
        "LEN": "9:08",
        "POP": "78",
        "ID": "4Ye8jGrfoshkKZUM6s2Sa4",
        "GENRES": "hip hop; rap",
    }


def test_build_row_joins_multiple_artists():
    item = _saved_item()
    item["track"]["artists"] = [
        {"id": "a1", "name": "Kanye West"},
        {"id": "a2", "name": "Pusha T"},
    ]
    row = liked_songs.build_row(item, {}, max_genres=4)
    assert row["ARTIST"] == "Kanye West, Pusha T"


def test_build_row_pulls_genres_from_every_credited_artist():
    item = _saved_item()
    item["track"]["artists"] = [
        {"id": "a1", "name": "Kanye West"},
        {"id": "a2", "name": "Bon Iver"},
    ]
    row = liked_songs.build_row(
        item, {"a1": ["rap"], "a2": ["indie folk"]}, max_genres=4
    )
    assert row["GENRES"] == "rap; indie folk"


def test_build_row_renders_placeholder_when_no_artist_has_genres():
    row = liked_songs.build_row(_saved_item(), {}, max_genres=4)
    assert row["GENRES"] == "-"


def test_build_row_tolerates_a_local_file_missing_most_metadata():
    # Local files carry no id, no album date and no popularity.
    item = _saved_item(track={
        "id": None,
        "name": "Some Bootleg",
        "artists": [{"id": None, "name": "Unknown"}],
        "album": {"name": "", "release_date": None},
        "duration_ms": None,
        "popularity": None,
    })
    row = liked_songs.build_row(item, {}, max_genres=4)
    assert row["ID"] == "-"
    assert row["ALBUM"] == "-"
    assert row["YEAR"] == "-"
    assert row["LEN"] == "-"
    assert row["POP"] == "-"
    assert row["TRACK"] == "Some Bootleg"


def test_build_row_added_at_missing_renders_placeholder():
    row = liked_songs.build_row(
        _saved_item(added_at=None), {}, max_genres=4
    )
    assert row["ADDED"] == "-"


def _rows(n=1, **overrides):
    row = liked_songs.build_row(_saved_item(), {"a1": ["hip hop"]}, 4)
    row.update(overrides)
    return [row] * n


def test_render_table_starts_with_a_comment_preamble():
    lines = liked_songs.render_table(_rows(2), generated_at="2026-09-12T14:22Z")
    assert lines[0] == "# Liked Songs — 2 tracks — generated 2026-09-12T14:22Z"
    assert lines[1].startswith("# genres are artist-level")


def test_render_table_header_names_every_column_in_order():
    lines = liked_songs.render_table(_rows(), generated_at="x")
    assert lines[2].split() == [
        "ADDED", "TRACK", "ARTIST", "ALBUM", "YEAR", "LEN", "POP", "ID",
        "GENRES",
    ]


def test_render_table_rules_off_the_header():
    lines = liked_songs.render_table(_rows(), generated_at="x")
    assert set(lines[3]) == {"─"}
    assert len(lines[3]) == len(lines[2])


def test_render_table_emits_one_line_per_track():
    lines = liked_songs.render_table(_rows(5), generated_at="x")
    assert len(lines) == liked_songs.HEADER_LINES + 5


def test_render_table_aligns_columns_at_identical_offsets():
    # A short row and a long row must put GENRES at the same column.
    short = liked_songs.build_row(_saved_item(), {}, 4)
    long_item = _saved_item()
    long_item["track"]["name"] = "A Very Long Track Title " * 5
    long_item["track"]["album"]["name"] = "An Absurdly Long Album Name " * 4
    long = liked_songs.build_row(long_item, {"a1": ["hip hop"]}, 4)
    lines = liked_songs.render_table([short, long], generated_at="x")
    track_at = lines[2].index("TRACK")
    assert lines[-1][track_at:].startswith("A Very")
    assert lines[-2][track_at:].startswith("Runaway")
    genres_at = lines[2].index("GENRES")
    assert lines[-1][genres_at:].startswith("hip hop")
    assert lines[-2][genres_at:].startswith("-")


def test_render_table_truncates_overlong_fields_to_their_column():
    long_item = _saved_item()
    long_item["track"]["name"] = "x" * 200
    lines = liked_songs.render_table(
        [liked_songs.build_row(long_item, {}, 4)], generated_at="x"
    )
    assert "…" in lines[-1]
    assert "x" * 200 not in lines[-1]


def test_render_table_keeps_rows_within_the_target_width():
    long_item = _saved_item()
    long_item["track"]["name"] = "x" * 200
    long_item["track"]["album"]["name"] = "y" * 200
    long_item["track"]["artists"] = [{"id": "a1", "name": "z" * 200}]
    lines = liked_songs.render_table(
        [liked_songs.build_row(long_item, {"a1": ["g"] * 4}, 4)],
        generated_at="x",
    )
    assert all(len(line) <= 210 for line in lines)


def test_render_table_with_no_tracks_still_renders_the_header():
    lines = liked_songs.render_table([], generated_at="x")
    assert lines[0] == "# Liked Songs — 0 tracks — generated x"
    assert len(lines) == liked_songs.HEADER_LINES


def _library(n):
    return [_saved_item() for _ in range(n)]


def test_fetch_saved_tracks_pages_through_the_whole_library():
    sp = FakeSpotify(saved_tracks=_library(130))  # SAVED_PAGE is 50
    assert len(liked_songs.fetch_saved_tracks(sp)) == 130


def test_fetch_saved_tracks_requests_full_pages():
    sp = FakeSpotify(saved_tracks=_library(130))
    liked_songs.fetch_saved_tracks(sp)
    assert sp.saved_tracks_calls == [(50, 0), (50, 50), (50, 100)]


def test_fetch_saved_tracks_stops_at_limit():
    sp = FakeSpotify(saved_tracks=_library(130))
    assert len(liked_songs.fetch_saved_tracks(sp, limit=60)) == 60


def test_fetch_saved_tracks_limit_does_not_overfetch():
    sp = FakeSpotify(saved_tracks=_library(500))
    liked_songs.fetch_saved_tracks(sp, limit=60)
    assert sp.saved_tracks_calls == [(50, 0), (10, 50)]


def test_fetch_saved_tracks_skips_items_with_no_track():
    # Tracks removed from Spotify's catalogue come back as a null track.
    items = _library(2) + [{"added_at": "2024-01-01T00:00:00Z", "track": None}]
    sp = FakeSpotify(saved_tracks=items)
    assert len(liked_songs.fetch_saved_tracks(sp)) == 2


def test_fetch_saved_tracks_empty_library_returns_nothing():
    assert liked_songs.fetch_saved_tracks(FakeSpotify(saved_tracks=[])) == []


def test_build_report_renders_a_line_per_liked_track():
    sp = FakeSpotify(saved_tracks=_library(3), artists_by_id={"a1": ["rap"]})
    lines = liked_songs.build_report(sp)
    assert len(lines) == liked_songs.HEADER_LINES + 3
    assert all(line.endswith("rap") for line in lines[liked_songs.HEADER_LINES:])


def test_build_report_looks_up_each_artist_only_once():
    sp = FakeSpotify(saved_tracks=_library(120), artists_by_id={"a1": ["rap"]})
    liked_songs.build_report(sp)
    assert sp.artists_calls == [["a1"]]


def test_build_report_batches_artist_lookups_within_the_spotify_cap():
    items = []
    artists = {}
    for i in range(60):
        item = _saved_item()
        item["track"]["artists"] = [{"id": f"a{i}", "name": f"Artist {i}"}]
        items.append(item)
        artists[f"a{i}"] = ["rock"]
    sp = FakeSpotify(saved_tracks=items, artists_by_id=artists)
    liked_songs.build_report(sp)
    assert all(len(call) <= 50 for call in sp.artists_calls)
    assert sum(len(call) for call in sp.artists_calls) == 60


def test_build_report_honours_max_genres():
    sp = FakeSpotify(
        saved_tracks=_library(1),
        artists_by_id={"a1": ["one", "two", "three"]},
    )
    lines = liked_songs.build_report(sp, max_genres=2)
    assert lines[-1].endswith("one; two")


def test_build_report_honours_limit():
    sp = FakeSpotify(saved_tracks=_library(30), artists_by_id={"a1": ["rap"]})
    assert len(liked_songs.build_report(sp, limit=5)) == liked_songs.HEADER_LINES + 5


def test_build_report_empty_library_renders_header_only():
    assert len(liked_songs.build_report(FakeSpotify(saved_tracks=[]))) == liked_songs.HEADER_LINES


def _stub_client(monkeypatch, sp):
    monkeypatch.setattr(liked_songs, "build_user_client", lambda scope: sp)


def test_main_writes_the_table_to_stdout_by_default(monkeypatch, capsys):
    _stub_client(monkeypatch, FakeSpotify(saved_tracks=_library(2),
                                          artists_by_id={"a1": ["rap"]}))
    monkeypatch.setattr("sys.argv", ["liked_songs.py"])
    liked_songs.main()
    out = capsys.readouterr().out
    assert out.startswith("# Liked Songs — 2 tracks")
    assert len(out.splitlines()) == liked_songs.HEADER_LINES + 2


def test_main_keeps_progress_on_stderr(monkeypatch, capsys):
    _stub_client(monkeypatch, FakeSpotify(saved_tracks=_library(2),
                                          artists_by_id={"a1": ["rap"]}))
    monkeypatch.setattr("sys.argv", ["liked_songs.py"])
    liked_songs.main()
    captured = capsys.readouterr()
    assert "Fetched 2 liked tracks." in captured.err
    assert "Fetched" not in captured.out


def test_main_output_flag_writes_file_and_prints_only_the_path(
    monkeypatch, capsys, tmp_path
):
    _stub_client(monkeypatch, FakeSpotify(saved_tracks=_library(2),
                                          artists_by_id={"a1": ["rap"]}))
    target = tmp_path / "liked.txt"
    monkeypatch.setattr("sys.argv", ["liked_songs.py", "--output", str(target)])
    liked_songs.main()
    assert capsys.readouterr().out.strip() == str(target)
    assert target.read_text().startswith("# Liked Songs — 2 tracks")
    assert target.read_text().endswith("\n")


def test_main_passes_limit_and_max_genres_through(monkeypatch, capsys):
    _stub_client(monkeypatch, FakeSpotify(
        saved_tracks=_library(10),
        artists_by_id={"a1": ["one", "two", "three"]},
    ))
    monkeypatch.setattr(
        "sys.argv",
        ["liked_songs.py", "--limit", "3", "--max-genres", "1"],
    )
    liked_songs.main()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == liked_songs.HEADER_LINES + 3
    assert lines[-1].endswith("one")


def test_main_requests_only_the_library_read_scope(monkeypatch, capsys):
    seen = {}

    def fake_client(scope):
        seen["scope"] = scope
        return FakeSpotify(saved_tracks=[])

    monkeypatch.setattr(liked_songs, "build_user_client", fake_client)
    monkeypatch.setattr("sys.argv", ["liked_songs.py"])
    liked_songs.main()
    assert seen["scope"] == "user-library-read"
