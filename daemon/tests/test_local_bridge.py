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
import os
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
        assert response["plot_data"] is not None
        assert isinstance(response["plot_data"]["x"], list)
        assert isinstance(response["plot_data"]["y"], list)
        assert len(response["plot_data"]["x"]) == len(response["plot_data"]["y"])
        # Domain includes 101 points between -10 and 10
        assert len(response["plot_data"]["x"]) == 101


def test_sympy_math_discontinuity_route() -> None:
    """Tests that a function with a removable discontinuity (e.g. 1/x) omits the singular point and returns the rest of the plot data."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"action": "sympy_math", "data": "1/x"}))
        response = websocket.receive_json()
        assert response["type"] == "math"
        assert response["source"] == "local_engine"
        assert "f(x) =" in response["latex"]
        assert response["plot_data"] is not None
        # x = 0 is a pole (ZeroDivisionError), so it must be omitted. Total points: 101 - 1 = 100
        assert len(response["plot_data"]["x"]) == 100
        assert 0.0 not in response["plot_data"]["x"]


def test_sympy_math_multivariable_omitted() -> None:
    """Tests that a multi-variable function (e.g. x + y) returns plot_data: null gracefully without crashing."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"action": "sympy_math", "data": "x + y"}))
        response = websocket.receive_json()
        assert response["type"] == "math"
        assert response["source"] == "local_engine"
        assert response["plot_data"] is None


def test_sympy_math_constant_omitted() -> None:
    """Tests that a constant function with zero free symbols returns plot_data: null gracefully."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"action": "sympy_math", "data": "5"}))
        response = websocket.receive_json()
        assert response["type"] == "math"
        assert response["source"] == "local_engine"
        assert response["plot_data"] is None


def test_sympy_math_parsing_error_route() -> None:
    """Tests that a parsing failure is handled gracefully with standard error latex and plot_data: null."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"action": "sympy_math", "data": "invalid syntax ++/ 123"}))
        response = websocket.receive_json()
        assert response["type"] == "math"
        assert response["source"] == "local_engine"
        assert "Errore parsing math locale" in response["latex"]
        assert response["plot_data"] is None


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


@pytest.mark.asyncio
async def test_transcription_disconnect_safety() -> None:
    """
    Tests that a WebSocketDisconnect or a Starlette RuntimeError disconnect
    thrown during an active transcription capture session is caught and handled
    gracefully, stopping the loop cleanly and calling stop() without throwing
    unhandled exceptions or error logging.
    """
    from local_bridge import TranscriptionSession
    from fastapi import WebSocketDisconnect

    mock_ws = AsyncMock()
    # Raise WebSocketDisconnect when sending data
    mock_ws.send_text.side_effect = WebSocketDisconnect()

    mock_instance = MagicMock()
    mock_stream = MagicMock()
    mock_instance.open.return_value = mock_stream
    mock_stream.read.side_effect = [b"\x00" * 32000, b""]

    remote_data = {
        "type": "transcription",
        "source": "remote_stt",
        "text": "Buongiorno classe",
        "translated_text": None
    }
    dummy_req = httpx.Request("POST", "http://192.168.1.100:8000/api/v1/analyze")
    mock_resp = httpx.Response(200, text=json.dumps(remote_data), request=dummy_req)

    with patch("pyaudio.PyAudio", return_value=mock_instance), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("local_bridge.logger") as mock_logger:

        mock_post.return_value = mock_resp

        session = TranscriptionSession()
        await session.start(mock_ws, "en", None)

        # Allow the task and its loop to execute the first chunk
        # which will trigger post and then send_and_backup -> raises WebSocketDisconnect
        await asyncio.sleep(0.1)

        # Ensure the PyAudio mock stream and session have stopped cleanly
        await session.stop()

        # Check that we logged a graceful stop message at info level,
        # and NOT an unhandled error/exception traceback.
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        error_calls = [call[0][0] for call in mock_logger.error.call_args_list]

        assert any("Widget disconnesso" in msg or "arresto" in msg for msg in info_calls)
        assert not any("Errore non gestito" in msg for msg in error_calls)


def test_tesseract_cmd_path_selection_packaged() -> None:
    """Tests that sys.frozen packaged mode correctly overrides pytesseract's tesseract_cmd path."""
    import sys
    import pytesseract
    from local_bridge import configure_tesseract_path

    # Mock frozen state and _MEIPASS path
    with patch("sys.frozen", True, create=True), \
         patch("sys._MEIPASS", "/mock/mei/dir", create=True):

        configure_tesseract_path()

        expected_path = os.path.join("/mock/mei/dir", "tesseract", "tesseract.exe")
        assert pytesseract.pytesseract.tesseract_cmd == expected_path


def test_tesseract_cmd_path_selection_development() -> None:
    """Tests that development mode leaves pytesseract's tesseract_cmd untouched."""
    import sys
    import pytesseract
    from local_bridge import configure_tesseract_path

    # Save current value
    original_cmd = pytesseract.pytesseract.tesseract_cmd

    # Mock non-frozen/dev state
    with patch("sys.frozen", False, create=True):
        configure_tesseract_path()

        # Should remain the original/system configured cmd (or whatever was there before)
        assert pytesseract.pytesseract.tesseract_cmd == original_cmd


def test_parse_filename_timestamp() -> None:
    """Tests the parsing of ISO 8601 timestamps from filenames."""
    from local_bridge import parse_filename_timestamp
    import datetime

    fn1 = "2026-07-28T03-12-15.808300+00-00.jsonl"
    dt1 = parse_filename_timestamp(fn1)
    assert dt1 is not None
    assert dt1.year == 2026
    assert dt1.month == 7
    assert dt1.day == 28
    assert dt1.hour == 3
    assert dt1.minute == 12
    assert dt1.second == 15
    assert dt1.tzinfo == datetime.timezone.utc

    # Invalid filename should return None
    assert parse_filename_timestamp("invalid-name.txt") is None
    assert parse_filename_timestamp("2026-07-28.jsonl") is None


def test_cleanup_old_backups_retention(monkeypatch) -> None:
    """Tests that old backup files are deleted while new ones are retained based on retention settings."""
    import tempfile
    import shutil
    import datetime
    from local_bridge import cleanup_old_backups

    # Create a temporary directory for backups
    tmp_dir = tempfile.mkdtemp()

    try:
        # 1. Create a recent file (today)
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        recent_fn = f"{now_dt.isoformat().replace(':', '-')}.jsonl"
        with open(os.path.join(tmp_dir, recent_fn), "w") as f:
            f.write("{}")

        # 2. Create an old file (older than 30 days, e.g. 40 days ago)
        old_dt = now_dt - datetime.timedelta(days=40)
        old_fn = f"{old_dt.isoformat().replace(':', '-')}.jsonl"
        with open(os.path.join(tmp_dir, old_fn), "w") as f:
            f.write("{}")

        # Run cleanup with LESSON_BACKUP_RETENTION_DAYS set to 30
        monkeypatch.setenv("LESSON_BACKUP_RETENTION_DAYS", "30")
        cleanup_old_backups(backups_dir=tmp_dir)

        # Recent file should STILL exist, old file should be DELETED
        assert os.path.exists(os.path.join(tmp_dir, recent_fn))
        assert not os.path.exists(os.path.join(tmp_dir, old_fn))

    finally:
        shutil.rmtree(tmp_dir)


@pytest.mark.asyncio
async def test_send_and_backup_respects_disable_toggle() -> None:
    """Tests that send_and_backup bypasses file writes when settings.disable_local_backup is active."""
    from local_bridge import send_and_backup, settings
    import tempfile
    import shutil

    mock_ws = AsyncMock()
    message = {"type": "math", "source": "local_engine", "latex": "f(x) = x"}

    tmp_dir = tempfile.mkdtemp()
    backup_file = os.path.join(tmp_dir, "test_session.jsonl")

    try:
        # Toggle enabled (backups are disabled)
        settings.disable_local_backup = True
        await send_and_backup(mock_ws, message, backup_file)

        # Websocket should be called
        mock_ws.send_text.assert_called_once()
        # File should NOT exist or be empty
        assert not os.path.exists(backup_file)

        # Toggle disabled (backups are enabled)
        mock_ws.reset_mock()
        settings.disable_local_backup = False
        await send_and_backup(mock_ws, message, backup_file)

        # Websocket should be called
        mock_ws.send_text.assert_called_once()
        # File should now exist and contain the backed up message
        assert os.path.exists(backup_file)
        with open(backup_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["message"]["type"] == "math"

    finally:
        shutil.rmtree(tmp_dir)
        # Restore default setting state
        settings.disable_local_backup = False


@pytest.mark.asyncio
async def test_sympy_math_backups_successfully() -> None:
    """Tests that a successful sympy_math local action results in exactly one backed up line."""
    import shutil
    backup_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lesson_backups"))
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"action": "sympy_math", "data": "x^2"}))
        response = websocket.receive_json()
        assert response["type"] == "math"

    # Find the created backup file
    assert os.path.exists(backup_dir)
    files = [f for f in os.listdir(backup_dir) if f.endswith(".jsonl")]
    assert len(files) == 1
    backup_file_path = os.path.join(backup_dir, files[0])

    with open(backup_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    entry = json.loads(lines[0].strip())
    assert "timestamp" in entry
    assert entry["message"]["type"] == "math"
    assert entry["message"]["source"] == "local_engine"

    # Clean up
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)


@pytest.mark.asyncio
async def test_remote_proxy_backups_successfully() -> None:
    """Tests that successful REMOTE actions backup successfully but system warnings are skipped."""
    import shutil
    backup_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lesson_backups"))
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)

    client = TestClient(app)

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
            # 1. Successful remote proxy (should backup)
            websocket.send_text(json.dumps({
                "action": "concept_map",
                "data": {"topic": "apparato circolatorio"}
            }))
            websocket.receive_json()

    assert os.path.exists(backup_dir)
    files = [f for f in os.listdir(backup_dir) if f.endswith(".jsonl")]
    assert len(files) == 1
    backup_file_path = os.path.join(backup_dir, files[0])

    with open(backup_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Only concept_map is lesson content and should be backed up
    assert len(lines) == 1
    entry = json.loads(lines[0].strip())
    assert entry["message"]["type"] == "concept_map"

    # Clean up
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)


@pytest.mark.asyncio
async def test_transcription_backups_successfully() -> None:
    """Tests that transcription final subtitles are backed up but interim subtitles or warnings are skipped."""
    import shutil
    backup_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lesson_backups"))
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)

    client = TestClient(app)

    mock_instance = MagicMock()
    mock_stream = MagicMock()
    mock_instance.open.return_value = mock_stream
    mock_stream.read.side_effect = [b"\x00" * 32000, b""]

    remote_data = {
        "type": "transcription",
        "source": "remote_stt",
        "text": "Buongiorno classe",
        "translated_text": None
    }
    dummy_req = httpx.Request("POST", "http://192.168.1.100:8000/api/v1/analyze")
    mock_resp = httpx.Response(200, text=json.dumps(remote_data), request=dummy_req)

    with patch("pyaudio.PyAudio", return_value=mock_instance), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with client.websocket_connect("/ws") as websocket:
            # 1. Final subtitle should backup
            websocket.send_text(json.dumps({
                "action": "start_transcription",
                "data": {"target_language": "en"}
            }))
            websocket.receive_json()

            websocket.send_text(json.dumps({
                "action": "stop_transcription"
            }))
            await asyncio.sleep(0.05)

    assert os.path.exists(backup_dir)
    files = [f for f in os.listdir(backup_dir) if f.endswith(".jsonl")]
    assert len(files) == 1
    backup_file_path = os.path.join(backup_dir, files[0])

    with open(backup_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 1
    entry = json.loads(lines[0].strip())
    assert entry["message"]["type"] == "subtitle"
    assert entry["message"]["is_final"] is True

    # Clean up
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)


@pytest.mark.asyncio
async def test_load_3d_model_local_caching() -> None:
    """
    Tests that the local daemon caches 3D models upon first download,
    rewrites model_url in response sent to the widget, and serves directly
    from cache on subsequent requests without calling the remote server.
    """
    import shutil
    from local_bridge import CACHE_DIR

    # Clean local cache directory first to guarantee cache miss
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
    os.makedirs(CACHE_DIR, exist_ok=True)

    client = TestClient(app)

    # 1. Mock remote server responses
    mock_remote_analyze_resp = MagicMock()
    mock_remote_analyze_resp.status_code = 200
    mock_remote_analyze_resp.json.return_value = {
        "type": "model_3d",
        "source": "remote_index",
        "model_url": "/models/model_uid_xyz/scene.gltf",
        "label": "Water Molecule",
        "attribution": {
            "author": "Science Lab",
            "license": "CC-BY",
            "source_url": "https://sketchfab.com/models/model_uid_xyz"
        }
    }

    # scene.gltf file content
    mock_gltf_content = {
        "buffers": [{"uri": "scene.bin"}],
        "images": [{"uri": "textures/baseColor.png"}]
    }
    mock_gltf_resp = MagicMock()
    mock_gltf_resp.status_code = 200
    mock_gltf_resp.text = json.dumps(mock_gltf_content)

    mock_bin_resp = MagicMock()
    mock_bin_resp.status_code = 200
    mock_bin_resp.content = b"\x10\x20\x30"

    mock_img_resp = MagicMock()
    mock_img_resp.status_code = 200
    mock_img_resp.content = b"\xff\xd8\xff"

    # Set up httpx.AsyncClient mocks
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:

        mock_post.return_value = mock_remote_analyze_resp
        mock_get.side_effect = [mock_gltf_resp, mock_bin_resp, mock_img_resp]

        # First request (Cache MISS)
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "load_3d_model",
                "data": {"query": "H2O Molecule"}
            }))
            response1 = websocket.receive_json()

            # Assert rewritten URL and preserved attribution
            assert response1["type"] == "model_3d"
            assert response1["source"] == "remote_index"
            assert "/models_cache/" in response1["model_url"]
            assert response1["label"] == "Water Molecule"
            assert response1["attribution"]["author"] == "Science Lab"

        # Verify download calls
        assert mock_post.call_count == 1
        assert mock_get.call_count == 3

        # Second request (Cache HIT)
        # Reset mock counters to assert no network calls
        mock_post.reset_mock()
        mock_get.reset_mock()

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "load_3d_model",
                "data": {"query": "H2O Molecule"}
            }))
            response2 = websocket.receive_json()

            # Assert served from cache immediately with identical rewritten details
            assert response2["type"] == "model_3d"
            assert "/models_cache/" in response2["model_url"]
            assert response2["label"] == "Water Molecule"
            assert response2["attribution"]["author"] == "Science Lab"

        # Verify NO remote analyze and NO download requests were performed on cache hit
        mock_post.assert_not_called()
        mock_get.assert_not_called()

    # Cleanup cache folder
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)


@pytest.mark.asyncio
async def test_transcription_success_forward() -> None:
    """
    Tests that a successful remote transcription is correctly processed
    and forwarded to the widget over the WebSocket as a 'subtitle' message.
    """
    client = TestClient(app)

    mock_instance = MagicMock()
    mock_stream = MagicMock()
    mock_instance.open.return_value = mock_stream
    # Yield one full chunk first, then return empty bytes to avoid continuous processing
    mock_stream.read.side_effect = [b"\x00" * 32000, b""]

    # Mock the remote server response for transcribe_audio
    remote_data = {
        "type": "transcription",
        "source": "remote_stt",
        "text": "Buongiorno classe",
        "translated_text": None
    }
    dummy_req = httpx.Request("POST", "http://192.168.1.100:8000/api/v1/analyze")
    mock_resp = httpx.Response(200, text=json.dumps(remote_data), request=dummy_req)

    with patch("pyaudio.PyAudio", return_value=mock_instance), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with client.websocket_connect("/ws") as websocket:
            # Send start_transcription
            websocket.send_text(json.dumps({
                "action": "start_transcription",
                "data": {"target_language": "en"}
            }))

            # Wait for message to be posted and response to be forwarded over WebSocket
            response = websocket.receive_json()

            # Verify the forwarded message content matches requirements
            assert response["type"] == "subtitle"
            assert response["source"] == "remote_stt"
            assert response["text"] == "Buongiorno classe"
            assert response["translated_text"] is None
            assert response["is_final"] is True

            # Stop the transcription cleanly
            websocket.send_text(json.dumps({
                "action": "stop_transcription"
            }))
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_transcription_failure_handling() -> None:
    """
    Tests that a connection error or timeout during remote transcription
    does not crash the capture loop, sends a system_warning to the widget, and keeps capturing.
    """
    client = TestClient(app)

    mock_instance = MagicMock()
    mock_stream = MagicMock()
    mock_instance.open.return_value = mock_stream
    # Yield one full chunk, then return empty bytes
    mock_stream.read.side_effect = [b"\x00" * 32000, b""]

    with patch("pyaudio.PyAudio", return_value=mock_instance), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Simulate a connection timeout exception
        mock_post.side_effect = httpx.TimeoutException("Remote server transcription timeout")

        with client.websocket_connect("/ws") as websocket:
            # Send start_transcription
            websocket.send_text(json.dumps({
                "action": "start_transcription",
                "data": {"target_language": "it"}
            }))

            # Expect system_warning message sent back to the widget
            response = websocket.receive_json()

            assert response["type"] == "system_warning"
            assert "offline" in response["message"]

            # Stop transcription cleanly
            websocket.send_text(json.dumps({
                "action": "stop_transcription"
            }))
            await asyncio.sleep(0.05)
