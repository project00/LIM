"""
Unit Tests for LIM-AI Copilot Mock Remote Server Authentication and Services.

Design Note:
    This module tests the Bearer token authentication mechanism on the POST /api/v1/analyze
    endpoint, and mocks LiteLLM to verify the prompt composition and responses for real
    concept_map actions.
"""

import os
import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

# Mock environment variables for the server's configuration before importing app/services
os.environ["API_KEY"] = "test_secret_token"
os.environ["LLM_MODEL"] = "gpt-4o-mini"
os.environ["LLM_API_KEY"] = "test_provider_key"

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


def test_analyze_authorized_when_token_matches_mock_action() -> None:
    """Tests that POST /api/v1/analyze succeeds and returns mock echo when token is valid (for other actions)."""
    client = TestClient(app)
    payload = {"action": "load_3d_model", "data": {"query": "H2O"}}
    headers = {"Authorization": "Bearer test_secret_token"}
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["source"] == "mock_server"
    assert resp.json()["action"] == "load_3d_model"


@patch("litellm.completion")
def test_concept_map_generation_success(mock_completion: MagicMock) -> None:
    """
    Tests that POST /api/v1/analyze with a 'concept_map' action uses LiteLLM to generate
    a concept map, validates the inputs, strips markdown fences, and formats the output.
    """
    client = TestClient(app)

    # Configure the mock response
    mock_choice = MagicMock()
    mock_choice.message.content = "```mermaid\ngraph TD\n  A[Apparato] --> B[Cuore]\n```"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    payload = {
        "action": "concept_map",
        "data": {
            "topic": "apparato circolatorio",
            "language": "it"
        }
    }
    headers = {"Authorization": "Bearer test_secret_token"}

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "concept_map"
    assert data["source"] == "remote_llm"
    # Ensure the markdown code fences have been stripped properly
    assert data["mermaid_code"] == "graph TD\n  A[Apparato] --> B[Cuore]"

    # Verify the completion prompt was composed correctly
    mock_completion.assert_called_once()
    called_kwargs = mock_completion.call_args[1]
    assert called_kwargs["model"] == "gpt-4o-mini"
    assert called_kwargs["api_key"] == "test_provider_key"
    messages = called_kwargs["messages"]
    assert len(messages) == 1
    assert "apparato circolatorio" in messages[0]["content"]
    assert "it" in messages[0]["content"]
    assert "Mermaid" in messages[0]["content"]
