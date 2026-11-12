# MiniLyrics

A lightweight, modern MiniLyrics clone for Spotify Web Player ([open.spotify.com](https://open.spotify.com)). MiniLyrics displays synchronized, smoothly scrolling lyrics on a sleek, transparent, always-on-top floating desktop overlay powered by PyQt5, LRCLIB, and WebSockets.

---

## Features

- **Transparent, Borderless, Always-on-Top Desktop Overlay**: Floats unobtrusively above all applications with a translucent dark backdrop, rounded corners, and smooth typography.
- **Click-Through / Lock Mode (`Ctrl+L` or System Tray)**: Make the window completely transparent to mouse clicks (`Qt.WindowTransparentForInput`) so you can work, game, or browse unimpeded while lyrics scroll. Toggle back anytime via the system tray icon.
- **Synchronized Scrolling Lyrics with Spotify Green Highlight**: Current singing lines are highlighted in Spotify vibrant green (`#1DB954`) and smoothly animated to the vertical center with exponential ease-out scrolling. Past and upcoming lines are rendered with subtle contrasting opacities.
- **Instant Sync with open.spotify.com via WebSocket**: Dedicated background asyncio server on port `8765` receives real-time track metadata and playback position updates from Spotify Web Player.
- **Automatic Synced Lyrics via LRCLIB with Offline Caching**: Fetches synced `.lrc` lyrics from the open LRCLIB database (exact matching with search fallback). Downloaded lyrics are cached locally to `.cache/lyrics/` as JSON for instant offline playback.
- **Manual Offset Calibration (`[-0.5s]`, `[+0.5s]`, `[` and `]` hotkeys)**: Fine-tune synchronization on the fly by +/- 500ms increments to compensate for audio latency or live versions.
- **Opacity Adjustment Slider**: Header slider allows effortless transparency adjustments between 30% and 100%.
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

## Browser Extension & Userscript Setup

To sync playback status from Spotify Web Player to the desktop overlay:

### Option A: Unpacked Chrome / Edge / Brave Extension (Recommended)

1. Open your Chromium-based browser and navigate to:
   - Chrome: `chrome://extensions`
   - Edge: `edge://extensions`
   - Brave: `brave://extensions`
2. Enable **Developer mode** (toggle switch in the top-right corner).
3. Click **Load unpacked** in the top-left toolbar.
4. Select the `extension/` folder in this repository (`miniLyrics/extension`).
5. Open or refresh [open.spotify.com](https://open.spotify.com).
6. When MiniLyrics is running, the status pill near the bottom-right playback controls will display:
   `MiniLyrics: Connected 🟢`.

### Option B: Tampermonkey / Violentmonkey Userscript

1. Install [Tampermonkey](https://www.tampermonkey.net/) or [Violentmonkey](https://violentmonkey.github.io/) in your browser.
2. Open extension dashboard, click **Create a new script**, and paste the full contents of [`extension/minilyrics.user.js`](extension/minilyrics.user.js).
3. Save the script and navigate to [open.spotify.com](https://open.spotify.com).

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
| **Click-Through / Lock** | `Ctrl + L` / Header `🔒 Lock` | Toggles input transparency. Clicks pass through to desktop/apps behind. |
| **Unlock Window** | **System Tray Icon Click** | Restores normal window input when click-through mode is active. |
| **Move Overlay** | Left-click + Drag | Drag window anywhere on screen (header bar or background). |
| **Resize Overlay** | Bottom-Right Grip | Drag the bottom-right size grip to scale window width/height. |
| **Decrease Offset** | `[` or `[-0.5s]` button | Adjusts lyric timing by -500ms (lyrics display earlier). |
| **Increase Offset** | `]` or `[+0.5s]` button | Adjusts lyric timing by +500ms (lyrics display later). |
| **Reset Offset** | System Tray Menu | Resets manual offset calibration back to `+0.0s`. |
| **Opacity Slider** | Header Horizontal Slider | Adjusts window opacity continuously from 30% to 100%. |
| **Close Overlay** | `✕` button / Tray -> Quit | Cleanly terminates WebSocket server and closes application. |

---

## Testing

Run the automated pytest suite (39 unit tests covering parsing, caching, GUI state, and WebSockets):

```bash
pytest -v
```

---

## License

MIT License. Built for music lovers and desktop customizers.
