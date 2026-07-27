"""
Unit and Integration Tests for Summary Generation and Integration Service.

Design Note:
    This module tests the generation, integration, and API endpoints of the
    remote server's summary feature. It mocks LiteLLM completion calls to isolate
    the tests and assert correct responses and error-handling behaviors.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.summary_service import generate_summary
from main import app


@patch("litellm.completion")
def test_generate_lesson_summary_success(mock_completion: MagicMock) -> None:
    """Tests that generate_summary service successfully queries LLM and returns summary text."""
    # Configure mock completion return value
    mock_choice = MagicMock()
    mock_choice.message.content = "Questo è il riassunto della lezione.\n\nContiene due paragrafi."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    lesson_log = [
        {"type": "subtitle", "content": "Benvenuti alla lezione di scienze.", "timestamp": "2026-07-23T10:00:00.000Z"},
        {"type": "math", "content": "Espressione: f(x) = x^2", "timestamp": "2026-07-23T10:01:00.000Z"}
    ]

    summary = generate_summary(lesson_log)
    assert summary == "Questo è il riassunto della lezione.\n\nContiene due paragrafi."
    mock_completion.assert_called_once()


@patch("litellm.completion")
def test_api_generate_summary_endpoint_success(mock_completion: MagicMock) -> None:
    """Tests that POST /api/v1/analyze for generate_summary action returns success schema."""
    mock_choice = MagicMock()
    mock_choice.message.content = "Riassunto di prova della lezione."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "generate_summary",
        "data": {
            "lesson_log": [
                {"type": "subtitle", "content": "Qualcosa", "timestamp": "2026-07-23T10:00:00Z"}
            ]
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "summary"
    assert data["source"] == "remote_llm"
    assert data["summary"] == "Riassunto di prova della lezione."


def test_api_generate_summary_empty_log() -> None:
    """Tests endpoint handles empty lesson log defensively, returning EMPTY_LESSON_LOG."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "generate_summary",
        "data": {
            "lesson_log": []
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "EMPTY_LESSON_LOG"
    assert data["action"] == "generate_summary"
    assert data["message"] == "Nessun contenuto da riassumere ancora"


@patch("litellm.completion")
def test_api_generate_summary_provider_error(mock_completion: MagicMock) -> None:
    """Tests endpoint handles LLM provider completion failure defensively, returning INVALID_LLM_OUTPUT (HTTP 200)."""
    import litellm
    mock_completion.side_effect = litellm.exceptions.APIError(
        message="Simulated connection timeout",
        status_code=504,
        llm_provider="openai",
        model="gpt-4o-mini"
    )

    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "generate_summary",
        "data": {
            "lesson_log": [
                {"type": "subtitle", "content": "Qualcosa", "timestamp": "2026-07-23T10:00:00Z"}
            ]
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "INVALID_LLM_OUTPUT"
    assert data["action"] == "generate_summary"
    assert "Simulated connection timeout" in data["message"]
