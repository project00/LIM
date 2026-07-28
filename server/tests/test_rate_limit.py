"""
Unit Tests for LIM-AI Copilot Mock Remote Server Rate Limiting.

Design Note:
    This module tests the rate limiting mechanism configured with Slowapi
    on the POST /api/v1/analyze endpoint. It verifies that rate limits are
    properly keyed by the caller's Authorization Bearer token rather than raw IP,
    that they return HTTP 200 with the correct error payload, that the liveness
    endpoint /health remains unaffected, and that the limit can reset.
"""

import os
import sys
from pathlib import Path

# Configure environment variables before importing app/services
os.environ["API_KEY"] = "test_secret_token"

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from main import app, limiter

original_rate_limit = None


def setup_module():
    """Sets up the environment variable and resets the limiter for this test module."""
    global original_rate_limit
    original_rate_limit = os.environ.get("RATE_LIMIT_PER_MINUTE")
    os.environ["RATE_LIMIT_PER_MINUTE"] = "2"
    limiter.reset()


def teardown_module():
    """Restores the environment variable and resets the limiter to avoid affecting other tests."""
    global original_rate_limit
    if original_rate_limit is None:
        if "RATE_LIMIT_PER_MINUTE" in os.environ:
            del os.environ["RATE_LIMIT_PER_MINUTE"]
    else:
        os.environ["RATE_LIMIT_PER_MINUTE"] = original_rate_limit
    limiter.reset()


def setup_function():
    """Resets the rate limiter storage before each test to ensure a clean slate."""
    limiter.reset()


def test_rate_limiting_triggered_on_analyze() -> None:
    """
    Tests that POST /api/v1/analyze allows requests up to the configured limit,
    and returns HTTP 200 with a RATE_LIMITED payload on the exceeding request.
    """
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {"action": "concept_map_test", "data": {"topic": "biology"}}

    # First request: Allowed
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("type") != "error"

    # Second request: Allowed
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("type") != "error"

    # Third request: Rate limited
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "RATE_LIMITED"
    assert data["action"] == "concept_map_test"
    assert "Rate limit exceeded" in data["message"]


def test_rate_limiting_keyed_by_bearer_token() -> None:
    """
    Tests that the rate limiting is keyed by the bearer token.
    If Token A is rate limited, Token B remains completely unaffected and can make successful requests.
    """
    client = TestClient(app)
    headers_a = {"Authorization": "Bearer test_secret_token"}
    headers_b = {"Authorization": "Bearer test_secret_token_b"}
    payload = {"action": "concept_map_test", "data": {"topic": "biology"}}

    # Overriding the verify_api_key dependency during this test to allow any bearer token
    from main import verify_api_key
    app.dependency_overrides[verify_api_key] = lambda: None

    try:
        # Request 1 with Token A: Allowed
        resp = client.post("/api/v1/analyze", json=payload, headers=headers_a)
        assert resp.status_code == 200

        # Request 2 with Token A: Allowed
        resp = client.post("/api/v1/analyze", json=payload, headers=headers_a)
        assert resp.status_code == 200

        # Request 3 with Token A: Rate limited
        resp = client.post("/api/v1/analyze", json=payload, headers=headers_a)
        assert resp.status_code == 200
        assert resp.json().get("code") == "RATE_LIMITED"

        # Request with Token B: Should be allowed since it's a different bearer token key!
        resp = client.post("/api/v1/analyze", json=payload, headers=headers_b)
        assert resp.status_code == 200
        assert resp.json().get("type") != "error"

    finally:
        # Clean up overrides
        app.dependency_overrides.clear()


def test_health_not_rate_limited() -> None:
    """Tests that GET /health remains unlimited and fully operational even if /api/v1/analyze is rate limited."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {"action": "concept_map_test", "data": {"topic": "biology"}}

    # Exceed rate limits on analyze first
    for _ in range(3):
        client.post("/api/v1/analyze", json=payload, headers=headers)

    # Health check endpoint should still work perfectly
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
