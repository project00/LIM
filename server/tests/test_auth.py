"""
Unit Tests for LIM-AI Copilot Mock Remote Server Authentication.

Design Note:
    This module tests the Bearer token authentication mechanism on the POST /api/v1/analyze
    endpoint. It establishes a test environment with a mock API_KEY and uses FastAPI's TestClient
    to verify:
    - GET /health is fully public/unauthenticated.
    - POST /api/v1/analyze returns 401 if the Authorization header is missing.
    - POST /api/v1/analyze returns 401 if the Bearer token is incorrect.
    - POST /api/v1/analyze succeeds and passes through when a valid Bearer token is provided.
"""

import os
import pytest
from fastapi.testclient import TestClient

# Mock environment variable for the server's API_KEY before importing app
os.environ["API_KEY"] = "test_secret_token"

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app


def test_health_is_public_unauthenticated() -> None:
    """Tests that the liveness check health endpoint does not require authentication."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_unauthorized_when_header_missing() -> None:
    """Tests that POST /api/v1/analyze fails with 401 when Authorization header is absent."""
    client = TestClient(app)
    payload = {"action": "concept_map", "data": {"topic": "biology"}}
    resp = client.post("/api/v1/analyze", json=payload)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or missing API key"}


def test_analyze_unauthorized_when_token_incorrect() -> None:
    """Tests that POST /api/v1/analyze fails with 401 when the Bearer token doesn't match."""
    client = TestClient(app)
    payload = {"action": "concept_map", "data": {"topic": "biology"}}
    headers = {"Authorization": "Bearer incorrect_token"}
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or missing API key"}


def test_analyze_authorized_when_token_matches() -> None:
    """Tests that POST /api/v1/analyze succeeds and returns correctly when token is valid."""
    client = TestClient(app)
    payload = {"action": "concept_map", "data": {"topic": "biology"}}
    headers = {"Authorization": "Bearer test_secret_token"}
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["source"] == "mock_server"
    assert resp.json()["action"] == "concept_map"
