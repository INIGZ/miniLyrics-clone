// ==UserScript==
// @name         MiniLyrics Spotify Web Player Integration
// @namespace    https://github.com/miniLyrics
// @version      1.0.0
// @description  Syncs playback status from Spotify Web Player to MiniLyrics desktop overlay via WebSocket.
// @author       MiniLyrics
// @match        *://open.spotify.com/*
// @icon         https://open.spotifycdn.com/cdn/images/favicon.0f31d2ea.ico
// @connect      127.0.0.1
// @connect      localhost
// @grant        GM_info
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  // Inject styles for status badge
  const style = document.createElement("style");
  style.id = "minilyrics-style";
  style.textContent = `
    #minilyrics-status-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-family: var(--font-family, spotify-circular, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif);
      font-size: 11px;
      font-weight: 500;
      line-height: 1;
      letter-spacing: 0.2px;
      color: #a7a7a7;
      background-color: rgba(255, 255, 255, 0.07);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 12px;
      padding: 4px 8px;
      margin: 0 10px;
      white-space: nowrap;
      user-select: none;
      pointer-events: none;
      transition: color 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
      box-sizing: border-box;
    }
    #minilyrics-status-badge.minilyrics-connected {
      color: #1ed760;
      border-color: rgba(30, 215, 96, 0.35);
      background-color: rgba(30, 215, 96, 0.08);
    }
    #minilyrics-status-badge.minilyrics-disconnected {
      color: #a7a7a7;
      border-color: rgba(255, 255, 255, 0.12);
      background-color: rgba(255, 255, 255, 0.05);
    }
  `;
  (document.head || document.documentElement).appendChild(style);

  const WS_URL = "ws://127.0.0.1:8765";
  const RECONNECT_INTERVAL_MS = 3000;
  const PLAYING_TICK_INTERVAL_MS = 250;

  let ws = null;
  let reconnectTimer = null;
  let isConnected = false;
  let lastSentState = null;
  let lastSentTime = 0;

  function parseTime(timeStr) {
    if (!timeStr || typeof timeStr !== "string") return 0;
    const parts = timeStr.trim().split(":").map((p) => parseFloat(p));
    if (parts.some((n) => isNaN(n))) return 0;
    if (parts.length === 3) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    if (parts.length === 2) {
      return parts[0] * 60 + parts[1];
    }
    if (parts.length === 1) {
      return parts[0];
    }
    return 0;
  }

  function getAudioElement() {
    return document.querySelector("audio");
  }

  function getNowPlayingWidget() {
    return document.querySelector('[data-testid="now-playing-widget"]');
  }

  function scrapeTitle(widget) {
    if (widget) {
      const titleElem = widget.querySelector(
        '[data-testid="context-item-info-title"], [data-testid="context-item-link"], a[href*="/track/"], .ellipsis-one-line a'
      );
      if (titleElem && titleElem.textContent.trim()) {
        return titleElem.textContent.trim();
      }
    }
    if (navigator.mediaSession?.metadata?.title) {
      return navigator.mediaSession.metadata.title.trim();
    }
    return "";
  }

  function scrapeArtist(widget) {
    if (widget) {
      const artistLinks = widget.querySelectorAll(
        '[data-testid="context-item-info-artist"] a, [data-testid="context-item-info-subtitles"] a, a[href*="/artist/"]'
      );
      if (artistLinks.length > 0) {
        const names = Array.from(artistLinks)
          .map((a) => a.textContent.trim())
          .filter(Boolean);
        if (names.length > 0) return names.join(", ");
      }
      const fallbackElem = widget.querySelector(
        '[data-testid="context-item-info-artist"], [data-testid="context-item-info-subtitles"]'
      );
      if (fallbackElem && fallbackElem.textContent.trim()) {
        return fallbackElem.textContent.trim();
      }
    }
    if (navigator.mediaSession?.metadata?.artist) {
      return navigator.mediaSession.metadata.artist.trim();
    }
    return "";
  }

  function scrapeAlbum(widget) {
    if (widget) {
      const albumElem = widget.querySelector(
        '[data-testid="context-item-info-album-name"], a[href*="/album/"]'
      );
      if (albumElem && albumElem.textContent.trim()) {
        return albumElem.textContent.trim();
      }
      const img = widget.querySelector(
        'img[data-testid="cover-art-image"], img[alt]'
      );
      if (img && img.getAttribute("alt")) {
        const alt = img.getAttribute("alt").trim();
        const cleaned = alt
          .replace(/^album cover of\s+/i, "")
          .replace(/^cover of\s+/i, "")
          .trim();
        if (cleaned) return cleaned;
      }
    }
    if (navigator.mediaSession?.metadata?.album) {
      return navigator.mediaSession.metadata.album.trim();
    }
    return "";
  }

  function scrapeDuration(audio) {
    const durElem = document.querySelector('[data-testid="playback-duration"]');
    if (durElem && durElem.textContent.trim()) {
      const parsed = parseTime(durElem.textContent.trim());
      if (parsed > 0) return Math.round(parsed * 10) / 10;
    }
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) {
      return Math.round(audio.duration * 10) / 10;
    }
    if (
      navigator.mediaSession &&
      typeof navigator.mediaSession.getPositionState === "function"
    ) {
      try {
        const state = navigator.mediaSession.getPositionState();
        if (state && Number.isFinite(state.duration) && state.duration > 0) {
          return Math.round(state.duration * 10) / 10;
        }
      } catch (_) {}
    }
    return 0;
  }

  function scrapePosition(audio) {
    const posElem = document.querySelector('[data-testid="playback-position"]');
    const domPos = posElem ? parseTime(posElem.textContent.trim()) : 0;

    // Check progress bar style transform for sub-second precision
    const bar = document.querySelector('[data-testid="playback-progressbar"], [data-testid="progress-bar"]');
    if (bar) {
      const transformElem = bar.querySelector('[style*="--progress-bar-transform"], [style*="--progress-bar-progress"]');
      if (transformElem && transformElem.getAttribute("style")) {
        const match = transformElem.getAttribute("style").match(/--progress-bar-(?:transform|progress):\s*([\d.]+)%/);
        if (match) {
          const pct = parseFloat(match[1]);
          const duration = scrapeDuration(audio);
          if (duration > 0 && Number.isFinite(pct) && pct >= 0 && pct <= 100) {
            return Math.round((pct / 100.0) * duration * 100) / 100;
          }
        }
      }
    }

    if (audio && Number.isFinite(audio.currentTime) && audio.currentTime >= 0) {
      if (!posElem || Math.abs(audio.currentTime - domPos) <= 3) {
        return Math.round(audio.currentTime * 10) / 10;
      }
    }
    if (
      navigator.mediaSession &&
      typeof navigator.mediaSession.getPositionState === "function"
    ) {
      try {
        const state = navigator.mediaSession.getPositionState();
        if (state && Number.isFinite(state.position) && state.position >= 0) {
          return Math.round(state.position * 10) / 10;
        }
      } catch (_) {}
    }
    return Math.round(domPos * 10) / 10;
  }

  function scrapeIsPaused(audio) {
    const playPauseBtn = document.querySelector(
      '[data-testid="control-button-playpause"]'
    );
    if (playPauseBtn) {
      const label = (playPauseBtn.getAttribute("aria-label") || "").toLowerCase();
      if (label.includes("pause") || label.includes("pausar")) {
        return false;
      }
      if (label.includes("play") || label.includes("reproducir")) {
        return true;
      }
    }

    if (navigator.mediaSession && navigator.mediaSession.playbackState) {
      if (navigator.mediaSession.playbackState === "playing") return false;
      if (navigator.mediaSession.playbackState === "paused") return true;
    }

    if (audio) {
      return audio.paused;
    }

    return true;
  }

  function scrapePlaybackState() {
    const widget = getNowPlayingWidget();
    const audio = getAudioElement();

    return {
      type: "playback_update",
      title: scrapeTitle(widget),
      artist: scrapeArtist(widget),
      album: scrapeAlbum(widget),
      duration: scrapeDuration(audio),
      position: scrapePosition(audio),
      isPaused: scrapeIsPaused(audio),
    };
  }

  function updateBadge(connected) {
    let badge = document.getElementById("minilyrics-status-badge");
    if (!badge || !document.body.contains(badge)) {
      if (badge && badge.parentNode) {
        badge.parentNode.removeChild(badge);
      }
      badge = document.createElement("div");
      badge.id = "minilyrics-status-badge";
      badge.title = "MiniLyrics WebSocket Status";

      const bottomBar =
        document.querySelector('[data-testid="now-playing-bar"]') ||
        document.querySelector("footer") ||
        document.querySelector(".now-playing-bar");

      if (bottomBar) {
        const rightControls =
          bottomBar.querySelector(
            '[data-testid="now-playing-bar-right-controls"]'
          ) ||
          bottomBar.querySelector('[data-testid="player-controls"]') ||
          bottomBar.lastElementChild;

        if (rightControls && rightControls.parentElement === bottomBar) {
          bottomBar.insertBefore(badge, rightControls);
        } else {
          bottomBar.appendChild(badge);
        }
      } else {
        document.body.appendChild(badge);
      }
    }

    if (badge._lastConnected !== connected) {
      badge._lastConnected = connected;
      badge.textContent = connected
        ? "MiniLyrics: Connected 🟢"
        : "MiniLyrics: Disconnected ⚪";
      badge.className = connected
        ? "minilyrics-connected"
        : "minilyrics-disconnected";
    }
  }

  function sendPlaybackUpdate(state) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!state.title && !lastSentState?.title) return;

    try {
      ws.send(JSON.stringify(state));
      lastSentState = state;
      lastSentTime = Date.now();
    } catch (_) {}
  }

  function hasSongOrPauseChanged(current, last) {
    if (!last) return true;
    return (
      current.title !== last.title ||
      current.artist !== last.artist ||
      current.album !== last.album ||
      current.isPaused !== last.isPaused
    );
  }

  function pollAndSync(force = false) {
    updateBadge(isConnected);

    const current = scrapePlaybackState();
    if (!isConnected) return;

    const songOrPauseChanged = hasSongOrPauseChanged(current, lastSentState);

    if (force || songOrPauseChanged) {
      sendPlaybackUpdate(current);
    } else if (!current.isPaused) {
      const elapsed = Date.now() - lastSentTime;
      if (elapsed >= PLAYING_TICK_INTERVAL_MS - 20) {
        sendPlaybackUpdate(current);
      }
    } else {
      if (
        lastSentState &&
        Math.abs(current.position - lastSentState.position) >= 0.5
      ) {
        sendPlaybackUpdate(current);
      }
    }
  }

  function robustClick(elem) {
    if (!elem) return false;
    try {
      elem.focus();
    } catch (_) {}

    const mouseOpts = { bubbles: true, cancelable: true, view: window, buttons: 1, detail: 1 };
    try {
      elem.dispatchEvent(new PointerEvent("pointerdown", mouseOpts));
      elem.dispatchEvent(new MouseEvent("mousedown", mouseOpts));
      elem.dispatchEvent(new PointerEvent("pointerup", mouseOpts));
      elem.dispatchEvent(new MouseEvent("mouseup", mouseOpts));
      elem.dispatchEvent(new MouseEvent("click", mouseOpts));
    } catch (_) {}

    try {
      elem.click();
    } catch (_) {}

    return true;
  }

  function togglePlayPause() {
    const doc = (typeof unsafeWindow !== "undefined" && unsafeWindow.document) ? unsafeWindow.document : document;
    const selectors = [
      '[data-testid="control-button-playpause"]',
      '[data-testid="play-button"]',
      '[data-testid="player-controls"] button[data-testid*="play" i]',
      '[data-testid="player-controls"] button[data-testid*="pause" i]',
      'button[aria-label="Play"]',
      'button[aria-label="Pause"]',
      'button[aria-label="Reproducir"]',
      'button[aria-label="Pausar"]',
      '[data-testid="player-controls"] button[aria-label*="Play" i]',
      '[data-testid="player-controls"] button[aria-label*="Pause" i]',
      '[data-testid="player-controls"] button[aria-label*="Reproducir" i]',
      '[data-testid="player-controls"] button[aria-label*="Pausar" i]',
      'footer button[aria-label*="Play" i]',
      'footer button[aria-label*="Pause" i]',
      'footer button[aria-label*="Reproducir" i]',
      'footer button[aria-label*="Pausar" i]',
    ];

    for (const sel of selectors) {
      const btn = doc.querySelector(sel);
      if (btn) {
        console.log("[MiniLyrics] Triggering play/pause on:", sel);
        robustClick(btn);
        return true;
      }
    }

    const controls = doc.querySelector('[data-testid="player-controls"], .player-controls');
    if (controls) {
      const buttons = controls.querySelectorAll("button");
      if (buttons.length >= 3) {
        const centerBtn = buttons[Math.floor(buttons.length / 2)];
        console.log("[MiniLyrics] Clicking center player-controls button");
        robustClick(centerBtn);
        return true;
      }
    }

    const audio = getAudioElement();
    if (audio) {
      console.log("[MiniLyrics] Toggling HTML5 audio directly");
      if (audio.paused) {
        audio.play().catch(() => {});
      } else {
        audio.pause();
      }
      return true;
    }

    const spaceOpts = { key: " ", code: "Space", keyCode: 32, which: 32, bubbles: true, cancelable: true };
    doc.body.dispatchEvent(new KeyboardEvent("keydown", spaceOpts));
    doc.body.dispatchEvent(new KeyboardEvent("keyup", spaceOpts));
    return true;
  }

  function skipNext() {
    const doc = (typeof unsafeWindow !== "undefined" && unsafeWindow.document) ? unsafeWindow.document : document;
    const selectors = [
      '[data-testid="control-button-skip-forward"]',
      '[data-testid="skip-forward-button"]',
      'button[aria-label*="Next" i]',
      'button[aria-label*="Siguiente" i]',
      'button[aria-label*="Suivant" i]',
      '[data-testid="player-controls"] button[aria-label*="Next" i]',
      'footer button[aria-label*="Next" i]',
    ];

    for (const sel of selectors) {
      const btn = doc.querySelector(sel);
      if (btn) {
        console.log("[MiniLyrics] Triggering skip-forward on:", sel);
        robustClick(btn);
        return true;
      }
    }

    const controls = doc.querySelector('[data-testid="player-controls"], .player-controls');
    if (controls) {
      const buttons = controls.querySelectorAll("button");
      if (buttons.length >= 4) {
        const nextBtn = buttons[Math.floor(buttons.length / 2) + 1];
        robustClick(nextBtn);
        return true;
      }
    }
    return false;
  }

  function skipPrev() {
    const doc = (typeof unsafeWindow !== "undefined" && unsafeWindow.document) ? unsafeWindow.document : document;
    const selectors = [
      '[data-testid="control-button-skip-back"]',
      '[data-testid="skip-back-button"]',
      'button[aria-label*="Previous" i]',
      'button[aria-label*="Anterior" i]',
      'button[aria-label*="Précédent" i]',
      '[data-testid="player-controls"] button[aria-label*="Previous" i]',
      'footer button[aria-label*="Previous" i]',
    ];

    for (const sel of selectors) {
      const btn = doc.querySelector(sel);
      if (btn) {
        console.log("[MiniLyrics] Triggering skip-back on:", sel);
        robustClick(btn);
        return true;
      }
    }

    const controls = doc.querySelector('[data-testid="player-controls"], .player-controls');
    if (controls) {
      const buttons = controls.querySelectorAll("button");
      if (buttons.length >= 3) {
        const prevBtn = buttons[Math.floor(buttons.length / 2) - 1];
        robustClick(prevBtn);
        return true;
      }
    }
    return false;
  }

  function executeSpotifyCommand(cmd) {
    console.log("[MiniLyrics] Received command:", cmd);
    if (!cmd || !cmd.action) return;

    switch (cmd.action) {
      case "play_pause": {
        togglePlayPause();
        break;
      }
      case "next": {
        skipNext();
        break;
      }
      case "prev": {
        skipPrev();
        break;
      }
      case "seek": {
        if (typeof cmd.position === "number") {
          seekSpotify(cmd.position);
        }
        break;
      }
    }
  }

  function seekSpotify(targetSeconds) {
    const doc = (typeof unsafeWindow !== "undefined" && unsafeWindow.document) ? unsafeWindow.document : document;
    console.log("[MiniLyrics] Seeking to:", targetSeconds);
    const audio = getAudioElement();
    if (audio && Number.isFinite(audio.duration) && audio.duration > 0) {
      try {
        audio.currentTime = targetSeconds;
      } catch (_) {}
    }

    const bar = doc.querySelector(
      '[data-testid="playback-progressbar"], [data-testid="progress-bar"], .playback-progressbar'
    );
    const durElem = doc.querySelector('[data-testid="playback-duration"]');
    const totalDuration = durElem ? parseTime(durElem.textContent.trim()) : (audio?.duration || 0);

    if (bar && totalDuration > 0) {
      const rect = bar.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, targetSeconds / totalDuration));
      const clickX = rect.left + rect.width * ratio;
      const clickY = rect.top + rect.height / 2;
      const opts = { bubbles: true, cancelable: true, view: window, clientX: clickX, clientY: clickY, button: 0 };
      bar.dispatchEvent(new PointerEvent("pointerdown", opts));
      bar.dispatchEvent(new MouseEvent("mousedown", opts));
      bar.dispatchEvent(new PointerEvent("pointerup", opts));
      bar.dispatchEvent(new MouseEvent("mouseup", opts));
      bar.dispatchEvent(new MouseEvent("click", opts));
    }
  }

  function connect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (
      ws &&
      (ws.readyState === WebSocket.CONNECTING ||
        ws.readyState === WebSocket.OPEN)
    ) {
      return;
    }

    try {
      ws = new WebSocket(WS_URL);
    } catch (_) {
      isConnected = false;
      updateBadge(false);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      isConnected = true;
      updateBadge(true);
      const current = scrapePlaybackState();
      sendPlaybackUpdate(current);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data && data.type === "command") {
          executeSpotifyCommand(data);
        }
      } catch (_) {}
    };

    ws.onclose = () => {
      isConnected = false;
      updateBadge(false);
      ws = null;
      scheduleReconnect();
    };

    ws.onerror = () => {
      // Handled by onclose
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, RECONNECT_INTERVAL_MS);
  }

  function init() {
    connect();
    setInterval(pollAndSync, 50);

    const onImmediate = () => pollAndSync(true);
    document.addEventListener("play", onImmediate, true);
    document.addEventListener("pause", onImmediate, true);
    document.addEventListener("playing", onImmediate, true);
    document.addEventListener("seeked", onImmediate, true);

    document.addEventListener(
      "click",
      (e) => {
        const target = e.target;
        if (
          target.closest?.('[data-testid="control-button-playpause"]') ||
          target.closest?.('[data-testid="control-button-skip-forward"]') ||
          target.closest?.('[data-testid="control-button-skip-back"]')
        ) {
          setTimeout(onImmediate, 20);
        }
      },
      true
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
