// ==UserScript==
// @name         MiniLyrics Web Music Integration
// @namespace    https://github.com/miniLyrics
// @version      1.1.0
// @description  Syncs playback status from Spotify, YouTube, YouTube Music, and Amazon Music to MiniLyrics desktop overlay via WebSocket.
// @author       MiniLyrics
// @match        *://open.spotify.com/*
// @match        *://*.youtube.com/*
// @match        *://music.amazon.com/*
// @match        *://music.amazon.co.uk/*
// @match        *://music.amazon.de/*
// @match        *://music.amazon.es/*
// @match        *://music.amazon.fr/*
// @match        *://music.amazon.it/*
// @match        *://music.amazon.co.jp/*
// @match        *://music.amazon.ca/*
// @match        *://music.amazon.in/*
// @connect      127.0.0.1
// @connect      localhost
// @grant        none
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
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 11px;
      font-weight: 500;
      line-height: 1;
      letter-spacing: 0.2px;
      color: #a7a7a7;
      background-color: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 12px;
      padding: 4px 8px;
      margin: 0 10px;
      white-space: nowrap;
      user-select: none;
      pointer-events: none;
      transition: color 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
      box-sizing: border-box;
      z-index: 999999;
    }
    #minilyrics-status-badge.minilyrics-connected {
      color: #1ed760;
      border-color: rgba(30, 215, 96, 0.4);
      background-color: rgba(30, 215, 96, 0.1);
    }
    #minilyrics-status-badge.minilyrics-disconnected {
      color: #a7a7a7;
      border-color: rgba(255, 255, 255, 0.12);
      background-color: rgba(255, 255, 255, 0.05);
    }
  `;
  if (!document.getElementById("minilyrics-style")) {
    document.head.appendChild(style);
  }

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
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 1) return parts[0];
    return 0;
  }

  function parseYouTubeSong(rawTitle, channelName) {
    if (!rawTitle) return { title: "", artist: channelName || "" };

    let cleaned = rawTitle
      .replace(
        /\s*[\(\[](?:Official\s*(?:Music\s*)?Video|Official\s*Audio|Lyric\s*Video|Official\s*Lyric\s*Video|Audio|4K|HD|Remastered|Visualizer|Clip\s*Officiel|Video\s*Oficial|Letra|Lyrics)[\)\]]/gi,
        ""
      )
      .trim();

    const dashes = [" - ", " – ", " — "];
    for (const dash of dashes) {
      if (cleaned.includes(dash)) {
        const parts = cleaned.split(dash);
        const artist = parts[0].trim().replace(/^VEVO\s*/i, "");
        const title = parts.slice(1).join(dash).trim();
        if (artist && title) {
          return { artist, title };
        }
      }
    }

    const cleanChannel = (channelName || "").replace(/\s*-\s*Topic$/i, "").trim();
    return { title: cleaned, artist: cleanChannel };
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

  const PROVIDERS = {
    spotify: {
      name: "Spotify",
      matches: () => window.location.hostname.includes("spotify.com"),
      getMedia: () => document.querySelector("audio, video"),
      getMetadata: () => {
        const widget = document.querySelector('[data-testid="now-playing-widget"]');
        let title = "";
        let artist = "";
        let album = "";

        if (widget) {
          const titleElem = widget.querySelector(
            '[data-testid="context-item-info-title"], [data-testid="context-item-link"], a[href*="/track/"], .ellipsis-one-line a'
          );
          if (titleElem) title = titleElem.textContent.trim();

          const artistLinks = widget.querySelectorAll(
            '[data-testid="context-item-info-artist"] a, [data-testid="context-item-info-subtitles"] a, a[href*="/artist/"]'
          );
          if (artistLinks.length > 0) {
            artist = Array.from(artistLinks)
              .map((a) => a.textContent.trim())
              .filter(Boolean)
              .join(", ");
          } else {
            const fallbackElem = widget.querySelector('[data-testid="context-item-info-artist"], [data-testid="context-item-info-subtitles"]');
            if (fallbackElem) artist = fallbackElem.textContent.trim();
          }

          const albumElem = widget.querySelector('[data-testid="context-item-info-album-name"], a[href*="/album/"]');
          if (albumElem) album = albumElem.textContent.trim();
        }

        return { title, artist, album };
      },
      playPause: (media) => {
        const doc = typeof unsafeWindow !== "undefined" && unsafeWindow.document ? unsafeWindow.document : document;
        const selectors = [
          '[data-testid="control-button-playpause"]',
          '[data-testid="play-button"]',
          '[data-testid="player-controls"] button[aria-label*="Play" i]',
          '[data-testid="player-controls"] button[aria-label*="Pause" i]',
          '[data-testid="player-controls"] button[aria-label*="Reproducir" i]',
          '[data-testid="player-controls"] button[aria-label*="Pausar" i]',
          'button[aria-label="Play"]',
          'button[aria-label="Pause"]',
        ];
        for (const sel of selectors) {
          const btn = doc.querySelector(sel);
          if (btn) return robustClick(btn);
        }
        if (media) return media.paused ? media.play().catch(() => {}) : media.pause();
      },
      next: () => {
        const doc = typeof unsafeWindow !== "undefined" && unsafeWindow.document ? unsafeWindow.document : document;
        const btn = doc.querySelector('[data-testid="control-button-skip-forward"], [data-testid="skip-forward-button"], button[aria-label*="Next" i], button[aria-label*="Siguiente" i]');
        if (btn) robustClick(btn);
      },
      prev: () => {
        const doc = typeof unsafeWindow !== "undefined" && unsafeWindow.document ? unsafeWindow.document : document;
        const btn = doc.querySelector('[data-testid="control-button-skip-back"], [data-testid="skip-back-button"], button[aria-label*="Previous" i], button[aria-label*="Anterior" i]');
        if (btn) robustClick(btn);
      },
      seek: (targetSeconds) => {
        const doc = typeof unsafeWindow !== "undefined" && unsafeWindow.document ? unsafeWindow.document : document;
        const bar = doc.querySelector('[data-testid="playback-progressbar"], [data-testid="progress-bar"]');
        const durElem = doc.querySelector('[data-testid="playback-duration"]');
        const totalDuration = durElem ? parseTime(durElem.textContent.trim()) : 0;
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
      },
    },

    ytmusic: {
      name: "YouTube Music",
      matches: () => window.location.hostname === "music.youtube.com",
      getMedia: () => document.querySelector("video"),
      getMetadata: () => {
        const bar = document.querySelector("ytmusic-player-bar");
        let title = "";
        let artist = "";
        let album = "";

        if (bar) {
          const titleElem = bar.querySelector(".title, yt-formatted-string.title");
          if (titleElem) title = titleElem.textContent.trim();

          const subtitle = bar.querySelector(".subtitle, .byline, .ytmusic-player-bar.byline");
          if (subtitle) {
            const links = subtitle.querySelectorAll("a");
            if (links.length > 0) {
              artist = links[0].textContent.trim();
              if (links.length > 1) album = links[1].textContent.trim();
            } else {
              const parts = subtitle.textContent.split("•").map((s) => s.trim());
              artist = parts[0] || "";
              if (parts.length > 1) album = parts[1] || "";
            }
          }
        }
        return { title, artist, album };
      },
      playPause: (media) => {
        const btn = document.querySelector("#play-pause-button, ytmusic-player-bar #play-pause-button");
        if (btn) return robustClick(btn);
        if (media) return media.paused ? media.play().catch(() => {}) : media.pause();
      },
      next: () => {
        const btn = document.querySelector(".next-button, ytmusic-player-bar .next-button");
        if (btn) robustClick(btn);
      },
      prev: () => {
        const btn = document.querySelector(".previous-button, ytmusic-player-bar .previous-button");
        if (btn) robustClick(btn);
      },
      seek: (targetSeconds) => {
        const v = document.querySelector("video");
        if (v && Number.isFinite(v.duration)) {
          v.currentTime = targetSeconds;
        }
      },
    },

    youtube: {
      name: "YouTube",
      matches: () => window.location.hostname.includes("youtube.com") && window.location.hostname !== "music.youtube.com",
      getMedia: () => document.querySelector("video"),
      getMetadata: () => {
        let rawTitle = "";
        const titleElem = document.querySelector("h1.ytd-watch-metadata yt-formatted-string, ytd-watch-metadata #title h1, #title h1 yt-formatted-string");
        if (titleElem) rawTitle = titleElem.textContent.trim();
        if (!rawTitle && navigator.mediaSession?.metadata?.title) {
          rawTitle = navigator.mediaSession.metadata.title;
        }
        if (!rawTitle) {
          rawTitle = document.title.replace(/ - YouTube$/, "").trim();
        }

        const channelElem = document.querySelector("#channel-name a, ytd-channel-name a, #owner-name a");
        const channel = channelElem ? channelElem.textContent.trim() : "";

        const parsed = parseYouTubeSong(rawTitle, channel);
        return { title: parsed.title, artist: parsed.artist, album: "" };
      },
      playPause: (media) => {
        const btn = document.querySelector(".ytp-play-button");
        if (btn) return robustClick(btn);
        if (media) return media.paused ? media.play().catch(() => {}) : media.pause();
      },
      next: () => {
        const btn = document.querySelector(".ytp-next-button");
        if (btn) robustClick(btn);
      },
      prev: () => {
        const btn = document.querySelector(".ytp-prev-button");
        if (btn) robustClick(btn);
        else {
          const v = document.querySelector("video");
          if (v) v.currentTime = 0;
        }
      },
      seek: (targetSeconds) => {
        const v = document.querySelector("video");
        if (v && Number.isFinite(v.duration)) {
          v.currentTime = targetSeconds;
        }
      },
    },

    amazon: {
      name: "Amazon Music",
      matches: () => window.location.hostname.includes("music.amazon."),
      getMedia: () => document.querySelector("audio, video"),
      getMetadata: () => {
        let title = "";
        let artist = "";
        let album = "";

        const titleElem = document.querySelector('[data-test="track-name"], music-horizontal-item [primary-text], .trackTitle, music-player-bar .track-title, [class*="trackTitle"]');
        if (titleElem) title = titleElem.textContent.trim();

        const artistElem = document.querySelector('[data-test="artist-name"], music-horizontal-item [secondary-text-1] a, music-horizontal-item [secondary-text-1], .trackArtist, [class*="trackArtist"]');
        if (artistElem) artist = artistElem.textContent.trim();

        const albumElem = document.querySelector('[data-test="album-name"], music-horizontal-item [secondary-text-2] a, music-horizontal-item [secondary-text-2]');
        if (albumElem) album = albumElem.textContent.trim();

        return { title, artist, album };
      },
      playPause: (media) => {
        const btn = document.querySelector('music-button[icon-name="play"], music-button[icon-name="pause"], [data-test="play-button"], button[aria-label*="Play" i], button[aria-label*="Pause" i]');
        if (btn) return robustClick(btn);
        if (media) return media.paused ? media.play().catch(() => {}) : media.pause();
      },
      next: () => {
        const btn = document.querySelector('music-button[icon-name="next"], [data-test="next-button"], button[aria-label*="Next" i]');
        if (btn) robustClick(btn);
      },
      prev: () => {
        const btn = document.querySelector('music-button[icon-name="previous"], [data-test="previous-button"], button[aria-label*="Previous" i]');
        if (btn) robustClick(btn);
      },
      seek: (targetSeconds) => {
        const media = document.querySelector("audio, video");
        if (media && Number.isFinite(media.duration)) {
          media.currentTime = targetSeconds;
        }
      },
    },
  };

  function getActiveProvider() {
    for (const key of Object.keys(PROVIDERS)) {
      if (PROVIDERS[key].matches()) {
        return PROVIDERS[key];
      }
    }
    return PROVIDERS.spotify;
  }

  function scrapePlaybackState() {
    const provider = getActiveProvider();
    const media = provider.getMedia() || document.querySelector("video, audio");
    let meta = provider.getMetadata();

    // Fallbacks to navigator.mediaSession
    if (!meta.title && navigator.mediaSession?.metadata?.title) {
      meta.title = navigator.mediaSession.metadata.title;
    }
    if (!meta.artist && navigator.mediaSession?.metadata?.artist) {
      meta.artist = navigator.mediaSession.metadata.artist;
    }
    if (!meta.album && navigator.mediaSession?.metadata?.album) {
      meta.album = navigator.mediaSession.metadata.album;
    }

    let duration = 0;
    let position = 0;
    let isPaused = true;

    if (media) {
      if (Number.isFinite(media.duration) && media.duration > 0) {
        duration = Math.round(media.duration * 10) / 10;
      }
      if (Number.isFinite(media.currentTime) && media.currentTime >= 0) {
        position = Math.round(media.currentTime * 100) / 100;
      }
      isPaused = Boolean(media.paused);
    } else if (provider.name === "Spotify") {
      const durElem = document.querySelector('[data-testid="playback-duration"]');
      if (durElem) duration = parseTime(durElem.textContent);

      const posElem = document.querySelector('[data-testid="playback-position"]');
      if (posElem) position = parseTime(posElem.textContent);

      const playPauseBtn = document.querySelector('[data-testid="control-button-playpause"]');
      if (playPauseBtn) {
        const label = (playPauseBtn.getAttribute("aria-label") || "").toLowerCase();
        isPaused = !(label.includes("pause") || label.includes("pausar"));
      }
    }

    return {
      type: "playback_update",
      provider: provider.name,
      title: meta.title || "",
      artist: meta.artist || "",
      album: meta.album || "",
      duration: duration,
      position: position,
      isPaused: isPaused,
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

      const provider = getActiveProvider();
      let container = null;

      if (provider.name === "Spotify") {
        container = document.querySelector('[data-testid="now-playing-bar"], footer, .now-playing-bar');
      } else if (provider.name === "YouTube Music") {
        container = document.querySelector("ytmusic-player-bar .middle-controls, ytmusic-player-bar");
      } else if (provider.name === "YouTube") {
        container = document.querySelector("#below, #top-row.ytd-watch-metadata, #masthead-container");
      } else if (provider.name === "Amazon Music") {
        container = document.querySelector('music-horizontal-item, [data-test="player"], #transport, music-player-bar');
      }

      if (container) {
        container.appendChild(badge);
      } else {
        document.body.appendChild(badge);
      }
    }

    const provider = getActiveProvider();
    if (badge._lastConnected !== connected || badge._lastProvider !== provider.name) {
      badge._lastConnected = connected;
      badge._lastProvider = provider.name;
      badge.textContent = connected
        ? `MiniLyrics: Connected 🟢 (${provider.name})`
        : `MiniLyrics: Disconnected ⚪ (${provider.name})`;
      badge.className = connected ? "minilyrics-connected" : "minilyrics-disconnected";
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
      if (lastSentState && Math.abs(current.position - lastSentState.position) >= 0.5) {
        sendPlaybackUpdate(current);
      }
    }
  }

  function executeCommand(cmd) {
    console.log("[MiniLyrics] Executing command:", cmd);
    if (!cmd || !cmd.action) return;

    const provider = getActiveProvider();
    const media = provider.getMedia() || document.querySelector("video, audio");

    if (cmd.action === "seek" && typeof cmd.position === "number") {
      if (media && Number.isFinite(media.duration)) {
        try {
          media.currentTime = cmd.position;
        } catch (_) {}
      }
      if (provider.seek) {
        provider.seek(cmd.position);
      }
      return;
    }

    if (cmd.action === "play_pause") {
      provider.playPause(media);
    } else if (cmd.action === "next") {
      provider.next(media);
    } else if (cmd.action === "prev") {
      provider.prev(media);
    }
  }

  function connect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
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
          executeCommand(data);
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
      () => {
        setTimeout(() => pollAndSync(true), 150);
      },
      true
    );

    if (navigator.mediaSession) {
      const origSetActionHandler = navigator.mediaSession.setActionHandler;
      if (typeof origSetActionHandler === "function") {
        navigator.mediaSession.setActionHandler = function (action, handler) {
          return origSetActionHandler.call(this, action, function () {
            setTimeout(() => pollAndSync(true), 50);
            if (typeof handler === "function") {
              return handler.apply(this, arguments);
            }
          });
        };
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
