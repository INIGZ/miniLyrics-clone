# MiniLyrics

A lightweight, modern MiniLyrics clone for Spotify Web Player ([open.spotify.com](https://open.spotify.com)). MiniLyrics displays synchronized, smoothly scrolling lyrics on a sleek, transparent, always-on-top floating desktop overlay powered by PyQt5, LRCLIB, and WebSockets.

---

## Features

- **Remembers Window Position & Size**: Automatically remembers your preferred screen location, dimensions, and background transparency mode across app restarts (`.cache/window_state.json`).
- **Compact & Floating (510×120 Default Size)**: 50% shorter height and 75% width by default for a sleek, unobtrusive desktop strip that floats above all apps.
- **2-Row Crystal Header Bar (Focus-Revealed)**: In Glass mode, the header is organized into two clean rows (Row 1: Track title & window actions; Row 2: Playback controls & timing offset) with an opaque beveled crystal glass gradient that reveals on focus or hover.
- **Delicate Hairline Black Font Outline**: Ultra-thin contour border around every lyric character that preserves font elegance while guaranteeing sharp contrast over any background wallpaper.
- **Transparent, Borderless, Always-on-Top Desktop Overlay**: Floats unobtrusively above all applications with a translucent dark backdrop, rounded corners, and smooth typography.
- **Full Playback Control of Spotify Web**: Control Spotify directly from the overlay via header buttons (`⏮`, `⏯`, `⏭`), keyboard shortcuts (`Space`, `Ctrl+Left`, `Ctrl+Right`), or tray menu.
- **Click-to-Seek Any Verse**: Left-click any lyric line in the window to instantly jump Spotify Web Player playback to that exact timestamp!
- **Transparent Background (Text Only Mode)**: Toggle between sleek dark frosted glass and 100% transparent background (`Ctrl+B` or header `🎨 Clear` button) so *only the lyrics text floats directly on your screen* with a subtle text shadow for readability over any light or dark background.
- **Full Word-Wrapping Support**: Automatically wraps long lines across multiple lines with dynamic height allocation so lyrics are never truncated or cut off horizontally.
- **Resizable Window with Adaptive Font Sizing**: Scale the overlay to any size (small widget or large display); font size smoothly adapts to window dimensions automatically.
- **Click-Through / Lock Mode (`Ctrl+L` or System Tray)**: Make the window completely transparent to mouse clicks (`Qt.WindowTransparentForInput`) so you can work, game, or browse unimpeded while lyrics scroll. Toggle back anytime via the system tray icon.
- **Synchronized Scrolling Lyrics with Spotify Green Highlight**: Current singing lines are highlighted in Spotify vibrant green (`#1DB954`) and smoothly animated to the vertical center with exponential ease-out scrolling. Past and upcoming lines are rendered with subtle contrasting opacities.
- **Instant Sync with open.spotify.com via WebSocket**: Dedicated background asyncio server on port `8765` receives real-time track metadata and playback position updates from Spotify Web Player.
- **Automatic Synced Lyrics via LRCLIB with Offline Caching**: Fetches synced `.lrc` lyrics from the open LRCLIB database (exact matching with search fallback). Downloaded lyrics are cached locally to `.cache/lyrics/` as JSON for instant offline playback.
- **Manual Offset Calibration (`[-0.5s]`, `[+0.5s]`, `[` and `]` hotkeys)**: Fine-tune synchronization on the fly by +/- 500ms increments to compensate for audio latency or live versions.
- **Built-in Visual Demo Mode (`python main.py --demo`)**: Immediately previews UI styling, lyrics synchronization, and smooth scrolling using Queen's *Bohemian Rhapsody* without launching a browser or logging into Spotify.
- **Standalone Mock Playback Simulator (`python -m src.simulator.mock_spotify`)**: CLI playback engine to simulate Spotify track transitions, seeking, and playback events over WebSocket.

---

## Architecture & Data Flow

```
+--------------------------------------------------------------------------+
|                        Spotify Web Player                                |
|                      (https://open.spotify.com)                          |
|                                                                          |
|   +------------------------------------------------------------------+   |
|   |         MiniLyrics Integration (Extension or Userscript)         |   |
|   |  - Scrapes title, artist, album, duration, position, isPaused    |   |
|   |  - 3-tier fallback: DOM testids -> HTML5 Audio -> MediaSession   |   |
|   |  - Visual status pill in bottom player bar                       |   |
|   +---------------------------------+--------------------------------+   |
+-------------------------------------|------------------------------------+
                                      | WebSocket (ws://127.0.0.1:8765)
                                      v
+--------------------------------------------------------------------------+
|                     MiniLyrics Desktop Application                       |
|                                                                          |
|   +------------------------------------------------------------------+   |
|   | WebSocketServer (QThread + asyncio)                              |   |
|   | Listens on 127.0.0.1:8765, deserializes playback_update JSON,    |   |
|   | and safely emits PyQt `playback_updated` signal across threads   |   |
|   +---------------------------------+--------------------------------+   |
|                                     | PyQt Signal (dict)                 |
|                                     v                                    |
|   +------------------------------------------------------------------+   |
|   | LyricsWindow (QMainWindow / QWidget)                             |   |
|   |  - Translucent frameless window (Qt.FramelessWindowHint)         |   |
|   |  - Manages playback position, manual offset, & lock state        |   |
|   |  - High-frequency (30ms) animation timer for time interpolation  |   |
|   |  - Queries LRCLibClient on background daemon thread              |   |
|   +-------------------+------------------------------+---------------+   |
|                       |                              |                   |
|                       v                              v                   |
|   +-------------------------------+   +------------------------------+   |
|   | LRCLibClient                  |   | LyricsDisplay (Custom QWidget)   |
|   | 1. Check disk: .cache/lyrics/ |   | - Antialiased QPainter       |   |
|   | 2. Exact API: /api/get        |   | - Exponential ease scrolling |   |
|   | 3. Search API: /api/search    |   | - Dynamic font & colors      |   |
|   | 4. LRCParser (bisect lookup)  |   | - Active line Spotify green  |   |
|   +-------------------------------+   +------------------------------+   |
+--------------------------------------------------------------------------+
```

---

## Installation & Quickstart

### Prerequisites
- Python 3.10+
- Google Chrome, Microsoft Edge, Brave, or any Chromium/Firefox browser

### 1. Install Dependencies

```bash
cd miniLyrics

# Install requirements
pip install -r requirements.txt
```

### 2. Run Desktop App

```bash
# Standard mode (waits for Spotify playback on ws://127.0.0.1:8765)
python main.py

# Visual demo mode (simulates playback immediately with bundled lyrics)
python main.py --demo

# CLI Options:
#   --demo     Run built-in song and lyrics simulation
#   --port     Custom WebSocket port (default: 8765)
#   --no-top   Disable WindowStaysOnTopHint
```

---

## Browser Setup (Mozilla Firefox, Chrome, Edge, Brave)

To sync playback status from Spotify Web Player to the desktop overlay:

### Mozilla Firefox Users (Recommended: Userscript)

Because Firefox removes temporary unpacked add-ons whenever the browser closes, **Option A (Userscript)** is the recommended permanent setup for Firefox:

#### Option A: Persistent Userscript via Violentmonkey or Tampermonkey (Recommended for Firefox)
1. Install [Violentmonkey](https://addons.mozilla.org/firefox/addon/violentmonkey/) or [Tampermonkey](https://addons.mozilla.org/firefox/addon/tampermonkey/) from Mozilla Add-ons.
2. Click the extension toolbar icon and choose **Create a new script** (or **+**).
3. Paste the full contents of [`extension/minilyrics.user.js`](extension/minilyrics.user.js).
4. Save (`Ctrl+S`).
5. Open [open.spotify.com](https://open.spotify.com) — it will automatically connect on every Firefox launch.

#### Option B: Firefox Temporary Add-on (about:debugging)
1. In Firefox address bar, navigate to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**
3. Select `extension/manifest.json`.
4. Open [open.spotify.com](https://open.spotify.com).

---

### Chromium Users (Chrome, Edge, Brave)

1. Open `chrome://extensions` (or `edge://extensions` / `brave://extensions`).
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** (top-left) and choose the `extension/` folder.
4. Open or refresh [open.spotify.com](https://open.spotify.com).

---

## Playback Simulator

Test lyrics synchronization without opening Spotify or logging in:

```bash
# Connect as a client to a running MiniLyrics desktop app
python -m src.simulator.mock_spotify --mode client

# Run with custom song or 2x speed
python -m src.simulator.mock_spotify --title "Hotel California" --artist "Eagles" --speed 2.0

# Run internal assertion self-checks
python -m src.simulator.mock_spotify --test
```

---

## Keyboard Shortcuts & Controls

| Action | Control / Hotkey | Description |
|---|---|---|
| **Play / Pause** | `Space` / Header `⏯` | Toggles play/pause in Spotify Web Player. |
| **Next Track** | `Ctrl + Right` / Header `⏭` | Skips to the next track in Spotify Web Player. |
| **Previous Track** | `Ctrl + Left` / Header `⏮` | Returns to the previous track in Spotify Web Player. |
| **Click-to-Seek** | Click any lyric line | Jumps Spotify playback directly to the clicked lyric timestamp. |
| **Collapse to Bubble** | `Ctrl + M` / Header `🫧` | Collapses overlay into a compact floating bubble. Click bubble or press `Ctrl+M` to expand. |
| **Minimize to Tray** | `Ctrl + N` / Header `—` | Hides window to the system tray. Click the tray icon to restore. |
| **Exit Process** | `Ctrl + Q` / Header `✕` | Immediately kills the process and terminates the application cleanly. |
| **Click-Through / Lock** | `Ctrl + L` / Header `🔒 Lock` | Toggles input transparency. Clicks pass through to desktop/apps behind. |
| **Restore / Unlock** | **System Tray Icon Click** | Restores window when hidden in tray, or unlocks click-through mode. |
| **Transparent Background** | `Ctrl + B` / Header `🎨 Clear` | Toggles background container between dark glass and 100% transparent (text-only). |
| **Move Overlay** | Left-click + Drag | Drag window anywhere on screen (header bar or background). |
| **Resize Overlay** | Bottom-Right Grip | Drag size grip to scale window; text size dynamically adapts. |
| **Decrease Offset** | `[` or `[-0.5s]` button | Adjusts lyric timing by -500ms (lyrics display earlier). |
| **Increase Offset** | `]` or `[+0.5s]` button | Adjusts lyric timing by +500ms (lyrics display later). |
| **Reset Offset** | System Tray Menu | Resets manual offset calibration back to `+0.0s`. |

---

## Testing

Run the automated pytest suite (49 unit tests covering parsing, caching, GUI state, window persistence, crystal header, bubble collapse, and bidirectional WebSockets):

```bash
pytest -v
```

---

## License

MIT License. Built for music lovers and desktop customizers.
