import pytest

import spotify_common


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
