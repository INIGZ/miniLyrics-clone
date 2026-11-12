import bisect
import re
from typing import Any, NamedTuple


class LyricLine(NamedTuple):
    timestamp: float  # seconds
    text: str

    @property
    def time(self) -> float:
        return self.timestamp


# Matches [mm:ss.xx] or [mm:ss.xxx] or [mm:ss]
_TIMESTAMP_RE = re.compile(r"\[(\d+):(\d{2})(?:\.(\d{1,3}))?\]")
# Matches metadata tags like [ti:Title], [ar:Artist], [al:Album], [offset:+500]
_METADATA_RE = re.compile(r"^\[([a-zA-Z_]+)\s*:\s*(.*)\]$")


def _parse_timestamp(min_s: str, sec_s: str, frac_s: str | None) -> float:
    # Scale fractional seconds according to digit count (e.g. .5 -> 0.5, .05 -> 0.05, .500 -> 0.5)
    frac = float(f"0.{frac_s}") if frac_s else 0.0
    return round(int(min_s) * 60 + int(sec_s) + frac, 3)


class LRCParser:
    def __init__(self, lrc_input: str | dict[str, Any] | None = None) -> None:
        self.metadata: dict[str, str] = {}
        self.offset_ms: int = 0
        self.lines: list[LyricLine] = []
        self._timestamps: list[float] = []
        if lrc_input:
            self.parse(lrc_input)

    @property
    def title(self) -> str:
        return self.metadata.get("ti", "")

    @property
    def artist(self) -> str:
        return self.metadata.get("ar", "")

    @property
    def album(self) -> str:
        return self.metadata.get("al", "")

    @property
    def offset(self) -> int:
        return self.offset_ms

    def parse(self, content: str | dict[str, Any]) -> "LRCParser":
        self.lines.clear()
        self.metadata.clear()
        self.offset_ms = 0

        if isinstance(content, dict):
            # Extract metadata and lyrics text from response dict (e.g. LRCLIB response)
            tag_map = {"trackName": "ti", "artistName": "ar", "albumName": "al"}
            for key, tag in tag_map.items():
                if key in content and content[key]:
                    self.metadata[tag] = str(content[key])
            raw_text = content.get("syncedLyrics") or content.get("plainLyrics") or ""
        else:
            raw_text = content

        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Parse metadata tags: [ti:Title], [ar:Artist], [al:Album], [offset:+500]
            meta_match = _METADATA_RE.match(line)
            if meta_match:
                tag = meta_match.group(1).lower()
                val = meta_match.group(2).strip()
                self.metadata[tag] = val
                if tag == "offset":
                    try:
                        self.offset_ms = int(val)
                    except ValueError:
                        try:
                            self.offset_ms = int(float(val))
                        except ValueError:
                            pass
                continue

            # Parse timestamp tags: e.g. [00:10.00][00:15.00]Hello
            matches = list(_TIMESTAMP_RE.finditer(line))
            if not matches:
                continue

            # Strip all matched timestamps to extract lyric text
            text = _TIMESTAMP_RE.sub("", line).strip()
            for m in matches:
                ts = _parse_timestamp(m.group(1), m.group(2), m.group(3))
                self.lines.append(LyricLine(timestamp=ts, text=text))

        # Store lines sorted by timestamp in seconds
        self.lines.sort(key=lambda item: item.timestamp)
        self._timestamps = [line.timestamp for line in self.lines]
        return self

    def get_line_index_at(self, time_seconds: float, offset_ms: float = 0) -> int:
        """Fast bisect lookup: returns active line index, or -1 if before the first line.

        Offset shifts playback time up (+ appears sooner), per LRC standard.
        """
        if not self.lines:
            return -1
        effective_time = time_seconds + (self.offset_ms + offset_ms) / 1000.0
        # bisect_right finds insertion index after elements <= effective_time
        return bisect.bisect_right(self._timestamps, effective_time) - 1

    def get_line_at(self, time_seconds: float, offset_ms: float = 0) -> LyricLine | None:
        idx = self.get_line_index_at(time_seconds, offset_ms)
        return self.lines[idx] if idx >= 0 else None

    def get_lyrics_window(
        self, time_seconds: float, window_size: int = 5, offset_ms: float = 0
    ) -> tuple[int, list[LyricLine]]:
        """Return (active_index, list_of_lines) centered around active line.

        active_index is relative to list_of_lines (or -1 if before first line).
        """
        if not self.lines or window_size <= 0:
            return -1, []

        active_idx = self.get_line_index_at(time_seconds, offset_ms)
        n = len(self.lines)

        if n <= window_size:
            return active_idx, list(self.lines)

        if active_idx == -1:
            start = 0
            rel_idx = -1
        else:
            half = window_size // 2
            start = max(0, min(active_idx - half, n - window_size))
            rel_idx = active_idx - start

        return rel_idx, self.lines[start : start + window_size]

    def __len__(self) -> int:
        return len(self.lines)

    def __getitem__(self, index: int) -> LyricLine:
        return self.lines[index]

    def __iter__(self):
        return iter(self.lines)


def parse_lrc(lrc_input: str | dict[str, Any]) -> LRCParser:
    return LRCParser(lrc_input)
