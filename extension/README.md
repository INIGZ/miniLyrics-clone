# MiniLyrics Spotify Web Player Integration

This directory contains integration options to stream playback status (track name, artist, album, duration, playback position, play/pause state) from [open.spotify.com](https://open.spotify.com) to the local MiniLyrics desktop overlay via WebSocket (`ws://127.0.0.1:8765`).

---

## Mozilla Firefox Users (Two Options)

### Option 1: Tampermonkey / Violentmonkey Userscript (Recommended for Firefox)

> **Why recommended for Firefox:** In Firefox, unpacked extensions loaded via `about:debugging` are temporary and get unloaded every time Firefox closes. A userscript in Violentmonkey or Tampermonkey **persists permanently across all Firefox restarts**.

1. Install [Violentmonkey](https://addons.mozilla.org/firefox/addon/violentmonkey/) or [Tampermonkey](https://addons.mozilla.org/firefox/addon/tampermonkey/) from Firefox Add-ons.
2. Click the extension icon in Firefox toolbar and choose **Create a new script** (or **+**).
3. Paste the contents of [`minilyrics.user.js`](./minilyrics.user.js).
4. Save (`Ctrl+S`).
5. Open or refresh [open.spotify.com](https://open.spotify.com).
6. When MiniLyrics desktop is running, a status pill appears at the bottom right:
   `MiniLyrics: Connected 🟢`.

### Option 2: Firefox Temporary Add-on (`about:debugging`)

1. Open Firefox and type `about:debugging#/runtime/this-firefox` in the address bar.
2. Click **Load Temporary Add-on...**
3. Browse to this directory and select `manifest.json` (or any file in this folder).
4. Open [open.spotify.com](https://open.spotify.com).

*(Note: Firefox unloads temporary add-ons when the browser exits, so Option 1 is recommended for everyday listening).*

---

## Chrome / Edge / Brave Users

1. Open your browser and navigate to:
   - Chrome: `chrome://extensions`
   - Edge: `edge://extensions`
   - Brave: `brave://extensions`
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** in the top-left toolbar.
4. Select this directory (`miniLyrics/extension`).
5. Open or refresh [open.spotify.com](https://open.spotify.com).

---

## Playback Simulator

To test MiniLyrics without opening Spotify in a browser, run the included simulator:

```bash
# Emit Bohemian Rhapsody playback events over WebSocket
python -m src.simulator.mock_spotify --mode client
```
