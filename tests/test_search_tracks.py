import search_tracks
from tests.fakes import FakeSpotify


def test_normalize_folds_case_and_punctuation():
    assert search_tracks.normalize("Super Smash Bros.") == "super smash bros"


def test_normalize_collapses_whitespace_and_symbols():
    assert search_tracks.normalize("THOT!  (feat. Quavo)") == (
        "thot feat quavo"
    )


def test_query_terms_drops_generic_music_words():
    # 'soundtrack' would otherwise have to appear in every kept row.
    assert search_tracks.query_terms("Super Smash Brothers soundtrack") == [
        "super", "smash", "brothers",
    ]


def test_query_terms_keeps_field_filter_values():
    assert search_tracks.query_terms('album:"Resident Evil 4"') == [
        "resident", "evil", "4",
    ]


def test_query_terms_drops_non_text_filters():
    # year:/tag:/isrc: values never appear in a track or album name.
    assert search_tracks.query_terms("zelda year:1998 tag:hipster") == [
        "zelda",
    ]


def test_relevance_is_the_fraction_of_query_terms_present():
    track = {
        "name": "Lifelight",
        "album": {"name": "Super Smash Bros. Ultimate"},
        "artists": [{"name": "Akano"}],
    }
    assert search_tracks.relevance(track, ["super", "smash", "lifelight"]) == 1.0
    assert search_tracks.relevance(track, ["super", "smash", "mario"]) == 2 / 3


def test_relevance_matches_abbreviations_sharing_a_prefix():
    # 'super smash brothers' must still find 'Super Smash Bros.'
    track = {
        "name": "Menu Theme",
        "album": {"name": "Super Smash Bros. Melee"},
        "artists": [{"name": "Hirokazu Ando"}],
    }
    assert search_tracks.relevance(
        track, ["super", "smash", "brothers"]
    ) == 1.0


def test_term_matches_plural_and_possessive_forms():
    assert search_tracks.term_matches("zelda", ["zeldas", "theme"])


def test_term_matches_rejects_words_that_merely_share_a_prefix():
    # The abbreviation rule must not make 'smash' match 'smart'.
    assert not search_tracks.term_matches("smash", ["smart", "bomb"])
    assert not search_tracks.term_matches("resident", ["resistance"])


def test_relevance_of_empty_terms_is_one():
    assert search_tracks.relevance({"name": "x"}, []) == 1.0


def test_filter_relevant_drops_popular_but_off_target_hits():
    # Verified against the live API: a bare popularity sort on
    # 'super smash bros soundtrack' puts these two rap tracks and a Mario
    # theme above every actual Smash cut.
    smash = {
        "name": "Menu Theme",
        "album": {"name": "Super Smash Bros. Melee"},
        "artists": [{"name": "Hirokazu Ando"}],
        "popularity": 30,
    }
    mario = {
        "name": "Super Mario Bros. Main Theme",
        "album": {"name": "Top 10 Nes Soundtracks"},
        "artists": [{"name": "Koji Kondo"}],
        "popularity": 57,
    }
    thot = {
        "name": "THOT!",
        "album": {"name": "THOT!"},
        "artists": [{"name": "TOKYO'S REVENGE"}],
        "popularity": 55,
    }
    kept, dropped = search_tracks.filter_relevant(
        [smash, mario, thot], ["super", "smash", "brothers"]
    )
    assert kept == [smash]
    assert dropped == [mario, thot]


def test_collapse_versions_keeps_the_most_popular_copy_of_a_recording():
    single = {
        "id": "a", "name": "Serenity", "popularity": 60,
        "artists": [{"name": "Capcom Sound Team"}],
    }
    reissue = {
        "id": "b", "name": "serenity", "popularity": 0,
        "artists": [{"name": "Capcom Sound Team"}],
    }
    other_artist = {
        "id": "c", "name": "Serenity", "popularity": 12,
        "artists": [{"name": "Someone Else"}],
    }
    assert search_tracks.collapse_versions(
        [reissue, single, other_artist]
    ) == [single, other_artist]


def test_rank_by_popularity_sorts_descending_with_name_tiebreak():
    tracks = [
        {"name": "b", "popularity": 40},
        {"name": "a", "popularity": 40},
        {"name": "c", "popularity": 90},
    ]
    assert [t["name"] for t in search_tracks.rank_by_popularity(tracks)] == [
        "c", "a", "b",
    ]


def test_rank_by_popularity_treats_missing_popularity_as_zero():
    tracks = [{"name": "a"}, {"name": "b", "popularity": 1}]
    assert [t["name"] for t in search_tracks.rank_by_popularity(tracks)] == [
        "b", "a",
    ]


def fake_track(index: int, name: str = None, popularity: int = 0) -> dict:
    return {
        "id": f"t{index}",
        "name": name or f"Track {index}",
        "popularity": popularity,
        "album": {"name": "An Album", "release_date": "2018-01-01"},
        "artists": [{"id": f"a{index}", "name": f"Artist {index}"}],
        "duration_ms": 120_000,
    }


def test_search_all_pages_collects_every_hit():
    tracks = [fake_track(i) for i in range(120)]
    sp = FakeSpotify(tracks_by_query={"zelda": tracks})
    found = search_tracks.search_all_pages(sp, "zelda")
    assert [t["id"] for t in found] == [t["id"] for t in tracks]
    assert [(limit, offset) for _, limit, offset, _ in sp.search_calls] == [
        (50, 0), (50, 50), (50, 100),
    ]


def test_search_all_pages_ignores_the_reported_total():
    # Live check: 'super smash bros soundtrack' reported total 485 while
    # offset 950 still returned a full page. The fake reports total 1.
    sp = FakeSpotify(tracks_by_query={"zelda": [fake_track(i) for i in range(60)]})
    assert len(search_tracks.search_all_pages(sp, "zelda")) == 60


def test_search_all_pages_dedupes_ids_repeated_across_pages():
    page = [fake_track(i) for i in range(50)]
    sp = FakeSpotify(tracks_by_query={"zelda": page + page[:10]})
    assert len(search_tracks.search_all_pages(sp, "zelda")) == 50


def test_search_all_pages_stops_at_the_offset_ceiling():
    # limit + offset > 1000 is a 400 from Spotify, so 1000 is all there is.
    sp = FakeSpotify(tracks_by_query={"zelda": [fake_track(i) for i in range(1200)]})
    found = search_tracks.search_all_pages(sp, "zelda")
    assert len(found) == 1000
    assert len(sp.search_calls) == 20


def test_search_all_pages_honours_max_pages():
    sp = FakeSpotify(tracks_by_query={"zelda": [fake_track(i) for i in range(500)]})
    found = search_tracks.search_all_pages(sp, "zelda", max_pages=2)
    assert len(found) == 100
    assert len(sp.search_calls) == 2


def test_search_all_pages_skips_items_with_no_id():
    sp = FakeSpotify(tracks_by_query={"zelda": [fake_track(1), None, {"id": None}]})
    assert [t["id"] for t in search_tracks.search_all_pages(sp, "zelda")] == ["t1"]


def test_search_all_pages_passes_the_market_through():
    sp = FakeSpotify(tracks_by_query={"zelda": [fake_track(1)]})
    search_tracks.search_all_pages(sp, "zelda", market="JP")
    assert sp.search_calls[0][3] == "JP"


def test_select_relevant_prefers_the_strict_threshold():
    strict = [
        fake_track(i, name=f"Zelda Theme {i}", popularity=i) for i in range(6)
    ]
    junk = [fake_track(90, name="Unrelated Banger", popularity=99)]
    kept, threshold = search_tracks.select_relevant(strict + junk, ["zelda"])
    assert threshold == 1.0
    assert kept == strict


def test_select_relevant_relaxes_when_strict_finds_too_few():
    # Only partial matches exist: 2 of the 3 terms appear. Returning nothing
    # would be worse than returning the near-misses and saying so.
    partial = [
        {
            "id": f"p{i}", "name": "Save Room",
            "album": {"name": "Resident Evil 2"},
            "artists": [{"name": "Capcom Sound Team"}], "popularity": i,
        }
        for i in range(3)
    ]
    kept, threshold = search_tracks.select_relevant(
        partial, ["resident", "evil", "piano"]
    )
    assert threshold < 1.0
    assert kept == partial


def test_select_relevant_falls_back_to_every_hit_when_nothing_matches():
    tracks = [fake_track(1, name="Nothing Alike")]
    kept, threshold = search_tracks.select_relevant(tracks, ["zelda", "ocarina"])
    assert kept == tracks
    assert threshold == 0.0


def test_build_row_falls_back_to_placeholders_for_missing_metadata():
    row = search_tracks.build_row({"name": "Untitled"}, {}, max_genres=4)
    assert row["TRACK"] == "Untitled"
    assert row["ARTIST"] == "-"
    assert row["ALBUM"] == "-"
    assert row["YEAR"] == "-"
    assert row["POP"] == "-"
    assert row["ID"] == "-"
    assert row["GENRES"] == "-"


def test_build_row_joins_genres_from_every_artist():
    track = fake_track(1)
    track["artists"].append({"id": "a2", "name": "Second"})
    row = search_tracks.build_row(
        track, {"a1": ["japanese vgm"], "a2": ["soundtrack"]}, max_genres=4
    )
    assert row["GENRES"] == "japanese vgm; soundtrack"


def test_render_table_header_names_every_column_in_order():
    lines = search_tracks.render_table([], "zelda", 0, 1.0, generated_at="x")
    assert lines[2].split() == [name for name, _ in search_tracks.COLUMNS]


def test_render_table_titles_the_report_with_the_query():
    lines = search_tracks.render_table([], "zelda ocarina", 12, 1.0, generated_at="x")
    assert "zelda ocarina" in lines[0]


def test_render_table_emits_one_line_per_track():
    rows = [search_tracks.build_row(fake_track(i), {}, 4) for i in range(5)]
    lines = search_tracks.render_table(rows, "q", 5, 1.0, generated_at="x")
    assert len(lines) == search_tracks.HEADER_LINES + 5


def test_render_table_keeps_every_row_within_the_target_width():
    track = fake_track(1, name="x" * 120)
    track["album"]["name"] = "y" * 120
    track["artists"][0]["name"] = "z" * 120
    row = search_tracks.build_row(track, {"a1": ["g" * 40, "h" * 40]}, 4)
    lines = search_tracks.render_table([row], "q", 1, 1.0, generated_at="x")
    assert max(len(line) for line in lines) <= search_tracks.MAX_ROW_WIDTH


def test_max_row_width_matches_the_declared_columns():
    padded = sum(w for _, w in search_tracks.COLUMNS if w)
    gutters = len(search_tracks.GUTTER) * (len(search_tracks.COLUMNS) - 1)
    assert search_tracks.MAX_ROW_WIDTH == (
        padded + gutters + search_tracks.GENRES_WIDTH
    )


def test_as_records_carries_the_machine_readable_fields():
    track = fake_track(1, name="Lifelight", popularity=57)
    records = search_tracks.as_records([track], {"a1": ["japanese vgm"]}, 4)
    assert records == [{
        "rank": 1,
        "name": "Lifelight",
        "artists": ["Artist 1"],
        "album": "An Album",
        "release_date": "2018-01-01",
        "duration_ms": 120_000,
        "popularity": 57,
        "id": "t1",
        "uri": "spotify:track:t1",
        "genres": ["japanese vgm"],
    }]


def _smash_catalogue():
    """A miniature of the real result set: two on-target Smash tracks and
    the popular off-target hits the live API actually returns for it."""
    def track(tid, name, album, artist, pop, artist_id="a1"):
        return {
            "id": tid, "name": name, "popularity": pop,
            "album": {"name": album, "release_date": "2018-12-07"},
            "artists": [{"id": artist_id, "name": artist}],
            "duration_ms": 90_000,
        }
    return [
        track("t1", "Menu Theme", "Super Smash Bros. Melee", "Hirokazu Ando", 30),
        track("t2", "Lifelight", "Super Smash Bros. Ultimate", "Akano", 57, "a2"),
        track("t3", "Super Mario Bros. Main Theme", "Nes Soundtracks", "Koji Kondo", 58, "a3"),
        track("t4", "THOT!", "THOT!", "TOKYO'S REVENGE", 55, "a4"),
    ]


def test_build_report_ranks_on_target_hits_by_popularity():
    query = "super smash brothers soundtrack"
    sp = FakeSpotify(tracks_by_query={query: _smash_catalogue()})
    lines = search_tracks.build_report(sp, query)
    body = lines[search_tracks.HEADER_LINES:]
    assert len(body) == 2
    assert body[0].startswith("Lifelight")   # pop 57
    assert body[1].startswith("Menu Theme")  # pop 30
    assert "Mario" not in "\n".join(body)
    assert "THOT" not in "\n".join(body)


def test_build_report_honours_limit():
    query = "zelda"
    tracks = [fake_track(i, name=f"Zelda {i}", popularity=i) for i in range(30)]
    sp = FakeSpotify(tracks_by_query={query: tracks})
    lines = search_tracks.build_report(sp, query, limit=5)
    assert len(lines) == search_tracks.HEADER_LINES + 5


def test_build_report_looks_up_genres_in_one_batched_call():
    query = "zelda"
    tracks = [fake_track(i, name=f"Zelda {i}") for i in range(30)]
    sp = FakeSpotify(
        tracks_by_query={query: tracks},
        artists_by_id={f"a{i}": ["japanese vgm"] for i in range(30)},
    )
    lines = search_tracks.build_report(sp, query)
    assert len(sp.artists_calls) == 1
    assert "japanese vgm" in lines[-1]


def test_build_report_can_skip_the_genre_lookup_entirely():
    query = "zelda"
    sp = FakeSpotify(tracks_by_query={query: [fake_track(1, name="Zelda")]})
    lines = search_tracks.build_report(sp, query, with_genres=False)
    assert sp.artists_calls == []
    assert lines[-1].rstrip().endswith("t1")


def test_build_report_reports_dropped_off_target_hits_on_stderr(capsys):
    query = "super smash brothers"
    sp = FakeSpotify(tracks_by_query={query: _smash_catalogue()})
    search_tracks.build_report(sp, query)
    err = capsys.readouterr().err
    assert "2 off-target" in err


def test_build_report_with_no_hits_renders_the_header_only():
    sp = FakeSpotify(tracks_by_query={"nothing": []})
    lines = search_tracks.build_report(sp, "nothing")
    assert len(lines) == search_tracks.HEADER_LINES


def _stub_client(monkeypatch, sp):
    monkeypatch.setattr(search_tracks, "build_public_client", lambda: sp)


def test_main_prints_the_table_to_stdout_by_default(monkeypatch, capsys):
    query = "super smash brothers"
    _stub_client(monkeypatch, FakeSpotify(tracks_by_query={query: _smash_catalogue()}))
    monkeypatch.setattr("sys.argv", ["search_tracks.py", query])
    search_tracks.main()
    out = capsys.readouterr().out
    assert out.startswith("# Spotify search")
    assert len(out.splitlines()) == search_tracks.HEADER_LINES + 2


def test_main_keeps_progress_on_stderr(monkeypatch, capsys):
    query = "zelda"
    _stub_client(monkeypatch, FakeSpotify(tracks_by_query={query: [fake_track(1, name="Zelda")]}))
    monkeypatch.setattr("sys.argv", ["search_tracks.py", query])
    search_tracks.main()
    captured = capsys.readouterr()
    assert "unique tracks" in captured.err
    assert "unique tracks" not in captured.out


def test_main_json_flag_emits_records_on_stdout(monkeypatch, capsys):
    import json

    query = "zelda"
    _stub_client(monkeypatch, FakeSpotify(
        tracks_by_query={query: [fake_track(1, name="Zelda", popularity=42)]},
        artists_by_id={"a1": ["japanese vgm"]},
    ))
    monkeypatch.setattr("sys.argv", ["search_tracks.py", query, "--json"])
    search_tracks.main()
    records = json.loads(capsys.readouterr().out)
    assert records[0]["id"] == "t1"
    assert records[0]["popularity"] == 42
    assert records[0]["genres"] == ["japanese vgm"]


def test_main_output_flag_writes_the_file_and_prints_only_the_path(
    monkeypatch, capsys, tmp_path
):
    query = "zelda"
    _stub_client(monkeypatch, FakeSpotify(tracks_by_query={query: [fake_track(1, name="Zelda")]}))
    target = tmp_path / "hits.txt"
    monkeypatch.setattr(
        "sys.argv", ["search_tracks.py", query, "--output", str(target)]
    )
    search_tracks.main()
    assert capsys.readouterr().out.strip() == str(target)
    assert target.read_text().startswith("# Spotify search")
    assert target.read_text().endswith("\n")


def test_main_passes_limit_and_market_through(monkeypatch, capsys):
    query = "zelda"
    tracks = [fake_track(i, name=f"Zelda {i}", popularity=i) for i in range(10)]
    sp = FakeSpotify(tracks_by_query={query: tracks})
    _stub_client(monkeypatch, sp)
    monkeypatch.setattr(
        "sys.argv",
        ["search_tracks.py", query, "--limit", "3", "--market", "JP"],
    )
    search_tracks.main()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == search_tracks.HEADER_LINES + 3
    assert sp.search_calls[0][3] == "JP"


def test_main_no_genres_flag_skips_the_artist_lookup(monkeypatch, capsys):
    query = "zelda"
    sp = FakeSpotify(tracks_by_query={query: [fake_track(1, name="Zelda")]})
    _stub_client(monkeypatch, sp)
    monkeypatch.setattr("sys.argv", ["search_tracks.py", query, "--no-genres"])
    search_tracks.main()
    assert sp.artists_calls == []
    assert "GENRES" not in capsys.readouterr().out


def test_render_table_omits_the_genre_note_when_the_column_is_gone():
    columns = tuple(c for c in search_tracks.COLUMNS if c[0] != "GENRES")
    lines = search_tracks.render_table(
        [], "q", 0, 1.0, generated_at="x", columns=columns
    )
    assert "genres" not in lines[1]
