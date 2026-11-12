import pytest
from src.core.lrc_parser import LRCParser, LyricLine, parse_lrc


SAMPLE_LRC = """[ti:Yesterday]
[ar:The Beatles]
[al:Help!]
[offset:+500]
[00:05.06]Yesterday, all my troubles seemed so far away
[00:13.53]Now it looks as though they're here to stay
[00:17.24]Oh, I believe in yesterday
[00:22.64]Suddenly, I'm not half the man I used to be
[00:27.50]There's a shadow hanging over me
"""


def test_metadata_parsing():
    parser = LRCParser(SAMPLE_LRC)
    assert parser.title == "Yesterday"
    assert parser.artist == "The Beatles"
    assert parser.album == "Help!"
    assert parser.offset == 500
    assert parser.metadata.get("ti") == "Yesterday"


def test_negative_offset_and_custom_metadata():
    lrc = """[offset:-250]
[by:MiniLyrics User]
[00:01.00]Test
"""
    parser = LRCParser(lrc)
    assert parser.offset == -250
    assert parser.metadata.get("by") == "MiniLyrics User"


def test_invalid_offset_ignored_safely():
    lrc = "[offset:invalid_num]\n[00:01.00]Test"
    parser = LRCParser(lrc)
    assert parser.offset == 0


def test_timestamp_variations():
    lrc = """[00:01.5]One digit fraction
[00:02.50]Two digit fraction
[00:03.500]Three digit fraction
[00:04]No fraction
"""
    parser = LRCParser(lrc)
    assert len(parser.lines) == 4
    assert parser.lines[0].timestamp == 1.5
    assert parser.lines[1].timestamp == 2.5
    assert parser.lines[2].timestamp == 3.5
    assert parser.lines[3].timestamp == 4.0


def test_multiple_timestamps_per_line():
    lrc = "[00:10.00][00:15.00]Hello world"
    parser = LRCParser(lrc)
    assert len(parser.lines) == 2
    assert parser.lines[0] == LyricLine(10.0, "Hello world")
    assert parser.lines[1] == LyricLine(15.0, "Hello world")


def test_multiple_timestamps_with_spacing():
    lrc = "[00:05.00] [00:12.50] Repeated chorus line"
    parser = LRCParser(lrc)
    assert len(parser.lines) == 2
    assert parser.lines[0].timestamp == 5.0
    assert parser.lines[1].timestamp == 12.5
    assert parser.lines[0].text == "Repeated chorus line"


def test_lines_sorted_chronologically():
    # Provide lines out of order
    lrc = """[00:30.00]Line 3
[00:10.00]Line 1
[00:20.00]Line 2
"""
    parser = LRCParser(lrc)
    timestamps = [line.timestamp for line in parser.lines]
    assert timestamps == [10.0, 20.0, 30.0]
    assert [line.text for line in parser.lines] == ["Line 1", "Line 2", "Line 3"]


def test_empty_lyric_line():
    lrc = "[01:00.00]\n[01:05.00]After instrumental"
    parser = LRCParser(lrc)
    assert len(parser.lines) == 2
    assert parser.lines[0].timestamp == 60.0
    assert parser.lines[0].text == ""
    assert parser.lines[1].text == "After instrumental"


def test_fast_lookup_get_line_index_at():
    lrc = """[00:10.00]First
[00:20.00]Second
[00:30.00]Third
"""
    parser = LRCParser(lrc)

    # Before first line
    assert parser.get_line_index_at(0.0) == -1
    assert parser.get_line_index_at(9.99) == -1

    # Exact boundary and intermediate positions
    assert parser.get_line_index_at(10.0) == 0
    assert parser.get_line_index_at(15.0) == 0
    assert parser.get_line_index_at(20.0) == 1
    assert parser.get_line_index_at(25.0) == 1
    assert parser.get_line_index_at(30.0) == 2
    assert parser.get_line_index_at(100.0) == 2


def test_lookup_with_offset():
    # Sample has [offset:+500] in header
    parser = LRCParser(SAMPLE_LRC)
    # Line 0 is at 5.06s.
    # With header offset +500ms, at playback time 4.56s effective time is 5.06s.
    assert parser.get_line_index_at(4.55) == -1
    assert parser.get_line_index_at(4.56) == 0

    # Additional runtime offset parameter offset_ms
    # 4.36s + 500ms (header) + 200ms (param) = 5.06s -> line 0 active
    assert parser.get_line_index_at(4.35, offset_ms=200) == -1
    assert parser.get_line_index_at(4.36, offset_ms=200) == 0


def test_get_line_at():
    parser = LRCParser(SAMPLE_LRC)
    assert parser.get_line_at(1.0) is None
    line = parser.get_line_at(6.0)
    assert line is not None
    assert "Yesterday" in line.text


def test_get_lyrics_window_centered():
    lines_lrc = "\n".join(f"[00:{i:02d}.00]Line {i}" for i in range(10))
    parser = LRCParser(lines_lrc)

    # In the middle (Line 5 active)
    active_idx, window = parser.get_lyrics_window(5.0, window_size=5)
    assert len(window) == 5
    assert active_idx == 2  # Window: [Line 3, Line 4, Line 5, Line 6, Line 7]
    assert window[active_idx].text == "Line 5"


def test_get_lyrics_window_boundaries():
    lines_lrc = "\n".join(f"[00:{i:02d}.00]Line {i}" for i in range(10))
    parser = LRCParser(lines_lrc)

    # Before first line
    active_idx, window = parser.get_lyrics_window(0.0, window_size=5)
    # Line 0 starts at 0.0, so at 0.0 line 0 is active
    assert active_idx == 0
    assert window[0].text == "Line 0"

    # Before any lines (negative time)
    active_idx, window = parser.get_lyrics_window(-5.0, window_size=5)
    assert active_idx == -1
    assert len(window) == 5
    assert window[0].text == "Line 0"

    # Near the end (Line 9 active)
    active_idx, window = parser.get_lyrics_window(9.0, window_size=5)
    assert len(window) == 5
    assert active_idx == 4
    assert window[active_idx].text == "Line 9"


def test_get_lyrics_window_small_song():
    lrc = "[00:01.00]One\n[00:02.00]Two"
    parser = LRCParser(lrc)
    active_idx, window = parser.get_lyrics_window(1.5, window_size=5)
    assert len(window) == 2
    assert active_idx == 0
    assert window[active_idx].text == "One"


def test_parse_from_dict_and_helper():
    payload = {
        "trackName": "Yesterday",
        "artistName": "The Beatles",
        "syncedLyrics": "[00:05.00]Yesterday",
    }
    parser = parse_lrc(payload)
    assert parser.title == "Yesterday"
    assert parser.artist == "The Beatles"
    assert len(parser) == 1
    assert parser[0].text == "Yesterday"
    assert parser[0].time == 5.0


def test_empty_parser():
    parser = LRCParser("")
    assert len(parser) == 0
    assert parser.get_line_index_at(10.0) == -1
    assert parser.get_lyrics_window(10.0) == (-1, [])
