"""MiniLyrics Mock Spotify Simulator.

Simulates Spotify Web Player playback events over WebSocket.
Can run as a client connecting to ws://127.0.0.1:8765 or as a standalone
WebSocket server emitting playback_update messages.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any
import websockets

DEFAULT_WS_URL = "ws://127.0.0.1:8765"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TITLE = "Bohemian Rhapsody"
DEFAULT_ARTIST = "Queen"
DEFAULT_ALBUM = "A Night at the Opera"
DEFAULT_DURATION = 354.0  # 5 minutes 54 seconds
DEFAULT_TICK_INTERVAL = 0.25  # 250ms tick rate matching extension
DEFAULT_RECONNECT_INTERVAL = 2.0


def format_seconds(seconds: float) -> str:
    """Format seconds into MM:SS string."""
    sec = max(0, int(round(seconds)))
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


class SpotifySimulator:
    """Maintains simulated Spotify playback state."""

    def __init__(
        self,
        title: str = DEFAULT_TITLE,
        artist: str = DEFAULT_ARTIST,
        album: str = DEFAULT_ALBUM,
        duration: float = DEFAULT_DURATION,
        start_position: float = 0.0,
        is_paused: bool = False,
        step: float = DEFAULT_TICK_INTERVAL,
        interval: float = DEFAULT_TICK_INTERVAL,
        speed: float = 1.0,
        loop: bool = True,
    ) -> None:
        self.title = title
        self.artist = artist
        self.album = album
        self.duration = max(0.1, float(duration))
        self.position = max(0.0, min(float(start_position), self.duration))
        self.is_paused = is_paused
        self.step = step
        self.interval = interval
        self.speed = max(0.01, speed)
        self.loop = loop

    def get_payload(self) -> dict[str, Any]:
        """Generate playback_update message matching MiniLyrics extension protocol."""
        return {
            "type": "playback_update",
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": round(float(self.duration), 2),
            "position": round(float(self.position), 2),
            "isPaused": bool(self.is_paused),
        }

    def get_json(self) -> str:
        """Serialize payload to JSON string."""
        return json.dumps(self.get_payload(), ensure_ascii=False)

    def tick(self) -> bool:
        """Advance playback position by step * speed. Returns False if reached end without looping."""
        if self.is_paused:
            return True

        self.position += self.step * self.speed
        if self.position >= self.duration:
            if self.loop:
                self.position = 0.0
                return True
            else:
                self.position = self.duration
                self.is_paused = True
                return False
        return True

    def format_status(self) -> str:
        """Format clean CLI status line."""
        pos_str = format_seconds(self.position)
        dur_str = format_seconds(self.duration)
        pct = (self.position / self.duration) * 100 if self.duration > 0 else 0
        state_icon = "⏸" if self.is_paused else "▶"
        state_label = " (PAUSED)" if self.is_paused else ""
        return (
            f"[Mock Spotify] {state_icon} {pos_str} / {dur_str} ({pct:5.1f}%) "
            f"| {self.title} - {self.artist}{state_label}"
        )


async def run_client(
    sim: SpotifySimulator,
    url: str = DEFAULT_WS_URL,
    max_ticks: int | None = None,
    verbose: bool = True,
) -> None:
    """Run simulator as a WebSocket client connecting to MiniLyrics overlay."""
    ticks_done = 0
    sleep_delay = sim.interval / sim.speed

    while max_ticks is None or ticks_done < max_ticks:
        try:
            if verbose:
                print(f"[Simulator] Connecting to {url}...")
            async with websockets.connect(url) as ws:
                if verbose:
                    print(f"[Simulator] Connected to {url}! Emitting playback updates...")
                while max_ticks is None or ticks_done < max_ticks:
                    payload_json = sim.get_json()
                    await ws.send(payload_json)
                    if verbose:
                        print(sim.format_status())

                    ticks_done += 1
                    if max_ticks is not None and ticks_done >= max_ticks:
                        break

                    await asyncio.sleep(sleep_delay)
                    has_more = sim.tick()
                    if not has_more and not sim.loop:
                        # Send the final paused state
                        await ws.send(sim.get_json())
                        if verbose:
                            print(sim.format_status())
                            print("[Simulator] Playback finished.")
                        return

        except (OSError, websockets.exceptions.WebSocketException) as exc:
            if verbose:
                print(
                    f"[Simulator] Connection to {url} failed ({exc}). "
                    f"Retrying in {DEFAULT_RECONNECT_INTERVAL}s..."
                )
            await asyncio.sleep(DEFAULT_RECONNECT_INTERVAL)


async def run_server(
    sim: SpotifySimulator,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    max_ticks: int | None = None,
    verbose: bool = True,
) -> None:
    """Run simulator as a WebSocket server emitting playback updates to all connected clients."""
    clients: set[websockets.WebSocketServerProtocol] = set()
    sleep_delay = sim.interval / sim.speed
    ticks_done = 0
    stop_event = asyncio.Event()

    async def handler(websocket: websockets.WebSocketServerProtocol) -> None:
        clients.add(websocket)
        if verbose:
            print(f"[Server] Client connected: {websocket.remote_address} (Total clients: {len(clients)})")
        try:
            # Send current state immediately on connect
            await websocket.send(sim.get_json())
            await websocket.wait_closed()
        finally:
            clients.remove(websocket)
            if verbose:
                print(f"[Server] Client disconnected: {websocket.remote_address}")

    async def ticker() -> None:
        nonlocal ticks_done
        while not stop_event.is_set():
            if clients:
                payload_json = sim.get_json()
                websockets.broadcast(clients, payload_json)
            if verbose:
                client_info = f"[{len(clients)} clients]"
                print(f"{sim.format_status()} {client_info}")

            ticks_done += 1
            if max_ticks is not None and ticks_done >= max_ticks:
                stop_event.set()
                break

            await asyncio.sleep(sleep_delay)
            has_more = sim.tick()
            if not has_more and not sim.loop:
                if clients:
                    websockets.broadcast(clients, sim.get_json())
                if verbose:
                    print(sim.format_status())
                    print("[Server] Playback finished.")
                stop_event.set()
                break

    if verbose:
        print(f"[Server] Starting WebSocket server on ws://{host}:{port} ...")

    async with websockets.serve(handler, host, port):
        if verbose:
            print(f"[Server] Listening on ws://{host}:{port}. Ready for connections.")
        ticker_task = asyncio.create_task(ticker())
        await stop_event.wait()
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass


def self_check() -> None:
    """Assert-based verification of simulator functionality."""
    print("Running self-check tests...")

    # 1. Simulator state initialization
    sim = SpotifySimulator(
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        duration=354.0,
        start_position=0.0,
    )
    p = sim.get_payload()
    assert p["type"] == "playback_update"
    assert p["title"] == "Bohemian Rhapsody"
    assert p["artist"] == "Queen"
    assert p["album"] == "A Night at the Opera"
    assert p["duration"] == 354.0
    assert p["position"] == 0.0
    assert p["isPaused"] is False

    # 2. Stepping
    sim.tick()
    assert sim.position == 0.25
    assert sim.get_payload()["position"] == 0.25

    # 3. Looping
    sim.position = 353.9
    sim.tick()
    assert sim.position == 0.0

    # 4. Non-looping stop
    sim2 = SpotifySimulator(duration=10.0, start_position=9.9, loop=False)
    res = sim2.tick()
    assert res is False
    assert sim2.position == 10.0
    assert sim2.is_paused is True

    # 5. Formatter
    assert "Queen" in sim.format_status()
    assert format_seconds(354) == "05:54"
    assert format_seconds(0) == "00:00"
    assert format_seconds(75) == "01:15"

    # 6. WebSocket loopback test (server & client)
    async def loopback_test() -> None:
        test_port = 8788
        sim_srv = SpotifySimulator(title="Test Song", artist="Tester", duration=100.0)
        received_msgs: list[dict[str, Any]] = []

        async def srv_handler(ws: websockets.WebSocketServerProtocol) -> None:
            await ws.send(sim_srv.get_json())
            try:
                await ws.wait_closed()
            except Exception:
                pass

        async with websockets.serve(srv_handler, "127.0.0.1", test_port):
            async with websockets.connect(f"ws://127.0.0.1:{test_port}") as client_ws:
                data = await client_ws.recv()
                msg = json.loads(data)
                received_msgs.append(msg)

        assert len(received_msgs) == 1
        assert received_msgs[0]["type"] == "playback_update"
        assert received_msgs[0]["title"] == "Test Song"
        assert received_msgs[0]["artist"] == "Tester"

    asyncio.run(loopback_test())
    print("Self-check completed successfully! All assertions passed.")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MiniLyrics Mock Spotify Simulator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["client", "server"],
        default="client",
        help="Run as WebSocket client (sending to MiniLyrics) or server (broadcasting to clients)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_WS_URL,
        help="WebSocket server URL for client mode",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Host to bind for server mode",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Port to bind for server mode",
    )
    parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="Track title",
    )
    parser.add_argument(
        "--artist",
        default=DEFAULT_ARTIST,
        help="Artist name",
    )
    parser.add_argument(
        "--album",
        default=DEFAULT_ALBUM,
        help="Album name",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help="Track duration in seconds",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=0.0,
        help="Start position in seconds",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=DEFAULT_TICK_INTERVAL,
        help="Time advance per tick in seconds",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_TICK_INTERVAL,
        help="Tick delay interval in seconds",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Simulation speed multiplier (e.g. 2.0 = 2x real-time)",
    )
    parser.add_argument(
        "--paused",
        action="store_true",
        help="Start in paused state",
    )
    parser.add_argument(
        "--no-loop",
        action="store_true",
        help="Do not loop when track ends",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Maximum ticks to run before exiting (useful for testing)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run built-in self-check assertions and exit",
    )
    return parser.parse_args(args)


def main() -> None:
    opts = parse_args()
    if opts.test:
        self_check()
        return

    sim = SpotifySimulator(
        title=opts.title,
        artist=opts.artist,
        album=opts.album,
        duration=opts.duration,
        start_position=opts.start,
        is_paused=opts.paused,
        step=opts.step,
        interval=opts.interval,
        speed=opts.speed,
        loop=not opts.no_loop,
    )

    try:
        if opts.mode == "server":
            asyncio.run(
                run_server(
                    sim,
                    host=opts.host,
                    port=opts.port,
                    max_ticks=opts.max_ticks,
                )
            )
        else:
            asyncio.run(
                run_client(
                    sim,
                    url=opts.url,
                    max_ticks=opts.max_ticks,
                )
            )
    except KeyboardInterrupt:
        print("\n[Simulator] Stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
