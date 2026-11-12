from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
import pytest
from src.gui.lyrics_window import LyricsWindow

SAMPLE_LRC = """[ti:Test Track]
[ar:Test Artist]
[00:00.00]Line 0: intro
[00:05.00]Line 1: first verse
[00:10.00]Line 2: second verse
"""


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_lyrics_window_init(qapp):
    win = LyricsWindow(always_on_top=True)
    assert bool(win.windowFlags() & Qt.FramelessWindowHint)
    assert bool(win.windowFlags() & Qt.WindowStaysOnTopHint)
    assert win.testAttribute(Qt.WA_TranslucentBackground)
    assert win.minimumWidth() >= 320
    assert win.minimumHeight() >= 140
    win.close()


def test_lyrics_window_no_top(qapp):
    win = LyricsWindow(always_on_top=False)
    assert bool(win.windowFlags() & Qt.FramelessWindowHint)
    assert not bool(win.windowFlags() & Qt.WindowStaysOnTopHint)
    win.close()


def test_lock_mode_toggle(qapp):
    win = LyricsWindow()
    assert not win._is_locked
    assert not bool(win.windowFlags() & Qt.WindowTransparentForInput)

    # Toggle lock on
    win.toggle_lock(True)
    assert win._is_locked
    assert bool(win.windowFlags() & Qt.WindowTransparentForInput)

    # Toggle lock off
    win.toggle_lock(False)
    assert not win._is_locked
    assert not bool(win.windowFlags() & Qt.WindowTransparentForInput)
    win.close()


def test_always_on_top_toggle(qapp):
    win = LyricsWindow(always_on_top=True)
    assert bool(win.windowFlags() & Qt.WindowStaysOnTopHint)

    win.toggle_always_on_top(False)
    assert not win._always_on_top
    assert not bool(win.windowFlags() & Qt.WindowStaysOnTopHint)

    win.toggle_always_on_top(True)
    assert win._always_on_top
    assert bool(win.windowFlags() & Qt.WindowStaysOnTopHint)
    win.close()


def test_offset_controls(qapp):
    win = LyricsWindow()
    assert win._manual_offset_ms == 0.0
    assert win.offset_label.text() == "[Offset: +0.0s]"

    win.adjust_offset(500)
    assert win._manual_offset_ms == 500.0
    assert win.offset_label.text() == "[Offset: +0.5s]"

    win.adjust_offset(-1000)
    assert win._manual_offset_ms == -500.0
    assert win.offset_label.text() == "[Offset: -0.5s]"

    win.reset_offset()
    assert win._manual_offset_ms == 0.0
    assert win.offset_label.text() == "[Offset: +0.0s]"
    win.close()


def test_lyrics_loading_and_scrolling(qapp):
    win = LyricsWindow()
    win.load_lyrics_direct(SAMPLE_LRC, title="Test Track", artist="Test Artist")

    assert len(win.parser.lines) == 3
    assert len(win.lyrics_display.lines) == 3
    assert win.title_artist_label.text() == "Test Track • Test Artist"

    # Playback at 2 seconds (Line 0 active)
    win.update_playback({
        "type": "playback_update",
        "title": "Test Track",
        "artist": "Test Artist",
        "position": 2.0,
        "duration": 60.0,
        "isPaused": False,
    })
    win._on_anim_tick()
    assert win._active_idx == 0

    # Playback at 7 seconds (Line 1 active)
    win.update_playback({
        "type": "playback_update",
        "title": "Test Track",
        "artist": "Test Artist",
        "position": 7.0,
        "duration": 60.0,
        "isPaused": False,
    })
    win._on_anim_tick()
    assert win._active_idx == 1

    win.close()


def test_minimize_to_tray(qapp):
    win = LyricsWindow()
    win.show()
    assert win.isVisible()

    # Minimize to tray
    win.minimize_to_tray()
    assert win.isHidden()

    # Restore from tray
    win.restore_from_tray()
    assert win.isVisible()
    win.close()


def test_transparent_background_toggle(qapp):
    win = LyricsWindow(transparent_bg=False)
    assert not win._transparent_bg
    assert "rgba(18, 18, 18, 210)" in win.container.styleSheet()

    # Toggle to transparent background (text only)
    win.set_transparent_background(True)
    assert win._transparent_bg
    assert "background-color: transparent" in win.container.styleSheet()
    assert win.btn_bg_mode.text() == "🎨 Clear"

    # Toggle back to glass background
    win.set_transparent_background(False)
    assert not win._transparent_bg
    assert "rgba(18, 18, 18, 210)" in win.container.styleSheet()
    assert win.btn_bg_mode.text() == "🎨 Glass"
    win.close()


def test_word_wrap_and_layout_computation(qapp):
    win = LyricsWindow()
    long_lrc = """[00:01.00]This is an extraordinarily long lyric line designed specifically to test word wrapping across multiple lines in MiniLyrics without horizontal clipping or truncating
[00:05.00]Short line
"""
    win.load_lyrics_direct(long_lrc, title="Long Song", artist="Artist")
    win.resize(400, 200)
    heights, y_positions = win.lyrics_display.compute_layout()

    assert len(heights) == 2
    assert len(y_positions) == 2
    # The long wrapped line must be allocated significantly more vertical height than the short line
    assert heights[0] > heights[1]
    assert y_positions[1] == y_positions[0] + heights[0]
    win.close()


def test_adaptive_font_sizing_on_resize(qapp):
    win = LyricsWindow()
    display = win.lyrics_display

    # Small window size
    display.update_font_sizes(380, 150)
    small_normal = display.font_normal.pointSize()
    small_active = display.font_active.pointSize()

    # Large window size
    display.update_font_sizes(1100, 480)
    large_normal = display.font_normal.pointSize()
    large_active = display.font_active.pointSize()

    assert large_normal > small_normal
    assert large_active > small_active
    win.close()


def test_line_change_layout_invariance(qapp):
    win = LyricsWindow()
    win.load_lyrics_direct(SAMPLE_LRC, title="Test", artist="Test")
    win.resize(600, 240)

    # When line 0 is active
    win.lyrics_display.active_idx = 0
    heights_0, y_pos_0 = win.lyrics_display.compute_layout()

    # When line 1 is active
    win.lyrics_display.active_idx = 1
    heights_1, y_pos_1 = win.lyrics_display.compute_layout()

    # Layout must be 100% invariant across line changes so text never shifts, jerks, or blinks
    assert heights_0 == heights_1
    assert y_pos_0 == y_pos_1
    win.close()


def test_monotonic_forward_clock_no_oscillation(qapp):
    win = LyricsWindow()
    # Line 0 is at 5.00s, Line 1 is at 5.20s
    lrc = """[00:05.00]Line 0
[00:05.20]Line 1
[00:08.00]Line 2
"""
    win.load_lyrics_direct(lrc, title="Clock Test", artist="Artist")

    # Spotify reports position 5.0s
    win.update_playback({
        "type": "playback_update",
        "title": "Clock Test",
        "artist": "Artist",
        "position": 5.0,
        "duration": 60.0,
        "isPaused": False,
    })
    win._on_anim_tick()
    assert win._active_idx == 0

    # Smooth clock advances 250ms forward: 5.0 + 0.25 = 5.25s (Line 1 active)
    import time
    win._last_update_monotonic = time.monotonic() - 0.25
    win._on_anim_tick()
    assert win._active_idx == 1

    # Spotify sends coarse 5.0s again (because DOM only shows whole seconds)
    win.update_playback({
        "type": "playback_update",
        "title": "Clock Test",
        "artist": "Artist",
        "position": 5.0,
        "duration": 60.0,
        "isPaused": False,
    })
    win._on_anim_tick()
    # Clock must NOT yank backwards! Line 1 must stay active and not oscillate back to Line 0!
    assert win._active_idx == 1
    win.close()


def test_collapse_and_expand_bubble(qapp):
    win = LyricsWindow()
    win.show()
    assert win.isVisible()
    assert not win.bubble.isVisible()

    # Collapse to bubble
    win.collapse_to_bubble()
    assert not win.isVisible()
    assert win.bubble.isVisible()

    # Expand from bubble
    win.expand_from_bubble()
    assert win.isVisible()
    assert not win.bubble.isVisible()

    # Toggle bubble
    win.toggle_bubble()
    assert not win.isVisible()
    assert win.bubble.isVisible()

    win.toggle_bubble()
    assert win.isVisible()
    assert not win.bubble.isVisible()

    win.close()


def test_window_controls_present(qapp):
    win = LyricsWindow()
    assert win.btn_bubble is not None
    assert win.btn_minimize is not None
    assert win.btn_close is not None
    assert win.btn_bubble.text() == "🫧"
    assert win.btn_minimize.text() == "—"
    win.close()

