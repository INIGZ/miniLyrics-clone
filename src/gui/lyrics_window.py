"""MiniLyrics Transparent Floating Lyrics Window.

Displays synchronized desktop lyrics with click-through mode, smooth scrolling,
and LRCLib integration.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from PyQt5.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QShortcut,
    QSizeGrip,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from src.core.lrc_parser import LRCParser, LyricLine
from src.core.lrclib_client import LRCLibClient

logger = logging.getLogger(__name__)


def create_default_tray_icon() -> QIcon:
    """Generate a clean green music note tray icon in-memory."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#1DB954"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI", 14, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "♪")
    painter.end()
    return QIcon(pixmap)


class LyricsDisplay(QWidget):
    """Custom-painted smooth-scrolling multi-line lyrics display."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lines: list[LyricLine] = []
        self.status_text: str = "Waiting for Spotify playback..."
        self.active_idx: int = -1
        self.scroll_y: float = 0.0

        self.font_active = QFont("Segoe UI", 18, QFont.Bold)
        self.font_normal = QFont("Segoe UI", 13, QFont.Normal)
        self.color_active = QColor("#1DB954")
        self.color_prev = QColor(255, 255, 255, 120)
        self.color_next = QColor(255, 255, 255, 170)

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_lines(self, lines: list[LyricLine], status_text: str = "") -> None:
        self.lines = list(lines)
        self.status_text = status_text
        self.update()

    def set_status(self, text: str) -> None:
        self.status_text = text
        self.lines.clear()
        self.update()

    def mousePressEvent(self, event) -> None:
        # Delegate mouse press to parent LyricsWindow for dragging
        window = self.window()
        if window and hasattr(window, "start_drag"):
            window.start_drag(event)
        else:
            event.ignore()

    def mouseMoveEvent(self, event) -> None:
        window = self.window()
        if window and hasattr(window, "handle_drag_move"):
            window.handle_drag_move(event)
        else:
            event.ignore()

    def mouseReleaseEvent(self, event) -> None:
        window = self.window()
        if window and hasattr(window, "end_drag"):
            window.end_drag(event)
        else:
            event.ignore()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        cy = h / 2.0

        if not self.lines:
            painter.setFont(self.font_normal)
            painter.setPen(QColor(255, 255, 255, 140))
            painter.drawText(
                QRectF(16, 0, w - 32, h),
                Qt.AlignCenter | Qt.TextWordWrap,
                self.status_text or "Waiting for Spotify playback...",
            )
            return

        # Keep 5-7 lines visible based on available height
        line_height = max(34.0, min(44.0, h / 6.0))

        for i, line in enumerate(self.lines):
            line_y = cy + (i * line_height - self.scroll_y)

            # Cull lines outside viewport
            if line_y + line_height < 0 or line_y - line_height > h:
                continue

            if i == self.active_idx:
                painter.setFont(self.font_active)
                painter.setPen(self.color_active)
                fm = QFontMetrics(self.font_active)
            elif i < self.active_idx:
                painter.setFont(self.font_normal)
                painter.setPen(self.color_prev)
                fm = QFontMetrics(self.font_normal)
            else:
                painter.setFont(self.font_normal)
                painter.setPen(self.color_next)
                fm = QFontMetrics(self.font_normal)

            raw_text = line.text if line.text else "• • •"
            text = fm.elidedText(raw_text, Qt.ElideRight, int(w - 36))
            rect = QRectF(18, line_y - line_height / 2.0, w - 36, line_height)
            painter.drawText(rect, Qt.AlignCenter | Qt.TextSingleLine, text)


class LyricsWindow(QWidget):
    """Transparent always-on-top lyrics window with click-through mode."""

    lyrics_fetched_signal = pyqtSignal(str, str, object)

    def __init__(
        self,
        lrclib_client: LRCLibClient | None = None,
        always_on_top: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.lrclib_client = lrclib_client or LRCLibClient()
        self._always_on_top = always_on_top
        self._is_locked = False
        self._drag_pos: QPoint | None = None

        # Playback and time interpolation state
        self.parser: LRCParser = LRCParser()
        self._current_track_key: tuple[str, str] = ("", "")
        self._playback_pos: float = 0.0
        self._duration: float = 0.0
        self._is_paused: bool = True
        self._last_update_monotonic: float = time.monotonic()
        self._current_time: float = 0.0
        self._manual_offset_ms: float = 0.0
        self._active_idx: int = -1
        self._current_scroll_y: float = 0.0
        self._target_scroll_y: float = 0.0

        # Window styling and flags
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.resize(680, 240)
        self.setMinimumSize(360, 140)

        self._init_ui()
        self._init_tray()
        self._init_shortcuts()

        # Connect background lyrics fetcher
        self.lyrics_fetched_signal.connect(self._on_lyrics_fetched)

        # 30ms timer for silky-smooth time interpolation and scrolling
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

        # Initial auto-hide timer for header bar
        self._header_timer = QTimer(self)
        self._header_timer.setSingleShot(True)
        self._header_timer.timeout.connect(self._on_header_timer_timeout)
        self.header_bar.show()
        self._header_timer.start(2000)

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Container frame with dark translucent background
        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setMouseTracking(True)
        self.container.setStyleSheet("""
            #container {
                background-color: rgba(18, 18, 18, 210);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 12px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 25);
                border: 1px solid rgba(255, 255, 255, 45);
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 500;
                padding: 2px 7px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 45);
                border-color: rgba(255, 255, 255, 75);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 70);
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 40);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #1DB954;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 10px;
                margin-top: -3px;
                margin-bottom: -3px;
                border-radius: 5px;
            }
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(14, 10, 14, 10)
        container_layout.setSpacing(6)

        # Header Bar
        self.header_bar = QWidget(self.container)
        self.header_bar.setObjectName("header_bar")
        self.header_bar.setMouseTracking(True)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.title_artist_label = QLabel("MiniLyrics", self.header_bar)
        self.title_artist_label.setStyleSheet("color: rgba(255, 255, 255, 220); font-weight: bold; font-size: 11px;")
        self.title_artist_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header_layout.addWidget(self.title_artist_label)

        self.offset_label = QLabel("[Offset: +0.0s]", self.header_bar)
        self.offset_label.setStyleSheet("color: rgba(255, 255, 255, 180); font-size: 11px; font-family: monospace;")
        header_layout.addWidget(self.offset_label)

        self.btn_sub_offset = QPushButton("-0.5s", self.header_bar)
        self.btn_sub_offset.setToolTip("Decrease offset by 0.5s")
        self.btn_sub_offset.clicked.connect(lambda: self.adjust_offset(-500))
        header_layout.addWidget(self.btn_sub_offset)

        self.btn_add_offset = QPushButton("+0.5s", self.header_bar)
        self.btn_add_offset.setToolTip("Increase offset by 0.5s")
        self.btn_add_offset.clicked.connect(lambda: self.adjust_offset(500))
        header_layout.addWidget(self.btn_add_offset)

        self.btn_lock = QPushButton("🔒 Lock", self.header_bar)
        self.btn_lock.setToolTip("Lock click-through mode (Ctrl+L)")
        self.btn_lock.clicked.connect(lambda: self.toggle_lock())
        header_layout.addWidget(self.btn_lock)

        self.opacity_slider = QSlider(Qt.Horizontal, self.header_bar)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(65)
        self.opacity_slider.setToolTip("Window Opacity (30% - 100%)")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        header_layout.addWidget(self.opacity_slider)

        self.btn_close = QPushButton("✕", self.header_bar)
        self.btn_close.setToolTip("Close MiniLyrics")
        self.btn_close.setFixedWidth(24)
        self.btn_close.clicked.connect(self.close)
        header_layout.addWidget(self.btn_close)

        container_layout.addWidget(self.header_bar)

        # Lyrics Display
        self.lyrics_display = LyricsDisplay(self.container)
        container_layout.addWidget(self.lyrics_display, stretch=1)

        root_layout.addWidget(self.container)

        # Bottom-right resize grip
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("background: transparent; width: 14px; height: 14px;")
        self.size_grip.raise_()

    def _init_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        self.tray_icon = QSystemTrayIcon(create_default_tray_icon(), self)
        self.tray_icon.setToolTip("MiniLyrics")

        tray_menu = QMenu()
        self.action_lock = QAction("Lock / Unlock Click-Through", self)
        self.action_lock.setCheckable(True)
        self.action_lock.setChecked(self._is_locked)
        self.action_lock.triggered.connect(lambda: self.toggle_lock())
        tray_menu.addAction(self.action_lock)

        self.action_always_on_top = QAction("Always on Top", self)
        self.action_always_on_top.setCheckable(True)
        self.action_always_on_top.setChecked(self._always_on_top)
        self.action_always_on_top.triggered.connect(self.toggle_always_on_top)
        tray_menu.addAction(self.action_always_on_top)

        self.action_reset_offset = QAction("Reset Offset", self)
        self.action_reset_offset.triggered.connect(self.reset_offset)
        tray_menu.addAction(self.action_reset_offset)

        tray_menu.addSeparator()

        self.action_quit = QAction("Quit", self)
        self.action_quit.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(self.action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _init_shortcuts(self) -> None:
        self.lock_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self.lock_shortcut.activated.connect(lambda: self.toggle_lock())
        self.sub_offset_shortcut = QShortcut(QKeySequence("["), self)
        self.sub_offset_shortcut.activated.connect(lambda: self.adjust_offset(-500))
        self.add_offset_shortcut = QShortcut(QKeySequence("]"), self)
        self.add_offset_shortcut.activated.connect(lambda: self.adjust_offset(500))

    def _on_opacity_changed(self, value: int) -> None:
        self.setWindowOpacity(value / 100.0)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_lock()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "size_grip"):
            self.size_grip.move(
                self.width() - self.size_grip.width() - 4,
                self.height() - self.size_grip.height() - 4,
            )
            self.size_grip.raise_()

    # Drag and movement handling
    def start_drag(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._is_locked:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def handle_drag_move(self, event) -> None:
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
        elif not self._is_locked:
            self._show_header()

    def end_drag(self, event) -> None:
        self._drag_pos = None

    def mousePressEvent(self, event) -> None:
        self.start_drag(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self.handle_drag_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.end_drag(event)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        if not self._is_locked:
            self._show_header()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._is_locked and not self.opacity_slider.isSliderDown():
            self.header_bar.hide()
            self._header_timer.stop()
        super().leaveEvent(event)

    def _show_header(self) -> None:
        if not self.header_bar.isVisible():
            self.header_bar.show()
        self._header_timer.start(2000)

    def _on_header_timer_timeout(self) -> None:
        if self.opacity_slider.isSliderDown():
            self._header_timer.start(2000)
            return

        # Auto-hide if mouse has left the window or is idle
        if not self.rect().contains(self.mapFromGlobal(self.cursor().pos())):
            self.header_bar.hide()
        elif not self.header_bar.rect().contains(self.header_bar.mapFromGlobal(self.cursor().pos())):
            self.header_bar.hide()
        else:
            self._header_timer.start(2000)

    # Click-Through / Lock mode
    def toggle_lock(self, locked: bool | None = None) -> None:
        if locked is None:
            self._is_locked = not self._is_locked
        else:
            self._is_locked = bool(locked)

        self.setWindowFlag(Qt.WindowTransparentForInput, self._is_locked)
        self.show()

        if hasattr(self, "action_lock"):
            self.action_lock.setChecked(self._is_locked)

        if self._is_locked:
            self.header_bar.hide()
            self.btn_lock.setText("🔒 Locked")
            if self.tray_icon and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    "MiniLyrics Click-Through Enabled",
                    "Clicks pass straight through. Use system tray icon to unlock.",
                    QSystemTrayIcon.Information,
                    2000,
                )
        else:
            self.btn_lock.setText("🔒 Lock")
            self._show_header()

    # Always-on-top toggle
    def toggle_always_on_top(self, enabled: bool | None = None) -> None:
        if enabled is None:
            self._always_on_top = not self._always_on_top
        else:
            self._always_on_top = bool(enabled)

        self.setWindowFlag(Qt.WindowStaysOnTopHint, self._always_on_top)
        self.show()
        if hasattr(self, "action_always_on_top"):
            self.action_always_on_top.setChecked(self._always_on_top)

    # Offset controls
    def adjust_offset(self, delta_ms: float) -> None:
        self._manual_offset_ms += delta_ms
        self._update_offset_label()

    def reset_offset(self) -> None:
        self._manual_offset_ms = 0.0
        self._update_offset_label()

    def _update_offset_label(self) -> None:
        secs = self._manual_offset_ms / 1000.0
        sign = "+" if secs >= 0 else ""
        self.offset_label.setText(f"[Offset: {sign}{secs:.1f}s]")

    # High frequency 30ms animation loop
    def _on_anim_tick(self) -> None:
        now = time.monotonic()
        if not self._is_paused and self._duration > 0:
            elapsed = now - self._last_update_monotonic
            self._current_time = min(self._playback_pos + elapsed, self._duration)
        else:
            self._current_time = self._playback_pos

        if self.parser and len(self.parser.lines) > 0:
            active_idx = self.parser.get_line_index_at(self._current_time, self._manual_offset_ms)
            line_height = max(34.0, min(44.0, self.lyrics_display.height() / 6.0))

            if active_idx != self._active_idx:
                self._active_idx = active_idx
                self.lyrics_display.active_idx = active_idx
                target_idx = max(0, active_idx) if active_idx >= 0 else 0
                self._target_scroll_y = target_idx * line_height

            # Smooth exponential ease-out scrolling
            diff = self._target_scroll_y - self._current_scroll_y
            scrolling = abs(diff) > 0.1
            if scrolling:
                self._current_scroll_y += diff * 0.15
            else:
                self._current_scroll_y = self._target_scroll_y

            if scrolling or active_idx != self.lyrics_display.active_idx or abs(self.lyrics_display.scroll_y - self._current_scroll_y) > 0.05:
                self.lyrics_display.scroll_y = self._current_scroll_y
                self.lyrics_display.update()

    # Playback updates & lyrics fetching
    def update_playback(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return

        title = str(payload.get("title", "") or "").strip()
        artist = str(payload.get("artist", "") or "").strip()
        album = str(payload.get("album", "") or "").strip()
        duration = float(payload.get("duration", 0.0) or 0.0)
        position = float(payload.get("position", 0.0) or 0.0)
        is_paused = bool(payload.get("isPaused", False))

        track_key = (title, artist)
        if track_key != self._current_track_key:
            self._current_track_key = track_key
            if title:
                header_text = f"{title} • {artist}" if artist else title
                self.title_artist_label.setText(header_text)
                self.title_artist_label.setToolTip(header_text)
                self._fetch_lyrics(title, artist, album, duration)
            else:
                self.title_artist_label.setText("MiniLyrics")
                self.lyrics_display.set_status("Waiting for Spotify playback...")
                self.parser = LRCParser()
                self._active_idx = -1
                self.lyrics_display.active_idx = -1

        self._playback_pos = position
        self._duration = duration
        self._is_paused = is_paused
        self._last_update_monotonic = time.monotonic()

    def _fetch_lyrics(self, title: str, artist: str, album: str, duration: float) -> None:
        self.lyrics_display.set_status(f"Searching lyrics for {title}...")

        def worker() -> None:
            try:
                data = self.lrclib_client.get_lyrics(
                    track_name=title,
                    artist_name=artist,
                    album_name=album,
                    duration=duration,
                )
            except Exception as e:
                logger.debug("Lyrics fetch error: %s", e)
                data = None
            self.lyrics_fetched_signal.emit(title, artist, data or {})

        threading.Thread(target=worker, daemon=True).start()

    def _on_lyrics_fetched(self, title: str, artist: str, data: dict[str, Any]) -> None:
        if (title, artist) != self._current_track_key:
            return

        if data and (data.get("syncedLyrics") or data.get("plainLyrics")):
            self.parser = LRCParser(data)
            if len(self.parser.lines) > 0:
                self.lyrics_display.set_lines(self.parser.lines)
            elif data.get("plainLyrics"):
                plain_lines = [
                    LyricLine(timestamp=0.0, text=line)
                    for line in data["plainLyrics"].splitlines()
                    if line.strip()
                ]
                self.lyrics_display.set_lines(
                    plain_lines, status_text="Synced lyrics unavailable (showing plain text)"
                )
            else:
                self.lyrics_display.set_lines([], status_text=f"No lyrics found for {title}")
        else:
            self.parser = LRCParser()
            self.lyrics_display.set_lines([], status_text=f"No lyrics found for {title}")

        self._active_idx = -1
        self._current_scroll_y = 0.0
        self._target_scroll_y = 0.0
        self.lyrics_display.active_idx = -1
        self.lyrics_display.scroll_y = 0.0

    def load_lyrics_direct(self, lrc_content: str | dict[str, Any], title: str = "", artist: str = "") -> None:
        """Directly load lyrics content (useful for demo mode and tests)."""
        if title:
            self._current_track_key = (title, artist)
            header_text = f"{title} • {artist}" if artist else title
            self.title_artist_label.setText(header_text)
        self.parser = LRCParser(lrc_content)
        self.lyrics_display.set_lines(self.parser.lines)
        self._active_idx = -1
        self._current_scroll_y = 0.0
        self._target_scroll_y = 0.0
        self.lyrics_display.active_idx = -1
        self.lyrics_display.scroll_y = 0.0
