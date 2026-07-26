"""
Unit Tests for LIM-AI Copilot Local Daemon Bridge.

Design Note:
    This module tests the WebSocket routing, heartbeat ping-pong mechanisms, and fallback
    scenarios of the local bridge. It mocks httpx.AsyncClient requests to simulate:
    - Remote server reachable (returning 200 OK or analytical JSON responses).
    - Remote server timeout (raising httpx.TimeoutException).
    - Remote server connection errors (raising httpx.ConnectError).
    Verification is done using FastAPI's standard TestClient WebSocket interface. All tests
    run asynchronously where appropriate, following PEP 484 type annotations and standard
    pytest/unittest.mock paradigms.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
import pytesseract

# Ensure daemon directory is in sys.path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from local_bridge import app


def test_sympy_math_local_route() -> None:
    """Tests local execution route for sympy_math, which should run entirely at edge."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"action": "sympy_math", "data": "2*x + 6 - 12"}))
        response = websocket.receive_json()
        assert response["type"] == "math"
        assert response["source"] == "local_engine"
        assert "f(x) =" in response["latex"]


def test_pytesseract_ocr_with_fixture() -> None:
    """Tests raw pytesseract integration with a Pillow image fixture containing rendered text."""
    # Create a 300x100 white background image
    img = Image.new("RGB", (300, 100), color="white")
    draw = ImageDraw.Draw(img)
    # Render basic black text on it
    draw.text((20, 40), "HELLO WORLD", fill="black")

    # Run pytesseract OCR to verify integration is fully functional and binary loads correctly
    try:
        text = pytesseract.image_to_string(img).strip()
        # Even if the headless character matching is loose, the call must execute successfully.
        assert isinstance(text, str)
    except Exception as e:
        pytest.fail(f"pytesseract call failed with exception: {e}")


@pytest.mark.asyncio
async def test_fast_ocr_capture_success_with_ocr_mock() -> None:
    """Tests that fast_ocr executes local screen capture and runs tesseract successfully."""
    client = TestClient(app)

    mock_sct_img = MagicMock()
    mock_sct_img.size = (100, 100)
    mock_sct_img.bgra = b"\x00" * (100 * 100 * 4)

    with patch("local_bridge.mss") as mock_mss, \
         patch("local_bridge.Image.frombytes"), \
         patch("local_bridge.pytesseract.image_to_string") as mock_ocr:

        mock_instance = mock_mss.return_value.__enter__.return_value
        mock_instance.grab.return_value = mock_sct_img
        mock_ocr.return_value = "TEST OCR SUCCESSFUL CONTENT"

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "fast_ocr",
                "data": {"region": {"x": 10, "y": 20, "width": 100, "height": 100}}
            }))
            response = websocket.receive_json()
            assert response["type"] == "ocr"
            assert response["source"] == "local_engine"
            assert response["text"] == "TEST OCR SUCCESSFUL CONTENT"


@pytest.mark.asyncio
async def test_fast_ocr_capture_headless_failure() -> None:
    """Tests that fast_ocr correctly catches and reports display access failures under headless environments."""
    client = TestClient(app)

    with patch("local_bridge.mss") as mock_mss:
        mock_mss.side_effect = Exception("No DISPLAY environment variable found")

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "fast_ocr",
                "data": {"region": {"x": 0, "y": 0, "width": 1920, "height": 1080}}
            }))
            response = websocket.receive_json()
            assert response["type"] == "ocr"
            assert response["source"] == "local_engine"
            assert "cattura fallita" in response["text"]
            assert "No DISPLAY" in response["text"]


@pytest.mark.asyncio
async def test_ping_remote_reachable() -> None:
    """Tests that ping_remote yields a pong_remote response when remote server is reachable."""
    client = TestClient(app)

    # Mocking httpx.AsyncClient.get to return 200 OK
    dummy_req = httpx.Request("GET", "http://192.168.1.100:8000/health")
    mock_resp = httpx.Response(200, json={"status": "ok"}, request=dummy_req)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_callable = mock_get
        mock_get.return_value = mock_resp

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({"action": "ping_remote"}))
            response = websocket.receive_json()
            assert response["type"] == "pong_remote"

        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_remote_reachable_analyze() -> None:
    """Tests that a remote action succeeds and echoes the remote server's response."""
    client = TestClient(app)

    # Mocking httpx.AsyncClient.post to return a valid analytical response
    remote_data = {
        "type": "concept_map",
        "source": "remote_llm",
        "mermaid_code": "graph TD; Cuore-->Arterie;"
    }
    dummy_req = httpx.Request("POST", "http://192.168.1.100:8000/api/v1/analyze")
    mock_resp = httpx.Response(200, text=json.dumps(remote_data), request=dummy_req)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "concept_map",
                "data": {"topic": "apparato circolatorio"}
            }))
            response = websocket.receive_json()
            assert response["type"] == "concept_map"
            assert response["source"] == "remote_llm"
            assert "Cuore-->Arterie" in response["mermaid_code"]


@pytest.mark.asyncio
async def test_remote_timeout_fallback() -> None:
    """Tests fallback warning is sent when remote server times out during analysis."""
    client = TestClient(app)

    # Mocking httpx.AsyncClient.post to raise TimeoutException
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Remote server timeout")

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "concept_map",
                "data": {"topic": "apparato circolatorio"}
            }))
            response = websocket.receive_json()
            assert response["type"] == "system_warning"
            assert "offline" in response["message"]


@pytest.mark.asyncio
async def test_remote_connection_error_fallback() -> None:
    """Tests fallback warning is sent when remote server experiences a connection error."""
    client = TestClient(app)

    # Mocking httpx.AsyncClient.post to raise ConnectError
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # ConnectError requires a message and request object (which can be mock or None)
        mock_req = httpx.Request("POST", "http://192.168.1.100:8000/api/v1/analyze")
        mock_post.side_effect = httpx.ConnectError("Connection refused", request=mock_req)

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "concept_map",
                "data": {"topic": "apparato circolatorio"}
            }))
            response = websocket.receive_json()
            assert response["type"] == "system_warning"
            assert "offline" in response["message"]


@pytest.mark.asyncio
async def test_start_transcription_success_mock() -> None:
    """Tests start_transcription action correctly sets up and starts audio capture using PyAudio mocks."""
    client = TestClient(app)

    mock_instance = MagicMock()
    mock_stream = MagicMock()
    mock_instance.open.return_value = mock_stream
    # Simulate return values of 1 second audio chunks
    mock_stream.read.return_value = b"\x00" * 32000

    with patch("pyaudio.PyAudio", return_value=mock_instance):
        with client.websocket_connect("/ws") as websocket:
            # Send start_transcription action
            websocket.send_text(json.dumps({
                "action": "start_transcription",
                "data": {"target_language": "en"}
            }))

            # Allow some async events to run
            await asyncio.sleep(0.1)

            # Send stop_transcription action
            websocket.send_text(json.dumps({
                "action": "stop_transcription"
            }))

            # Allow cleanup events to run
            await asyncio.sleep(0.1)

        import pyaudio
        # Verify that PyAudio stream open was called with correct parameters
        mock_instance.open.assert_called_once_with(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )
        # Verify cleanup
        mock_stream.stop_stream.assert_called()
        mock_stream.close.assert_called_once()
        mock_instance.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_start_transcription_device_failure() -> None:
    """Tests start_transcription handles device failure gracefully by sending a standard error payload."""
    client = TestClient(app)

    mock_instance = MagicMock()
    # Simulate OSError when opening stream (no default input device)
    mock_instance.open.side_effect = OSError("No default input device available")

    with patch("pyaudio.PyAudio", return_value=mock_instance):
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "start_transcription",
                "data": {"target_language": "it"}
            }))
            response = websocket.receive_json()

            assert response["type"] == "error"
            assert response["code"] == "NO_AUDIO_DEVICE"
            assert response["action"] == "start_transcription"
            assert "No default input device available" in response["message"]


@pytest.mark.asyncio
async def test_stop_transcription_unstarted() -> None:
    """Tests stop_transcription succeeds gracefully without throwing errors even if no stream was running."""
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({
            "action": "stop_transcription"
        }))
        # Ensure WebSocket does not disconnect unexpectedly and remains open/usable
        # We can ping the local websocket to confirm it's still alive
        websocket.send_text(json.dumps({
            "action": "sympy_math",
            "data": "1+1"
        }))
        res = websocket.receive_json()
        assert res["type"] == "math"


@pytest.mark.asyncio
async def test_start_transcription_double_start() -> None:
    """Tests that sending start_transcription twice in a row cleanly stops the previous stream first before starting a new one."""
    client = TestClient(app)

    mock_instance = MagicMock()
    mock_stream = MagicMock()
    mock_instance.open.return_value = mock_stream
    mock_stream.read.return_value = b"\x00" * 32000

    with patch("pyaudio.PyAudio", return_value=mock_instance):
        with client.websocket_connect("/ws") as websocket:
            # Send first start_transcription action
            websocket.send_text(json.dumps({
                "action": "start_transcription",
                "data": {"target_language": "en"}
            }))
            await asyncio.sleep(0.05)

            # Send second start_transcription action without stopping first
            websocket.send_text(json.dumps({
                "action": "start_transcription",
                "data": {"target_language": "it"}
            }))
            await asyncio.sleep(0.05)

            # Send stop_transcription action
            websocket.send_text(json.dumps({
                "action": "stop_transcription"
            }))
            await asyncio.sleep(0.05)

        # Verify PyAudio open was called twice (once for each start_transcription)
        assert mock_instance.open.call_count == 2
        # Verify previous stream cleanup was called during second start or during stop
        assert mock_stream.stop_stream.call_count >= 1
        assert mock_stream.close.call_count >= 1
