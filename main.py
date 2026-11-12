"""MiniLyrics Main Application Entrypoint.

Initializes the transparent floating lyrics window, starts the WebSocket server,
and connects to Spotify playback updates.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from src.core.lrclib_client import LRCLibClient
from src.gui.lyrics_window import LyricsWindow
from src.server.ws_server import WebSocketServer

DEMO_LRC = """[ti:Bohemian Rhapsody]
[ar:Queen]
[al:A Night at the Opera]
[length:05:54]
[00:00.00]Is this the real life? Is this just fantasy?
[00:05.50]Caught in a landslide, no escape from reality
[00:11.80]Open your eyes, look up to the skies and see
[00:17.50]I'm just a poor boy, I need no sympathy
[00:22.50]Because I'm easy come, easy go, little high, little low
[00:29.00]Any way the wind blows doesn't really matter to me, to me
[00:38.00]Mama, just killed a man
[00:43.50]Put a gun against his head, pulled my trigger, now he's dead
[00:50.00]Mama, life had just begun
[00:55.50]But now I've gone and thrown it all away
[01:02.00]Mama, ooh, didn't mean to make you cry
[01:09.50]If I'm not back again this time tomorrow
[01:14.50]Carry on, carry on as if nothing really matters
[01:23.00]Too late, my time has come
[01:28.00]Sends shivers down my spine, body's aching all the time
[01:34.50]Goodbye, everybody, I've got to go
[01:40.00]Gotta leave you all behind and face the truth
[01:46.50]Mama, ooh, I don't wanna die
[01:52.50]I sometimes wish I'd never been born at all
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MiniLyrics Desktop App")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with built-in mock song and lyrics for instant visual verification",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="WebSocket port (default: 8765)",
    )
    parser.add_argument(
        "--no-top",
        action="store_true",
        help="Disable always-on-top window hint",
    )
    parser.add_argument(
        "--transparent-bg",
        "--clear-bg",
        action="store_true",
        help="Start with 100%% transparent background (text only)",
    )
    return parser.parse_args(argv)


class DemoRunner:
    """Simulates song playback for visual verification in demo mode."""

    def __init__(self, window: LyricsWindow, step: float = 0.25) -> None:
        self.window = window
        self.step = step
        self.position = 0.0
        self.duration = 354.0
        self.timer = QTimer()
        self.timer.setInterval(int(step * 1000))
        self.timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.window.load_lyrics_direct(DEMO_LRC, title="Bohemian Rhapsody", artist="Queen")
        self.timer.start()
        self._emit()

    def _tick(self) -> None:
        self.position += self.step
        if self.position > self.duration:
            self.position = 0.0
        self._emit()

    def _emit(self) -> None:
        self.window.update_playback({
            "type": "playback_update",
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "album": "A Night at the Opera",
            "duration": self.duration,
            "position": round(self.position, 2),
            "isPaused": not self.timer.isActive(),
        })

    def handle_command(self, action: str, **kwargs: Any) -> None:
        if action == "play_pause":
            if self.timer.isActive():
                self.timer.stop()
            else:
                self.timer.start()
            self._emit()
        elif action == "next":
            self.position = min(self.position + 15.0, self.duration)
            self._emit()
        elif action == "prev":
            self.position = max(0.0, self.position - 15.0)
            self._emit()
        elif action == "seek":
            if "position" in kwargs:
                self.position = float(kwargs["position"])
                self._emit()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv if argv is None else ["minilyrics"] + argv)
    app.setApplicationName("MiniLyrics")

    client = LRCLibClient()
    server = WebSocketServer(port=args.port)
    window = LyricsWindow(
        lrclib_client=client,
        ws_server=server,
        always_on_top=not args.no_top,
        transparent_bg=args.transparent_bg,
    )

    server.playback_updated.connect(window.update_playback)
    server.start()

    # Clean shutdown on application exit
    app.aboutToQuit.connect(server.stop)

    # Allow SIGINT (Ctrl+C) in terminal to terminate the Qt app cleanly
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    sigint_timer = QTimer()
    sigint_timer.setInterval(500)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start()

    demo_runner: DemoRunner | None = None
    if args.demo:
        demo_runner = DemoRunner(window)
        window.demo_runner = demo_runner
        demo_runner.start()

    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
