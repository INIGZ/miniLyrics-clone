import json
from pathlib import Path
import re
from typing import Any
import requests

BASE_URL = "https://lrclib.net/api"
DEFAULT_CACHE_DIR = ".cache/lyrics"
DEFAULT_TIMEOUT = 5.0
DEFAULT_USER_AGENT = "MiniLyrics/1.0"


def sanitize_filename(name: str) -> str:
    """Sanitize track/artist strings for safe filesystem storage."""
    # Replace illegal filesystem characters with underscore
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
    # Clean up mixed underscore and whitespace sequences
    sanitized = re.sub(r"[\s_]*_[\s_]*", "_", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(". _")
    return sanitized or "unknown"


def get_cache_filename(track_name: str, artist_name: str = "") -> str:
    base = f"{artist_name} - {track_name}" if artist_name else track_name
    return f"{sanitize_filename(base)}.json"


class LRCLibClient:
    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        timeout: float = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        base_url: str = BASE_URL,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.user_agent = user_agent
        self.base_url = base_url.rstrip("/")

    def get_cache_path(self, track_name: str, artist_name: str = "") -> Path:
        return self.cache_dir / get_cache_filename(track_name, artist_name)

    def _load_from_cache(self, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save_to_cache(self, path: Path, data: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Cache write failures should never break runtime flow

    def _request(self, endpoint: str, params: dict[str, Any]) -> requests.Response | None:
        try:
            headers = {"User-Agent": self.user_agent}
            resp = requests.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            return resp
        except (requests.RequestException, Exception):
            return None

    def _fetch_exact(
        self,
        track_name: str,
        artist_name: str = "",
        album_name: str = "",
        duration: float | int | None = None,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {"track_name": track_name}
        if artist_name:
            params["artist_name"] = artist_name
        if album_name:
            params["album_name"] = album_name
        if duration is not None:
            params["duration"] = round(float(duration))

        resp = self._request("/get", params)
        if resp is not None and resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    return data
            except (ValueError, Exception):
                return None
        return None

    def _fetch_search(self, track_name: str, artist_name: str = "") -> dict[str, Any] | None:
        query = f"{track_name} {artist_name}".strip()
        resp = self._request("/search", {"q": query})
        if resp is None or resp.status_code != 200:
            return None

        try:
            results = resp.json()
        except (ValueError, Exception):
            return None

        if not isinstance(results, list) or not results:
            return None

        # shortcut: picks first candidate with synced lyrics without fuzzy scoring, upgrade to distance-based ranking if false positive matches occur
        for item in results:
            if isinstance(item, dict) and item.get("syncedLyrics"):
                return item

        # Fallback to candidate with plain lyrics, or the top search result
        for item in results:
            if isinstance(item, dict) and item.get("plainLyrics"):
                return item

        first = results[0]
        return first if isinstance(first, dict) else None

    def get_lyrics(
        self,
        track_name: str,
        artist_name: str = "",
        album_name: str = "",
        duration: float | int | None = None,
    ) -> dict[str, Any] | None:
        """Fetch lyrics data from disk cache, exact LRCLIB endpoint, or search fallback."""
        cache_path = self.get_cache_path(track_name, artist_name)
        cached = self._load_from_cache(cache_path)
        if cached is not None:
            return cached

        # Attempt exact match first
        result = self._fetch_exact(track_name, artist_name, album_name, duration)

        # Fallback to search if exact match returned 404/failed or lacked synced lyrics
        if result is None or not result.get("syncedLyrics"):
            search_result = self._fetch_search(track_name, artist_name)
            if search_result is not None:
                if result is None or search_result.get("syncedLyrics"):
                    result = search_result

        if result is not None:
            self._save_to_cache(cache_path, result)

        return result

    def get_synced_lyrics(
        self,
        track_name: str,
        artist_name: str = "",
        album_name: str = "",
        duration: float | int | None = None,
    ) -> str | None:
        """Convenience method returning synced LRC string or None."""
        data = self.get_lyrics(track_name, artist_name, album_name, duration)
        if isinstance(data, dict):
            return data.get("syncedLyrics")
        return None


_default_client = LRCLibClient()


def get_lyrics(
    track_name: str,
    artist_name: str = "",
    album_name: str = "",
    duration: float | int | None = None,
) -> dict[str, Any] | None:
    return _default_client.get_lyrics(track_name, artist_name, album_name, duration)


def get_synced_lyrics(
    track_name: str,
    artist_name: str = "",
    album_name: str = "",
    duration: float | int | None = None,
) -> str | None:
    return _default_client.get_synced_lyrics(track_name, artist_name, album_name, duration)
