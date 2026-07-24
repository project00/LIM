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

import json
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

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


def test_fast_ocr_local_route_not_implemented() -> None:
    """Tests fast_ocr local route fallback yielding NOT_IMPLEMENTED error."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"action": "fast_ocr"}))
        response = websocket.receive_json()
        assert response["type"] == "error"
        assert response["code"] == "NOT_IMPLEMENTED"
        assert response["action"] == "fast_ocr"
        assert "non ancora disponibile" in response["message"]


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
