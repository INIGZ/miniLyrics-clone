"""MiniLyrics Transparent Floating Lyrics Window.

Displays synchronized desktop lyrics with click-through mode, smooth scrolling,
and LRCLib integration.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from PyQt5.QtCore import QEvent, QPoint, QRectF, Qt, QTimer, pyqtSignal
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


def wrap_text_to_lines(fm: QFontMetrics, text: str, max_width: int) -> list[str]:
    """Break text into word-wrapped lines using font metrics."""
    if not text:
        return ["• • •"]
    words = text.split(" ")
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        test = " ".join(cur + [word])
        if fm.horizontalAdvance(test) <= max_width or not cur:
            cur.append(word)
        else:
            lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines


class LyricsDisplay(QWidget):
    """Custom-painted smooth-scrolling multi-line lyrics display with word-wrap and prominent active line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lines: list[LyricLine] = []
        self.status_text: str = "Waiting for Spotify playback..."
        self.active_idx: int = -1
        self.scroll_y: float = 0.0

        # Visual hierarchy: active line is larger and bolder!
        self.font_active = QFont("Segoe UI", 18, QFont.Bold)
        self.font_normal = QFont("Segoe UI", 13, QFont.Normal)
        self.color_active = QColor("#1DB954")
        self.color_prev = QColor(255, 255, 255, 110)
        self.color_next = QColor(255, 255, 255, 160)

        self._cached_layout: tuple[list[float], list[float]] | None = None
        self._cached_sublines: list[list[str]] = []
        self._cached_w: int = -1

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def update_font_sizes(self, w: int, h: int) -> None:
        """Dynamically adapt font sizes based on window dimensions."""
        scale = (w / 510.0) * 0.40 + (h / 120.0) * 0.60
        normal_pt = max(10, min(28, int(13 * scale)))
        active_pt = max(14, min(38, int(17 * scale)))
        changed = False
        if self.font_normal.pointSize() != normal_pt:
            self.font_normal.setPointSize(normal_pt)
            changed = True
        if self.font_active.pointSize() != active_pt:
            self.font_active.setPointSize(active_pt)
            changed = True
        if changed:
            self._cached_layout = None

    def compute_layout(self) -> tuple[list[float], list[float]]:
        """Compute line heights and cumulative top y-offsets with pre-wrapped sublines.
        Uses font_active bounds to guarantee slot stability and zero re-wrapping pops."""
        if not self.lines:
            self._cached_sublines = []
            return [], []

        w = int(max(100.0, float(self.width() - 40)))
        if self._cached_layout is not None and self._cached_w == w and len(self._cached_layout[0]) == len(self.lines):
            return self._cached_layout

        fm_active = QFontMetrics(self.font_active)
        heights: list[float] = []
        y_positions: list[float] = []
        all_sublines: list[list[str]] = []
        cur_y = 0.0

        for line in self.lines:
            text = line.text.strip() if line.text else "• • •"
            sublines = wrap_text_to_lines(fm_active, text, w)
            all_sublines.append(sublines)
            sub_h = float(fm_active.height())
            line_h = len(sublines) * (sub_h + 4.0) + 14.0
            heights.append(line_h)
            y_positions.append(cur_y)
            cur_y += line_h

        self._cached_layout = (heights, y_positions)
        self._cached_sublines = all_sublines
        self._cached_w = w
        return self._cached_layout

    def set_lines(self, lines: list[LyricLine], status_text: str = "") -> None:
        self.lines = list(lines)
        self.status_text = status_text
        self._cached_layout = None
        self._cached_sublines = []
        self.update()

    def set_status(self, text: str) -> None:
        self.status_text = text
        self.lines.clear()
        self._cached_layout = None
        self._cached_sublines = []
        self.update()

    def get_line_index_at_y(self, y: float) -> int:
        """Find the lyric line index corresponding to vertical widget coordinate y."""
        if not self.lines:
            return -1
        cy = self.height() / 2.0
        heights, y_positions = self.compute_layout()
        for i in range(len(self.lines)):
            top_y = cy + (y_positions[i] - self.scroll_y)
            if top_y <= y <= top_y + heights[i]:
                return i
        return -1

    def mousePressEvent(self, event) -> None:
        self._press_pos = event.pos()
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

        # Click-to-seek: if mouse was clicked without dragging, seek Spotify to clicked lyric
        if event.button() == Qt.LeftButton and hasattr(self, "_press_pos") and self._press_pos is not None:
            dist = (event.pos() - self._press_pos).manhattanLength()
            if dist < 6:
                idx = self.get_line_index_at_y(event.pos().y())
                if 0 <= idx < len(self.lines):
                    line = self.lines[idx]
                    if hasattr(window, "send_command"):
                        window.send_command("seek", position=line.timestamp)
        self._press_pos = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        cy = h / 2.0

        self.update_font_sizes(w, h)

        if not self.lines:
            painter.setFont(self.font_normal)
            status_text = self.status_text or "Waiting for Spotify playback..."
            status_rect = QRectF(16, 0, w - 32, h)
            # Crisp black outline around status text
            painter.setPen(QColor(0, 0, 0, 255))
            for dx, dy in ((-1.5, 0), (1.5, 0), (0, -1.5), (0, 1.5), (-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)):
                painter.drawText(status_rect.translated(dx, dy), Qt.AlignCenter | Qt.TextWordWrap, status_text)
            painter.setPen(QColor(255, 255, 255, 220))
            painter.drawText(status_rect, Qt.AlignCenter | Qt.TextWordWrap, status_text)
            return

        heights, y_positions = self.compute_layout()
        all_sublines = self._cached_sublines
        content_w = max(100.0, float(w - 40))

        fm_active = QFontMetrics(self.font_active)
        fm_normal = QFontMetrics(self.font_normal)

        for i, line in enumerate(self.lines):
            line_h = heights[i]
            top_y = cy + (y_positions[i] - self.scroll_y)

            # Cull lines outside viewport
            if top_y + line_h < -20 or top_y > h + 20:
                continue

            sublines = all_sublines[i] if i < len(all_sublines) else ["• • •"]
            is_active = (i == self.active_idx)

            if is_active:
                painter.setFont(self.font_active)
                text_color = self.color_active
                step_h = float(fm_active.height()) + 4.0
            else:
                painter.setFont(self.font_normal)
                text_color = self.color_prev if i < self.active_idx else self.color_next
                step_h = float(fm_normal.height()) + 4.0

            total_sub_h = len(sublines) * step_h
            start_y = top_y + (line_h - total_sub_h) / 2.0

            for s_idx, s_text in enumerate(sublines):
                sub_rect = QRectF(20, start_y + s_idx * step_h, content_w, step_h)

                # Draw crisp black outline around glyphs
                painter.setPen(QColor(0, 0, 0, 255))
                for dx, dy in ((-1.5, 0), (1.5, 0), (0, -1.5), (0, 1.5), (-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)):
                    painter.drawText(sub_rect.translated(dx, dy), Qt.AlignCenter | Qt.TextSingleLine, s_text)

                # Draw main text in center
                painter.setPen(text_color)
                painter.drawText(sub_rect, Qt.AlignCenter | Qt.TextSingleLine, s_text)


class LyricsBubble(QWidget):
    """Compact floating desktop bubble when lyrics window is collapsed."""

    def __init__(self, main_window: "LyricsWindow") -> None:
        super().__init__()
        self.main_window = main_window
        self._drag_pos: QPoint | None = None
        self._is_dragging = False

        flags = Qt.FramelessWindowHint | Qt.Tool
        if main_window._always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(52, 52)
        self.setToolTip("MiniLyrics (Click to expand, drag to move, Ctrl+M)")
        self.setCursor(Qt.PointingHandCursor)

        self.shortcut_toggle = QShortcut(QKeySequence("Ctrl+M"), self)
        self.shortcut_toggle.activated.connect(self.main_window.expand_from_bubble)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._is_dragging = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            self._is_dragging = True
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if not self._is_dragging:
                self.main_window.expand_from_bubble()
            self._drag_pos = None
            self._is_dragging = False
            event.accept()

    def contextMenuEvent(self, event) -> None:
        if hasattr(self.main_window, "tray_icon") and self.main_window.tray_icon and self.main_window.tray_icon.contextMenu():
            self.main_window.tray_icon.contextMenu().exec_(event.globalPos())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = QRectF(2, 2, 48, 48)
        # Translucent dark body with glowing Spotify green border
        painter.setBrush(QColor(18, 18, 18, 235))
        painter.setPen(QColor("#1DB954"))
        painter.drawEllipse(rect)

        # Musical note icon in center
        painter.setPen(QColor("#1DB954"))
        font = QFont("Segoe UI", 18, QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "♪")


class LyricsWindow(QWidget):
    """Transparent always-on-top lyrics window with click-through mode."""

    lyrics_fetched_signal = pyqtSignal(str, str, object)

    def __init__(
        self,
        lrclib_client: LRCLibClient | None = None,
        ws_server: Any = None,
        always_on_top: bool = True,
        transparent_bg: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.lrclib_client = lrclib_client or LRCLibClient()
        self.ws_server = ws_server
        self._always_on_top = always_on_top
        self._transparent_bg = transparent_bg
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
        self._saved_geometry = None

        # Floating bubble when collapsed
        self.bubble = LyricsBubble(self)

        # Window styling and flags
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.resize(510, 120)
        self.setMinimumSize(280, 70)

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

        # Header bar auto-hide timer (header is hidden until focused)
        self._header_timer = QTimer(self)
        self._header_timer.setSingleShot(True)
        self._header_timer.timeout.connect(self._on_header_timer_timeout)
        self.header_bar.hide()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Container frame with customizable background
        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setMouseTracking(True)
        self._apply_container_style()

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 6, 12, 6)
        container_layout.setSpacing(4)

        # Header Bar: Reshaped into 2 clean rows
        self.header_bar = QWidget(self.container)
        self.header_bar.setObjectName("header_bar")
        self.header_bar.setMouseTracking(True)
        header_vbox = QVBoxLayout(self.header_bar)
        header_vbox.setContentsMargins(8, 4, 8, 4)
        header_vbox.setSpacing(4)

        # Row 1: Track Title & Window Action Controls
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)

        self.title_artist_label = QLabel("MiniLyrics", self.header_bar)
        self.title_artist_label.setStyleSheet("color: rgba(255, 255, 255, 225); font-weight: bold; font-size: 11px;")
        self.title_artist_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row1.addWidget(self.title_artist_label)

        self.btn_bg_mode = QPushButton("🎨 Clear" if self._transparent_bg else "🎨 Glass", self.header_bar)
        self.btn_bg_mode.setToolTip("Toggle Transparent Background (Text Only) (Ctrl+B)")
        self.btn_bg_mode.clicked.connect(lambda: self.set_transparent_background(not self._transparent_bg))
        row1.addWidget(self.btn_bg_mode)

        self.btn_lock = QPushButton("🔒 Lock", self.header_bar)
        self.btn_lock.setToolTip("Lock click-through mode (Ctrl+L)")
        self.btn_lock.clicked.connect(lambda: self.toggle_lock())
        row1.addWidget(self.btn_lock)

        self.btn_bubble = QPushButton("🫧", self.header_bar)
        self.btn_bubble.setToolTip("Collapse into Floating Bubble (Ctrl+M)")
        self.btn_bubble.setFixedWidth(24)
        self.btn_bubble.clicked.connect(self.collapse_to_bubble)
        row1.addWidget(self.btn_bubble)

        self.btn_minimize = QPushButton("—", self.header_bar)
        self.btn_minimize.setToolTip("Minimize to Tray (Ctrl+N)")
        self.btn_minimize.setFixedWidth(24)
        self.btn_minimize.clicked.connect(self.minimize_to_tray)
        row1.addWidget(self.btn_minimize)

        self.btn_close = QPushButton("✕", self.header_bar)
        self.btn_close.setToolTip("Close and Exit Process (Ctrl+Q)")
        self.btn_close.setFixedWidth(24)
        self.btn_close.clicked.connect(self.quit_app)
        row1.addWidget(self.btn_close)

        header_vbox.addLayout(row1)

        # Row 2: Playback Controls & Sync Calibration
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)

        self.btn_prev = QPushButton("⏮", self.header_bar)
        self.btn_prev.setToolTip("Previous Track (Ctrl+Left)")
        self.btn_prev.setFixedWidth(26)
        self.btn_prev.clicked.connect(lambda: self.send_command("prev"))
        row2.addWidget(self.btn_prev)

        self.btn_play_pause = QPushButton("⏯", self.header_bar)
        self.btn_play_pause.setToolTip("Play / Pause (Space)")
        self.btn_play_pause.setFixedWidth(26)
        self.btn_play_pause.clicked.connect(lambda: self.send_command("play_pause"))
        row2.addWidget(self.btn_play_pause)

        self.btn_next = QPushButton("⏭", self.header_bar)
        self.btn_next.setToolTip("Next Track (Ctrl+Right)")
        self.btn_next.setFixedWidth(26)
        self.btn_next.clicked.connect(lambda: self.send_command("next"))
        row2.addWidget(self.btn_next)

        row2.addStretch(1)

        self.offset_label = QLabel("[Offset: +0.0s]", self.header_bar)
        self.offset_label.setStyleSheet("color: rgba(255, 255, 255, 180); font-size: 11px; font-family: monospace;")
        row2.addWidget(self.offset_label)

        self.btn_sub_offset = QPushButton("-0.5s", self.header_bar)
        self.btn_sub_offset.setToolTip("Decrease offset by 0.5s")
        self.btn_sub_offset.clicked.connect(lambda: self.adjust_offset(-500))
        row2.addWidget(self.btn_sub_offset)

        self.btn_add_offset = QPushButton("+0.5s", self.header_bar)
        self.btn_add_offset.setToolTip("Increase offset by 0.5s")
        self.btn_add_offset.clicked.connect(lambda: self.adjust_offset(500))
        row2.addWidget(self.btn_add_offset)

        header_vbox.addLayout(row2)

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

        self.action_transparent_bg = QAction("Transparent Background (Text Only)", self)
        self.action_transparent_bg.setCheckable(True)
        self.action_transparent_bg.setChecked(self._transparent_bg)
        self.action_transparent_bg.triggered.connect(self.set_transparent_background)
        tray_menu.addAction(self.action_transparent_bg)

        self.action_play_pause = QAction("Play / Pause", self)
        self.action_play_pause.triggered.connect(lambda: self.send_command("play_pause"))
        tray_menu.addAction(self.action_play_pause)

        self.action_next = QAction("Next Track", self)
        self.action_next.triggered.connect(lambda: self.send_command("next"))
        tray_menu.addAction(self.action_next)

        self.action_prev = QAction("Previous Track", self)
        self.action_prev.triggered.connect(lambda: self.send_command("prev"))
        tray_menu.addAction(self.action_prev)

        self.action_bubble = QAction("Collapse to Bubble / Expand", self)
        self.action_bubble.triggered.connect(self.toggle_bubble)
        tray_menu.addAction(self.action_bubble)

        self.action_minimize = QAction("Minimize to Tray", self)
        self.action_minimize.triggered.connect(self.minimize_to_tray)
        tray_menu.addAction(self.action_minimize)

        self.action_restore = QAction("Restore Window", self)
        self.action_restore.triggered.connect(self.restore_from_tray)
        tray_menu.addAction(self.action_restore)

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
        self.bg_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self.bg_shortcut.activated.connect(lambda: self.set_transparent_background(not self._transparent_bg))
        self.bubble_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.bubble_shortcut.activated.connect(self.toggle_bubble)
        self.minimize_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.minimize_shortcut.activated.connect(self.minimize_to_tray)
        self.play_shortcut = QShortcut(QKeySequence("Space"), self)
        self.play_shortcut.activated.connect(lambda: self.send_command("play_pause"))
        self.next_shortcut = QShortcut(QKeySequence("Ctrl+Right"), self)
        self.next_shortcut.activated.connect(lambda: self.send_command("next"))
        self.prev_shortcut = QShortcut(QKeySequence("Ctrl+Left"), self)
        self.prev_shortcut.activated.connect(lambda: self.send_command("prev"))
        self.quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut.activated.connect(self.quit_app)
        self.sub_offset_shortcut = QShortcut(QKeySequence("["), self)
        self.sub_offset_shortcut.activated.connect(lambda: self.adjust_offset(-500))
        self.add_offset_shortcut = QShortcut(QKeySequence("]"), self)
        self.add_offset_shortcut.activated.connect(lambda: self.adjust_offset(500))

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isHidden():
                self.restore_from_tray()
            elif self._is_locked:
                self.toggle_lock(False)
            else:
                self.toggle_lock()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "lyrics_display"):
            self.lyrics_display.update_font_sizes(self.width(), self.height())
            self.lyrics_display.update()
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

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.ActivationChange:
            if not self._is_locked:
                if self.isActiveWindow():
                    self._show_header()
                else:
                    self.header_bar.hide()
                    self._header_timer.stop()
        super().changeEvent(event)

    def focusInEvent(self, event) -> None:
        if not self._is_locked:
            self._show_header()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        if not self._is_locked:
            self.header_bar.hide()
            self._header_timer.stop()
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:
        if not self._is_locked:
            self._show_header()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._is_locked and not self.isActiveWindow():
            self.header_bar.hide()
            self._header_timer.stop()
        super().leaveEvent(event)

    def _show_header(self) -> None:
        if not self.header_bar.isVisible():
            self.header_bar.show()
        self._header_timer.start(2000)

    def _on_header_timer_timeout(self) -> None:
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

    # Transparent background toggle
    def _apply_container_style(self) -> None:
        if getattr(self, "_transparent_bg", False):
            bg_css = "background-color: transparent; border: none;"
            header_css = """
                background-color: rgba(22, 26, 32, 240);
                border: 1px solid rgba(255, 255, 255, 55);
                border-top: 1px solid rgba(255, 255, 255, 95);
                border-radius: 8px;
            """
        else:
            # Glass mode: crystal-like dark acrylic container
            bg_css = "background-color: rgba(18, 22, 28, 215); border: 1px solid rgba(255, 255, 255, 35); border-radius: 12px;"
            # Non-transparent crystal-like header bar with beveled glass highlights
            header_css = """
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(44, 52, 65, 255), stop:1 rgba(22, 27, 35, 255));
                border: 1px solid rgba(255, 255, 255, 75);
                border-top: 1px solid rgba(255, 255, 255, 140);
                border-bottom: 1px solid rgba(0, 0, 0, 180);
                border-radius: 8px;
            """

        self.container.setStyleSheet(f"""
            #container {{
                {bg_css}
            }}
            #header_bar {{
                {header_css}
            }}
            QPushButton {{
                background-color: rgba(255, 255, 255, 28);
                border: 1px solid rgba(255, 255, 255, 60);
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 500;
                padding: 2px 6px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 60);
                border-color: rgba(255, 255, 255, 130);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 85);
            }}
        """)

    def set_transparent_background(self, enabled: bool) -> None:
        self._transparent_bg = bool(enabled)
        self._apply_container_style()
        if hasattr(self, "btn_bg_mode"):
            self.btn_bg_mode.setText("🎨 Clear" if self._transparent_bg else "🎨 Glass")
        if hasattr(self, "action_transparent_bg"):
            self.action_transparent_bg.setChecked(self._transparent_bg)

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

    # Bubble collapse & expand
    def send_command(self, action: str, **kwargs: Any) -> None:
        """Send a playback control command (play_pause, next, prev, seek) to Spotify Web."""
        if self.ws_server and hasattr(self.ws_server, "send_command"):
            self.ws_server.send_command(action, **kwargs)

    def collapse_to_bubble(self) -> None:
        """Collapse lyrics window into a compact floating bubble."""
        self._saved_geometry = self.geometry()
        bubble_x = self.x() + self.width() - 60
        bubble_y = self.y() + 10
        self.hide()
        self.bubble.move(max(0, bubble_x), max(0, bubble_y))
        self.bubble.show()

    def expand_from_bubble(self) -> None:
        """Expand from floating bubble back to full window."""
        self.bubble.hide()
        if hasattr(self, "_saved_geometry") and self._saved_geometry:
            new_x = max(0, self.bubble.x() - self._saved_geometry.width() + 60)
            new_y = max(0, self.bubble.y() - 10)
            self.move(new_x, new_y)
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_bubble(self) -> None:
        """Toggle between bubble mode and full window mode."""
        if self.isVisible():
            self.collapse_to_bubble()
        else:
            self.expand_from_bubble()

    def minimize_to_tray(self) -> None:
        """Minimize window directly to system tray."""
        if hasattr(self, "bubble"):
            self.bubble.hide()
        self.hide()
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "MiniLyrics Minimized",
                "App is running in the system tray. Click the tray icon to restore.",
                QSystemTrayIcon.Information,
                1500,
            )

    def restore_from_tray(self) -> None:
        """Restore window from system tray."""
        if hasattr(self, "bubble"):
            self.bubble.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        """Kill the process and cleanly exit the application."""
        if hasattr(self, "bubble"):
            self.bubble.hide()
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.hide()
        QApplication.instance().quit()

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
            heights, y_positions = self.lyrics_display.compute_layout()

            line_changed = (active_idx != self._active_idx)
            if line_changed:
                self._active_idx = active_idx
                self.lyrics_display.active_idx = active_idx

            if 0 <= active_idx < len(y_positions):
                self._target_scroll_y = y_positions[active_idx] + heights[active_idx] / 2.0
            elif y_positions:
                self._target_scroll_y = y_positions[0] + heights[0] / 2.0

            # Smooth exponential ease-out scrolling
            diff = self._target_scroll_y - self._current_scroll_y
            scrolling = abs(diff) > 0.05
            if scrolling:
                self._current_scroll_y += diff * 0.12
            else:
                self._current_scroll_y = self._target_scroll_y

            if scrolling or line_changed or abs(self.lyrics_display.scroll_y - self._current_scroll_y) > 0.02:
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

        now = time.monotonic()
        track_key = (title, artist)
        track_changed = (track_key != self._current_track_key)

        if track_changed:
            self._current_track_key = track_key
            self._playback_pos = position
            self._current_time = position
            self._last_update_monotonic = now
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
        else:
            # Same track: prevent coarse Spotify updates (whole seconds) from yanking time backwards
            if not is_paused and self._playback_pos > 0:
                delta = position - self._current_time
                if abs(delta) > 1.5:
                    # User clicked seekbar (large seek backward or forward)
                    self._playback_pos = position
                    self._current_time = position
                    self._last_update_monotonic = now
                elif delta >= 0.0:
                    # Spotify time caught up or moved forward
                    self._playback_pos = position
                    self._current_time = position
                    self._last_update_monotonic = now
                else:
                    # delta between -1.5s and 0.0s: coarse integer second lag from DOM.
                    # Never yank time backwards during continuous playback!
                    pass
            else:
                self._playback_pos = position
                self._current_time = position
                self._last_update_monotonic = now

        self._duration = duration
        self._is_paused = is_paused

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
