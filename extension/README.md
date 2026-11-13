# MiniLyrics Web Music Integration

This directory contains browser integration options to stream playback status (track name, artist, album, duration, playback position, play/pause state) and control playback for:
- **Spotify Web Player** (`open.spotify.com`)
- **YouTube Music** (`music.youtube.com`)
- **YouTube** (`www.youtube.com`)
- **Amazon Music** (`music.amazon.*`)

All streaming events connect to the local MiniLyrics desktop overlay via WebSocket (`ws://127.0.0.1:8765`).

---

## Mozilla Firefox Users (Recommended: Userscript)

> **Why recommended for Firefox:** In Firefox, unpacked extensions loaded via `about:debugging` are temporary and get unloaded every time Firefox closes. A userscript in Violentmonkey or Tampermonkey **persists permanently across all Firefox restarts**.

### Option 1: Persistent Userscript via Violentmonkey or Tampermonkey (Recommended for Firefox)
1. Install [Violentmonkey](https://addons.mozilla.org/firefox/addon/violentmonkey/) or [Tampermonkey](https://addons.mozilla.org/firefox/addon/tampermonkey/) from Firefox Add-ons.
2. Click the extension toolbar icon and choose **Create a new script** (or **+**).
3. Paste the contents of [`minilyrics.user.js`](./minilyrics.user.js).
4. Save (`Ctrl+S`).
5. Open any supported music website:
   - [music.youtube.com](https://music.youtube.com)
   - [www.youtube.com](https://www.youtube.com)
   - [open.spotify.com](https://open.spotify.com)
   - [music.amazon.com](https://music.amazon.com)
6. A status badge will appear confirming connection:  
   `MiniLyrics: Connected 🟢 (YouTube Music)`

### Option 2: Firefox Temporary Add-on (`about:debugging`)
1. Open Firefox and type `about:debugging#/runtime/this-firefox` in the address bar.
2. Click **Load Temporary Add-on...**
3. Select `extension/manifest.json`.

---

## Chrome / Edge / Brave Users

1. Open your browser and navigate to:
   - Chrome: `chrome://extensions`
   - Edge: `edge://extensions`
   - Brave: `brave://extensions`
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** in the top-left toolbar.
4. Select the `extension/` folder in this repository.
5. Open or refresh any supported music site.

---

## Playback Simulator

To test MiniLyrics without opening a browser:

```bash
python -m src.simulator.mock_spotify --mode client
```
