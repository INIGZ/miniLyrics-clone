"""MiniLyrics WebSocket Server.

Runs an asyncio WebSocket server inside a QThread to receive playback updates
from the Spotify browser extension or mock Spotify simulator.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from PyQt5.QtCore import QThread, pyqtSignal
import websockets

logger = logging.getLogger(__name__)


class WebSocketServer(QThread):
    """QThread-based WebSocket server listening for playback updates."""

    playback_updated = pyqtSignal(dict)

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, parent=None) -> None:
        super().__init__(parent)
        self.host = host
        self.port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._server = None

    async def _handle_connection(self, websocket: Any) -> None:
        """Handle incoming WebSocket client messages."""
        try:
            async for raw_message in websocket:
                if not raw_message:
                    continue
                if isinstance(raw_message, bytes):
                    message_str = raw_message.decode("utf-8", errors="ignore")
                else:
                    message_str = str(raw_message)

                try:
                    payload = json.loads(message_str)
                    if isinstance(payload, dict):
                        self.playback_updated.emit(payload)
                except (json.JSONDecodeError, ValueError):
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.debug("WebSocket connection error: %s", e)

    async def _run_server(self) -> None:
        """Run the WebSocket server until stop_event is set."""
        self._stop_event = asyncio.Event()
        try:
            async with websockets.serve(self._handle_connection, self.host, self.port) as server:
                self._server = server
                logger.info("WebSocket server listening on ws://%s:%d", self.host, self.port)
                await self._stop_event.wait()
        except asyncio.CancelledError:
            pass
        except OSError as e:
            logger.warning("Failed to bind WebSocket server on %s:%d: %s", self.host, self.port, e)

    def run(self) -> None:
        """Main thread loop running asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_server())
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                self._loop.close()
                self._loop = None

    def stop(self) -> None:
        """Signal the event loop to stop and wait for thread to terminate."""
        if self._loop and self._loop.is_running() and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self.wait(2000)
        if self.isRunning():
            self.terminate()
            self.wait(500)
