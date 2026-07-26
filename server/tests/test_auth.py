"""
Unit Tests for LIM-AI Copilot Mock Remote Server Authentication, Services and Validation.

Design Note:
    This module tests the Bearer token authentication mechanism on the POST /api/v1/analyze
    endpoint, mocks LiteLLM to verify the prompt composition, and tests strict Mermaid.js
    validation and sanitization rules (fences, starts, empty, and XSS prevention).
"""

import os
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
from services.mermaid_validator import validate_and_sanitize_mermaid, InvalidMermaidError


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


def test_mermaid_validator_valid_passes() -> None:
    """Confirm valid Mermaid passes through unchanged."""
    valid_graph = "graph TD\n  A --> B"
    valid_mindmap = "mindmap\n  root\n    node1"
    valid_flowchart = "flowchart LR\n  X --> Y"

    assert validate_and_sanitize_mermaid(valid_graph) == valid_graph
    assert validate_and_sanitize_mermaid(valid_mindmap) == valid_mindmap
    assert validate_and_sanitize_mermaid(valid_flowchart) == valid_flowchart


def test_mermaid_validator_fenced_unfenced() -> None:
    """Confirm fenced Mermaid gets unfenced correctly."""
    fenced_1 = "```mermaid\ngraph TD\n  A --> B\n```"
    fenced_2 = "```\nflowchart LR\n  X --> Y\n```"

    assert validate_and_sanitize_mermaid(fenced_1) == "graph TD\n  A --> B"
    assert validate_and_sanitize_mermaid(fenced_2) == "flowchart LR\n  X --> Y"


def test_mermaid_validator_empty_rejected() -> None:
    """Confirm empty or whitespace-only output is rejected."""
    with pytest.raises(InvalidMermaidError, match="vuoto"):
        validate_and_sanitize_mermaid("")

    with pytest.raises(InvalidMermaidError, match="vuoto"):
        validate_and_sanitize_mermaid("   \n  \t ")


def test_mermaid_validator_invalid_keyword_rejected() -> None:
    """Confirm output not starting with flowchart/graph/mindmap is rejected."""
    invalid_mermaid = "Mind map on chemistry:\nThis mindmap starts differently."
    with pytest.raises(InvalidMermaidError, match="non inizia con una parola chiave valida"):
        validate_and_sanitize_mermaid(invalid_mermaid)


def test_mermaid_validator_xss_rejected() -> None:
    """Confirm output containing script or other XSS tags is strictly rejected."""
    xss_script = "graph TD\n  A[node] --> B[<script>alert(1)</script>]"
    xss_img = "flowchart LR\n  A[node] --> B[<img src=x onerror=alert(1)>]"
    xss_iframe = "mindmap\n  root\n    <iframe src='javascript:alert(1)'></iframe>"
    xss_javascript = "graph TD\n  A[node] --> B[javascript:alert(1)]"

    for xss_input in (xss_script, xss_img, xss_iframe, xss_javascript):
        with pytest.raises(InvalidMermaidError, match="potenziale contenuto XSS non sicuro"):
            validate_and_sanitize_mermaid(xss_input)


@patch("litellm.completion")
def test_concept_map_invalid_mermaid_rejection(mock_completion: MagicMock) -> None:
    """
    Tests that POST /api/v1/analyze returns the correct error response structure
    when the LLM output fails validation (e.g. contains invalid starting keywords).
    """
    client = TestClient(app)

    # Configure the mock response with invalid output
    mock_choice = MagicMock()
    mock_choice.message.content = "Here is your diagram:\ngraph TD\n  A --> B"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    payload = {
        "action": "concept_map",
        "data": {
            "topic": "apparato circolatorio"
        }
    }
    headers = {"Authorization": "Bearer test_secret_token"}

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "INVALID_LLM_OUTPUT"
    assert data["action"] == "concept_map"
    assert "non inizia con una parola chiave valida" in data["message"]


@patch("litellm.completion")
def test_concept_map_xss_integration_rejection(mock_completion: MagicMock) -> None:
    """
    Tests that POST /api/v1/analyze returns the correct error response structure
    when the LLM output contains an XSS vector like <script> or iframe.
    """
    client = TestClient(app)

    # Configure the mock response with an XSS vector
    mock_choice = MagicMock()
    mock_choice.message.content = "graph TD\n  A[node] --> B[<script>alert('XSS')</script>]"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    payload = {
        "action": "concept_map",
        "data": {
            "topic": "apparato circolatorio"
        }
    }
    headers = {"Authorization": "Bearer test_secret_token"}

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "INVALID_LLM_OUTPUT"
    assert data["action"] == "concept_map"
    assert "potenziale contenuto XSS" in data["message"]


@patch("litellm.completion")
def test_concept_map_empty_integration_rejection(mock_completion: MagicMock) -> None:
    """
    Tests that POST /api/v1/analyze returns the correct error response structure
    when the LLM output is empty or contains only markdown fences without code.
    """
    client = TestClient(app)

    # Configure the mock response with empty output
    mock_choice = MagicMock()
    mock_choice.message.content = "```mermaid\n\n```"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    payload = {
        "action": "concept_map",
        "data": {
            "topic": "apparato circolatorio"
        }
    }
    headers = {"Authorization": "Bearer test_secret_token"}

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "INVALID_LLM_OUTPUT"
    assert data["action"] == "concept_map"
    assert "vuoto" in data["message"]
