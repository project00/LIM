"""
Unit and Integration Tests for Sketchfab OAuth2 Integration (Fase 6A).

Design Note:
    These tests validate the server-side OAuth2 flow: login redirection, CSRF
    state parameters, code exchange, profile retrieval, session creation, status,
    and logout endpoints. External API endpoints of Sketchfab are mocked using
    unittest.mock patches.
"""

import sys
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, OAUTH_STATES, SESSIONS


@pytest.fixture(autouse=True)
def clean_oauth_state() -> None:
    """Ensures test runs start with fresh, clean state and session storages."""
    OAUTH_STATES.clear()
    SESSIONS.clear()
    # Mock environment variables
    os.environ["SKETCHFAB_CLIENT_ID"] = "mock_client_id"
    os.environ["SKETCHFAB_CLIENT_SECRET"] = "mock_client_secret"
    os.environ["SKETCHFAB_REDIRECT_URI"] = (
        "http://127.0.0.1:8000/api/v1/sketchfab/callback"
    )
    yield
    OAUTH_STATES.clear()
    SESSIONS.clear()


# 1. Login redirection tests
def test_sketchfab_login_success() -> None:
    """Tests GET /api/v1/sketchfab/login redirects to Sketchfab with generated state."""
    client = TestClient(app)
    resp = client.get(
        "/api/v1/sketchfab/login?session_id=test_session_123", allow_redirects=False
    )

    assert resp.status_code == 307
    location = resp.headers["Location"]
    assert "https://sketchfab.com/oauth2/authorize/" in location
    assert "client_id=mock_client_id" in location
    assert "redirect_uri=http://127.0.0.1:8000/api/v1/sketchfab/callback" in location
    assert "state=" in location

    # Verify state was recorded in OAUTH_STATES
    assert len(OAUTH_STATES) == 1
    state_val = list(OAUTH_STATES.keys())[0]
    assert OAUTH_STATES[state_val]["session_id"] == "test_session_123"


def test_sketchfab_login_missing_session_id() -> None:
    """Tests GET /api/v1/sketchfab/login returns 400 when session_id is missing."""
    client = TestClient(app)
    resp = client.get("/api/v1/sketchfab/login?session_id=", allow_redirects=False)
    assert resp.status_code == 400
    assert "Missing required 'session_id' parameter" in resp.json()["detail"]


def test_sketchfab_login_missing_env_vars() -> None:
    """Tests GET /api/v1/sketchfab/login returns 500 when environment variables are unset."""
    # Temporarily remove env vars
    del os.environ["SKETCHFAB_CLIENT_ID"]
    client = TestClient(app)
    resp = client.get(
        "/api/v1/sketchfab/login?session_id=test_session_123", allow_redirects=False
    )
    assert resp.status_code == 500
    assert "Sketchfab OAuth is not configured on this server." in resp.json()["detail"]


# 2. Callback validation and exchange tests
@patch("httpx.AsyncClient.post")
@patch("httpx.AsyncClient.get")
def test_sketchfab_callback_success(mock_get: MagicMock, mock_post: MagicMock) -> None:
    """Tests GET /api/v1/sketchfab/callback processes auth code, retrieves user, and builds session."""
    # Pre-populate OAUTH_STATES with a valid state
    state = "secure_state_val"
    OAUTH_STATES[state] = {"session_id": "test_session_abc", "created_at": time.time()}

    # Mock token exchange response (httpx.AsyncClient.post)
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "oauth_user_access_token_789",
        "refresh_token": "oauth_user_refresh_token_789",
        "expires_in": 3600,
    }
    mock_post.return_value = mock_token_resp

    # Mock profile response (httpx.AsyncClient.get)
    mock_profile_resp = MagicMock()
    mock_profile_resp.status_code = 200
    mock_profile_resp.json.return_value = {
        "username": "professore_lim",
        "displayName": "Prof. LIM",
    }
    mock_get.return_value = mock_profile_resp

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/sketchfab/callback?code=mock_auth_code_123&state={state}"
    )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["Content-Type"]
    assert "Autenticazione Completata!" in resp.text
    assert "Prof. LIM" in resp.text

    # Assert state was popped (replay prevention)
    assert state not in OAUTH_STATES

    # Assert SESSIONS is properly populated
    assert "test_session_abc" in SESSIONS
    session = SESSIONS["test_session_abc"]
    assert session["username"] == "professore_lim"
    assert session["displayName"] == "Prof. LIM"
    assert session["access_token"] == "oauth_user_access_token_789"
    assert session["refresh_token"] == "oauth_user_refresh_token_789"


def test_sketchfab_callback_missing_params() -> None:
    """Tests callback returns 400 on missing code or state."""
    client = TestClient(app)
    resp = client.get("/api/v1/sketchfab/callback?code=123")
    assert resp.status_code == 400


def test_sketchfab_callback_invalid_state() -> None:
    """Tests callback returns 400 on unrecognized state."""
    client = TestClient(app)
    resp = client.get("/api/v1/sketchfab/callback?code=123&state=not_existing_state")
    assert resp.status_code == 400
    assert "Invalid or unrecognized state parameter." in resp.json()["detail"]


def test_sketchfab_callback_expired_state() -> None:
    """Tests callback returns 400 when state timestamp exceeds 10 minutes (expired)."""
    state = "expired_state_val"
    OAUTH_STATES[state] = {
        "session_id": "test_session_abc",
        "created_at": time.time() - 601.0,  # 10 minutes and 1 second ago
    }
    client = TestClient(app)
    resp = client.get(f"/api/v1/sketchfab/callback?code=123&state={state}")
    assert resp.status_code == 400
    assert "State parameter expired." in resp.json()["detail"]


# 3. Status and Logout endpoints tests
def test_sketchfab_status_unauthenticated() -> None:
    """Tests status endpoint returns authenticated=False if session does not exist."""
    client = TestClient(app)
    resp = client.get(
        "/api/v1/sketchfab/status", headers={"X-Sketchfab-Session-Id": "no_session"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}


def test_sketchfab_status_authenticated() -> None:
    """Tests status endpoint returns username and displayName if session exists and is active."""
    SESSIONS["session_active"] = {
        "username": "g_galilei",
        "displayName": "Galileo Galilei",
        "access_token": "some_secret_token",
        "refresh_token": "some_refresh_token",
        "expires_at": time.time() + 1000.0,
    }
    client = TestClient(app)
    resp = client.get(
        "/api/v1/sketchfab/status", headers={"X-Sketchfab-Session-Id": "session_active"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["username"] == "g_galilei"
    assert data["displayName"] == "Galileo Galilei"
    # Ensure tokens are never exposed in payload response
    assert "access_token" not in data
    assert "refresh_token" not in data


def test_sketchfab_status_expired() -> None:
    """Tests status endpoint invalidates and removes session if it is expired."""
    SESSIONS["session_expired"] = {
        "username": "expired_user",
        "displayName": "Expired User",
        "access_token": "some_token",
        "expires_at": time.time() - 1.0,  # Expired 1 second ago
    }
    client = TestClient(app)
    resp = client.get(
        "/api/v1/sketchfab/status",
        headers={"X-Sketchfab-Session-Id": "session_expired"},
    )
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is False
    assert "session_expired" not in SESSIONS


def test_sketchfab_logout() -> None:
    """Tests POST logout destroys the session from server storage."""
    SESSIONS["session_active"] = {
        "username": "g_galilei",
        "access_token": "some_token",
        "expires_at": time.time() + 1000.0,
    }
    client = TestClient(app)
    resp = client.post(
        "/api/v1/sketchfab/logout", headers={"X-Sketchfab-Session-Id": "session_active"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "logged_out"}
    assert "session_active" not in SESSIONS
