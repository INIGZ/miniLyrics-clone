import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

from src.core.lrclib_client import (
    LRCLibClient,
    get_cache_filename,
    get_lyrics,
    get_synced_lyrics,
    sanitize_filename,
)


@pytest.fixture
def client(tmp_path: Path) -> LRCLibClient:
    return LRCLibClient(cache_dir=tmp_path / "lyrics_cache", timeout=2.0)


def test_sanitize_filename():
    assert sanitize_filename('AC/DC: "Highway? <To> |Hell*') == "AC_DC_Highway_To_Hell"
    assert sanitize_filename("...Track Name...   ") == "Track Name"
    assert sanitize_filename("") == "unknown"


def test_get_cache_filename():
    assert get_cache_filename("Yesterday", "The Beatles") == "The Beatles - Yesterday.json"
    assert get_cache_filename("Song Only") == "Song Only.json"


def test_cache_hit_offline(client: LRCLibClient):
    cache_path = client.get_cache_path("Yesterday", "The Beatles")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trackName": "Yesterday",
        "artistName": "The Beatles",
        "syncedLyrics": "[00:05.00]Yesterday",
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    # Even with requests.get patched out, cached data is loaded instantly
    with patch("requests.get") as mock_get:
        res = client.get_lyrics("Yesterday", "The Beatles")
        assert res == payload
        mock_get.assert_not_called()


def test_exact_get_success(client: LRCLibClient):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 101,
        "trackName": "Yesterday",
        "artistName": "The Beatles",
        "syncedLyrics": "[00:05.00]Yesterday",
    }

    with patch("requests.get", return_value=mock_resp) as mock_get:
        data = client.get_lyrics("Yesterday", "The Beatles", album_name="Help!", duration=125)
        assert data is not None
        assert data["syncedLyrics"] == "[00:05.00]Yesterday"
        mock_get.assert_called_once()

    # Verify cached on disk
    cache_file = client.get_cache_path("Yesterday", "The Beatles")
    assert cache_file.is_file()
    with open(cache_file, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["trackName"] == "Yesterday"


def test_fallback_to_search_on_404(client: LRCLibClient):
    resp_404 = MagicMock(status_code=404)
    resp_search = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value=[
                {
                    "id": 202,
                    "trackName": "Yesterday",
                    "artistName": "The Beatles",
                    "syncedLyrics": "[00:05.00]Yesterday from search",
                }
            ]
        ),
    )

    with patch("requests.get", side_effect=[resp_404, resp_search]) as mock_get:
        data = client.get_lyrics("Yesterday", "The Beatles")
        assert data is not None
        assert data["syncedLyrics"] == "[00:05.00]Yesterday from search"
        assert mock_get.call_count == 2

    # Verify search result was cached
    cache_file = client.get_cache_path("Yesterday", "The Beatles")
    assert cache_file.is_file()


def test_fallback_to_search_when_exact_get_lacks_synced_lyrics(client: LRCLibClient):
    # Exact get returns unsynced plain lyrics
    resp_unsynced = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "id": 301,
                "trackName": "Song",
                "artistName": "Artist",
                "plainLyrics": "Only plain lyrics",
                "syncedLyrics": None,
            }
        ),
    )
    # Search finds synced lyrics
    resp_search = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value=[
                {
                    "id": 302,
                    "trackName": "Song",
                    "artistName": "Artist",
                    "syncedLyrics": "[00:01.00]Synced version",
                }
            ]
        ),
    )

    with patch("requests.get", side_effect=[resp_unsynced, resp_search]):
        data = client.get_lyrics("Song", "Artist")
        assert data is not None
        assert data["syncedLyrics"] == "[00:01.00]Synced version"


def test_search_prefers_synced_lyrics_candidate(client: LRCLibClient):
    resp_404 = MagicMock(status_code=404)
    resp_search = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value=[
                {"id": 1, "trackName": "Track", "syncedLyrics": None, "plainLyrics": "Plain"},
                {"id": 2, "trackName": "Track", "syncedLyrics": "[00:02.00]Synced"},
            ]
        ),
    )

    with patch("requests.get", side_effect=[resp_404, resp_search]):
        data = client.get_lyrics("Track", "Artist")
        assert data is not None
        assert data["id"] == 2
        assert data["syncedLyrics"] == "[00:02.00]Synced"


def test_not_found_returns_none(client: LRCLibClient):
    resp_404 = MagicMock(status_code=404)
    resp_search_empty = MagicMock(status_code=200, json=MagicMock(return_value=[]))

    with patch("requests.get", side_effect=[resp_404, resp_search_empty]):
        data = client.get_lyrics("Nonexistent Track", "Nobody")
        assert data is None

    cache_file = client.get_cache_path("Nonexistent Track", "Nobody")
    assert not cache_file.exists()


def test_network_timeout_handling(client: LRCLibClient):
    with patch("requests.get", side_effect=requests.exceptions.Timeout("Connection timed out")):
        res = client.get_lyrics("Slow Track", "Artist")
        assert res is None


def test_network_connection_error_handling(client: LRCLibClient):
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Network down")):
        res = client.get_lyrics("Offline Track", "Artist")
        assert res is None


def test_invalid_json_handling(client: LRCLibClient):
    resp = MagicMock(status_code=200)
    resp.json.side_effect = ValueError("Invalid JSON response")

    with patch("requests.get", return_value=resp):
        res = client.get_lyrics("Bad JSON Track", "Artist")
        assert res is None


def test_get_synced_lyrics(client: LRCLibClient):
    mock_resp = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "trackName": "Track",
                "syncedLyrics": "[00:10.00]Line 1",
            }
        ),
    )
    with patch("requests.get", return_value=mock_resp):
        synced = client.get_synced_lyrics("Track", "Artist")
        assert synced == "[00:10.00]Line 1"

    # When no synced lyrics found
    with patch.object(client, "get_lyrics", return_value=None):
        assert client.get_synced_lyrics("Missing") is None


def test_offline_repeat_play(client: LRCLibClient):
    mock_resp = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "trackName": "Song",
                "artistName": "Band",
                "syncedLyrics": "[00:01.00]Music",
            }
        ),
    )
    # First call: fetched from network and cached
    with patch("requests.get", return_value=mock_resp):
        first = client.get_lyrics("Song", "Band")
        assert first is not None

    # Second call: network raises exception, but cached file loads successfully
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
        second = client.get_lyrics("Song", "Band")
        assert second == first
