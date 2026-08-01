import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from services.summary_service import generate_summary
from services.graph_service import generate_concept_map
from services.quiz_service import generate_quiz
from services.translate_service import translate_text

client = TestClient(app)

@patch("litellm.completion")
def test_generate_summary_uses_passed_credentials(mock_completion: MagicMock):
    # Mock Litellm completion
    mock_choice = MagicMock()
    mock_choice.message.content = "Summary using custom creds"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    lesson_log = [{"type": "subtitle", "content": "Hello", "timestamp": "2026"}]
    custom_credentials = {
        "llm": {
            "type": "llm_cloud",
            "model": "gpt-custom-model",
            "api_key": "my-custom-api-key",
            "api_base": "https://custom.api.base"
        }
    }

    # Call summary service with custom credentials
    summary = generate_summary(lesson_log, credentials=custom_credentials)
    assert summary == "Summary using custom creds"

    mock_completion.assert_called_once()
    called_kwargs = mock_completion.call_args.kwargs
    assert called_kwargs["model"] == "gpt-custom-model"
    assert called_kwargs["api_key"] == "my-custom-api-key"
    assert called_kwargs["api_base"] == "https://custom.api.base"


@patch("litellm.completion")
def test_generate_quiz_uses_passed_credentials(mock_completion: MagicMock):
    # Mock Litellm completion returning a valid quiz JSON array with 3 questions
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '['
        '  {"question": "Q1", "options": ["A", "B"], "correct_index": 0},'
        '  {"question": "Q2", "options": ["C", "D"], "correct_index": 1},'
        '  {"question": "Q3", "options": ["E", "F"], "correct_index": 0}'
        ']'
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    custom_credentials = {
        "llm": {
            "type": "llm_ollama",
            "model": "ollama/llama-custom",
            "api_key": "",
            "api_base": "http://localhost:9999"
        }
    }

    quiz = generate_quiz("lesson context", num_questions=3, credentials=custom_credentials)
    assert len(quiz) == 3
    assert quiz[0]["question"] == "Q1"

    mock_completion.assert_called_once()
    called_kwargs = mock_completion.call_args.kwargs
    assert called_kwargs["model"] == "ollama/llama-custom"
    assert "api_key" not in called_kwargs
    assert called_kwargs["api_base"] == "http://localhost:9999"


@patch("litellm.completion")
def test_api_concept_map_uses_passed_credentials(mock_completion: MagicMock):
    # Mock Litellm completion returning simple Mermaid
    mock_choice = MagicMock()
    mock_choice.message.content = "graph TD; A-->B"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    payload = {
        "action": "concept_map",
        "data": {
            "topic": "cioccolato",
            "language": "it"
        },
        "credentials": {
            "llm": {
                "type": "llm_cloud",
                "model": "gpt-4o-new",
                "api_key": "api-key-test"
            }
        }
    }

    headers = {"Authorization": "Bearer test_secret_token"}
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["type"] == "concept_map"
    assert resp.json()["mermaid_code"] == "graph TD; A-->B"

    mock_completion.assert_called_once()
    called_kwargs = mock_completion.call_args.kwargs
    assert called_kwargs["model"] == "gpt-4o-new"
    assert called_kwargs["api_key"] == "api-key-test"
