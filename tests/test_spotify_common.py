import pytest

import spotify_common
from tests.fakes import FakeSpotify


def test_log_writes_to_stderr(capsys):
    spotify_common.log("hello")
    captured = capsys.readouterr()
    assert captured.err == "hello\n"
    assert captured.out == ""


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "abc123")
    assert spotify_common.require_env("SPOTIFY_CLIENT_ID") == "abc123"


def test_require_env_missing_raises_systemexit(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with pytest.raises(SystemExit, match="SPOTIFY_CLIENT_ID"):
        spotify_common.require_env("SPOTIFY_CLIENT_ID")


def test_require_env_empty_string_raises_systemexit(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "")
    with pytest.raises(SystemExit, match="SPOTIFY_CLIENT_ID"):
        spotify_common.require_env("SPOTIFY_CLIENT_ID")


def test_chunked_splits_into_batches():
    assert list(spotify_common.chunked(["a", "b", "c", "d", "e"], 2)) == [
        ["a", "b"], ["c", "d"], ["e"],
    ]


def test_chunked_empty_sequence_yields_nothing():
    assert list(spotify_common.chunked([], 10)) == []


def test_fetch_artist_genres_batches_and_dedupes():
    artists = {f"a{i}": ["rock"] for i in range(60)}
    sp = FakeSpotify(artists_by_id=artists)
    ids = list(artists) + list(artists)  # duplicates must collapse
    result = spotify_common.fetch_artist_genres(sp, ids)
    assert result == artists
    assert all(
        len(call) <= spotify_common.ARTIST_BATCH for call in sp.artists_calls
    )
    assert sum(len(call) for call in sp.artists_calls) == 60
