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


def test_opacity_slider(qapp):
    win = LyricsWindow()
    win.opacity_slider.setValue(80)
    assert round(win.windowOpacity(), 2) == 0.8
    win.close()
