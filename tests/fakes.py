"""In-memory stand-in for spotipy.Spotify, mirroring the response shapes
the snapshot fetchers rely on. No network, no auth."""
from typing import Dict, List, Optional

from spotipy.exceptions import SpotifyException


class FakeSpotify:
    def __init__(
        self,
        playlists: Optional[List[Dict]] = None,
        tracks_by_playlist: Optional[Dict[str, List[Dict]]] = None,
        artists_by_id: Optional[Dict[str, List[str]]] = None,
        unreadable_playlists: Optional[List[str]] = None,
    ):
        self._playlists = playlists or []
        self._tracks = tracks_by_playlist or {}
        self._artists = artists_by_id or {}
        # Playlist IDs that raise 404, mimicking Spotify's algorithmic
        # "Made for you" mixes, which are not readable via the Web API.
        self._unreadable = set(unreadable_playlists or [])
        self.artists_calls: List[List[str]] = []  # batch-size assertions
        # query -> raw search response, for seed-track lookups
        self.search_results: Dict[str, Dict] = {}

    def current_user(self) -> Dict:
        return {"id": "testuser", "display_name": "Test User"}

    def current_user_playlists(self, limit: int, offset: int) -> Dict:
        return {"items": self._playlists[offset:offset + limit]}

    def playlist_items(
        self, playlist_id: str, fields: str, limit: int, offset: int
    ) -> Dict:
        if playlist_id in self._unreadable:
            raise SpotifyException(404, -1, "Resource not found")
        items = self._tracks.get(playlist_id, [])[offset:offset + limit]
        return {"items": items}

    def search(self, q: str, type: str, limit: int) -> Dict:
        return self.search_results.get(q, {"tracks": {"items": []}})

    def artists(self, ids: List[str]) -> Dict:
        self.artists_calls.append(list(ids))
        return {
            "artists": [
                {"id": i, "genres": self._artists.get(i, [])} for i in ids
            ]
        }
