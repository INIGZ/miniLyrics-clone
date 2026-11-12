import asyncio
import json
import time
from PyQt5.QtCore import QCoreApplication
import pytest
import websockets
from src.server.ws_server import WebSocketServer


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_ws_server_init():
    server = WebSocketServer(host="127.0.0.1", port=9876)
    assert server.host == "127.0.0.1"
    assert server.port == 9876


def test_ws_server_start_stop(qapp):
    server = WebSocketServer(host="127.0.0.1", port=9877)
    server.start()
    time.sleep(0.15)
    assert server.isRunning()
    server.stop()
    assert not server.isRunning()


def test_ws_server_receives_playback_payload(qapp):
    port = 9878
    server = WebSocketServer(host="127.0.0.1", port=port)
    received_payloads = []
    server.playback_updated.connect(lambda d: received_payloads.append(d))

    server.start()
    time.sleep(0.15)

    test_payload = {
        "type": "playback_update",
        "title": "Bohemian Rhapsody",
        "artist": "Queen",
        "album": "A Night at the Opera",
        "position": 42.0,
        "duration": 354.0,
        "isPaused": False,
    }

    async def send_message():
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(json.dumps(test_payload))
            await asyncio.sleep(0.05)

    asyncio.run(send_message())
    qapp.processEvents()

    server.stop()

    assert len(received_payloads) == 1
    assert received_payloads[0]["title"] == "Bohemian Rhapsody"
    assert received_payloads[0]["artist"] == "Queen"
    assert received_payloads[0]["position"] == 42.0


def test_ws_server_sends_command_to_connected_client(qapp):
    port = 9879
    server = WebSocketServer(host="127.0.0.1", port=port)
    server.start()
    time.sleep(0.15)

    received_commands = []

    async def client_listener():
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            # Allow registration
            await asyncio.sleep(0.05)
            server.send_command("play_pause")
            server.send_command("seek", position=12.5)
            msg1 = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg2 = await asyncio.wait_for(ws.recv(), timeout=2.0)
            received_commands.append(json.loads(msg1))
            received_commands.append(json.loads(msg2))

    asyncio.run(client_listener())
    server.stop()

    assert len(received_commands) == 2
    assert received_commands[0]["action"] == "play_pause"
    assert received_commands[1]["action"] == "seek"
    assert received_commands[1]["position"] == 12.5
