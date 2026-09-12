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
        saved_tracks: Optional[List[Dict]] = None,
        tracks_by_query: Optional[Dict[str, List[Dict]]] = None,
    ):
        self._playlists = playlists or []
        self._tracks = tracks_by_playlist or {}
        self._artists = artists_by_id or {}
        self._saved_tracks = saved_tracks or []
        # Playlist IDs that raise 404, mimicking Spotify's algorithmic
        # "Made for you" mixes, which are not readable via the Web API.
        self._unreadable = set(unreadable_playlists or [])
        self.artists_calls: List[List[str]] = []  # batch-size assertions
        # (limit, offset) per call, for paging assertions
        self.saved_tracks_calls: List[tuple] = []
        # query -> raw search response, for seed-track lookups
        self.search_results: Dict[str, Dict] = {}
        # query -> every catalogue hit, paged through by search() below
        self._query_tracks = tracks_by_query or {}
        # (q, limit, offset, market) per call, for paging assertions
        self.search_calls: List[tuple] = []

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

    def current_user_saved_tracks(self, limit: int, offset: int) -> Dict:
        self.saved_tracks_calls.append((limit, offset))
        return {
            "items": self._saved_tracks[offset:offset + limit],
            "total": len(self._saved_tracks),
        }

    def search(
        self,
        q: str,
        type: str,
        limit: int,
        offset: int = 0,
        market: Optional[str] = None,
    ) -> Dict:
        self.search_calls.append((q, limit, offset, market))
        if limit > 50:
            raise SpotifyException(400, -1, "Invalid limit")
        # The live API rejects deep paging outright, which is what caps a
        # search at 1000 results.
        if limit + offset > 1000:
            raise SpotifyException(
                400, -1, "Limit + Offset exceeds maximum of 1000"
            )
        if q in self.search_results:
            return self.search_results[q]
        items = self._query_tracks.get(q, [])[offset:offset + limit]
        # `total` is an estimate on the live API and routinely understates
        # what paging actually returns, so it is deliberately wrong here.
        return {"tracks": {"items": items, "total": 1}}

    def artists(self, ids: List[str]) -> Dict:
        self.artists_calls.append(list(ids))
        return {
            "artists": [
                {"id": i, "genres": self._artists.get(i, [])} for i in ids
            ]
        }
