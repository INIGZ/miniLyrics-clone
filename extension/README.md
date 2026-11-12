# MiniLyrics Spotify Web Player Integration

This directory contains integration options to stream playback status (track name, artist, album, duration, playback position, play/pause state) from [open.spotify.com](https://open.spotify.com) to the local MiniLyrics desktop overlay via WebSocket (`ws://127.0.0.1:8765`).

## Option 1: Chrome / Edge / Brave Extension (Unpacked)

1. Open your browser and navigate to `chrome://extensions` (or `edge://extensions` in Microsoft Edge, `brave://extensions` in Brave).
2. Enable **Developer mode** toggle in the top-right corner.
3. Click **Load unpacked** in the top-left corner.
4. Select this directory (`miniLyrics/extension`).
5. Open or refresh [open.spotify.com](https://open.spotify.com).
6. When MiniLyrics desktop is running, a small status pill at the bottom right will show:
   `MiniLyrics: Connected 🟢`.

## Option 2: Tampermonkey / Violentmonkey Userscript

If you prefer userscripts:
1. Install [Tampermonkey](https://www.tampermonkey.net/) or [Violentmonkey](https://violentmonkey.github.io/) in your browser.
2. Create a new script and copy-paste the contents of [`minilyrics.user.js`](./minilyrics.user.js).
3. Save the script and open [open.spotify.com](https://open.spotify.com).

## Playback Simulator

To test MiniLyrics without opening Spotify in a browser, run the included simulator:

```bash
# Emit Bohemian Rhapsody playback events over WebSocket
python -m src.simulator.mock_spotify --mode client
```
