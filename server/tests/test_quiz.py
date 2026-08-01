"""
Unit and Integration Tests for Quiz Generation and Validation Service.

Design Note:
    This module tests the generation, structural validation, and API integration
    of the remote server's quiz feature. It mocks LiteLLM completion calls to isolate
    the tests and assert correct validation/error-handling behaviors.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.quiz_validator import validate_and_parse_quiz, InvalidQuizError
from services.quiz_service import generate_quiz
from main import app


# ------------------ 1. Unit Tests for Validator ------------------

def test_validator_success_clean_json() -> None:
    """Tests that a properly-formed quiz JSON is validated and parsed correctly."""
    raw_output = """
    [
        {"question": "What is 2+2?", "options": ["3", "4", "5"], "correct_index": 1},
        {"question": "What is the capital of Italy?", "options": ["Rome", "Milan", "Venice"], "correct_index": 0},
        {"question": "What is the capital of France?", "options": ["Paris", "Lyon"], "correct_index": 0}
    ]
    """
    data = validate_and_parse_quiz(raw_output)
    assert len(data) == 3
    assert data[0]["question"] == "What is 2+2?"
    assert data[1]["options"] == ["Rome", "Milan", "Venice"]
    assert data[2]["correct_index"] == 0


def test_validator_code_blocks_stripped() -> None:
    """Tests that validator successfully strips markdown backticks and json code blocks."""
    raw_output = """```json
    [
        {"question": "Q1", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2", "options": ["A", "B"], "correct_index": 1},
        {"question": "Q3", "options": ["A", "B"], "correct_index": 0}
    ]
    ```"""
    data = validate_and_parse_quiz(raw_output)
    assert len(data) == 3


def test_validator_reject_non_json() -> None:
    """Tests that malformed or non-JSON output is rejected."""
    with pytest.raises(InvalidQuizError, match="Formato JSON non valido"):
        validate_and_parse_quiz("not-a-json-string")


def test_validator_reject_non_list() -> None:
    """Tests that JSON objects (instead of lists) are rejected."""
    raw_output = '{"error": "not a list"}'
    with pytest.raises(InvalidQuizError, match="L'output non è una lista JSON"):
        validate_and_parse_quiz(raw_output)


def test_validator_reject_too_few_questions() -> None:
    """Tests that a quiz with fewer than 3 questions is rejected."""
    raw_output = """
    [
        {"question": "Q1?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2?", "options": ["A", "B"], "correct_index": 1}
    ]
    """
    with pytest.raises(InvalidQuizError, match="Il numero di domande .* deve essere compreso tra 3 e 5"):
        validate_and_parse_quiz(raw_output)


def test_validator_reject_too_many_questions() -> None:
    """Tests that a quiz with more than 5 questions is rejected."""
    raw_output = """
    [
        {"question": "Q1?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2?", "options": ["A", "B"], "correct_index": 1},
        {"question": "Q3?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q4?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q5?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q6?", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    with pytest.raises(InvalidQuizError, match="Il numero di domande .* deve essere compreso tra 3 e 5"):
        validate_and_parse_quiz(raw_output)


def test_validator_reject_non_dict_question() -> None:
    """Tests that a question element that is not a dictionary is rejected."""
    raw_output = """
    [
        {"question": "Q1?", "options": ["A", "B"], "correct_index": 0},
        "not-a-dictionary",
        {"question": "Q3?", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    with pytest.raises(InvalidQuizError, match="non è un oggetto dizionario"):
        validate_and_parse_quiz(raw_output)


def test_validator_reject_empty_question_text() -> None:
    """Tests that a question with missing/empty text is rejected."""
    raw_output = """
    [
        {"question": "Q1?", "options": ["A", "B"], "correct_index": 0},
        {"question": "   ", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q3?", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    with pytest.raises(InvalidQuizError, match="ha un testo non valido o vuoto"):
        validate_and_parse_quiz(raw_output)


def test_validator_reject_insufficient_options() -> None:
    """Tests that a question with fewer than 2 options is rejected."""
    raw_output = """
    [
        {"question": "Q1?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2?", "options": ["A"], "correct_index": 0},
        {"question": "Q3?", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    with pytest.raises(InvalidQuizError, match="deve avere almeno 2 opzioni"):
        validate_and_parse_quiz(raw_output)


def test_validator_reject_out_of_bounds_index() -> None:
    """Tests that a correct_index value outside the options array bounds is rejected."""
    raw_output = """
    [
        {"question": "Q1?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2?", "options": ["A", "B"], "correct_index": 2},
        {"question": "Q3?", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    with pytest.raises(InvalidQuizError, match="è fuori dai limiti"):
        validate_and_parse_quiz(raw_output)


def test_validator_reject_boolean_index() -> None:
    """Tests that correct_index must be a real integer and not a boolean."""
    raw_output = """
    [
        {"question": "Q1?", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2?", "options": ["A", "B"], "correct_index": true},
        {"question": "Q3?", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    with pytest.raises(InvalidQuizError, match="deve essere un numero intero"):
        validate_and_parse_quiz(raw_output)


# ------------------ 2. Service and API Integration Tests ------------------

@patch("litellm.completion")
def test_generate_quiz_success(mock_completion: MagicMock) -> None:
    """Tests that generate_quiz service successfully parses a valid LLM response."""
    # Configure mock completion return value
    mock_choice = MagicMock()
    mock_choice.message.content = """
    [
        {"question": "Q1", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2", "options": ["A", "B"], "correct_index": 1},
        {"question": "Q3", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    quiz = generate_quiz("Test context about Python programming", 3, "gpt-4o", "test-key", None)
    assert len(quiz) == 3
    assert quiz[1]["question"] == "Q2"
    mock_completion.assert_called_once()
    called_kwargs = mock_completion.call_args.kwargs
    assert called_kwargs["model"] == "gpt-4o"
    assert called_kwargs["api_key"] == "test-key"


@patch("litellm.completion")
def test_api_generate_quiz_endpoint_success(mock_completion: MagicMock) -> None:
    """Tests endpoint POST /api/v1/analyze for generate_quiz returns success schema."""
    mock_choice = MagicMock()
    mock_choice.message.content = """
    [
        {"question": "Q1", "options": ["A", "B"], "correct_index": 0},
        {"question": "Q2", "options": ["A", "B"], "correct_index": 1},
        {"question": "Q3", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-LLM-Model": "gpt-4o"
    }
    payload = {
        "action": "generate_quiz",
        "data": {
            "lesson_context": "Introduction to photosynthesis.",
            "num_questions": 3
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "quiz"
    assert data["source"] == "remote_llm"
    assert len(data["questions"]) == 3
    assert data["questions"][0]["question"] == "Q1"


@patch("litellm.completion")
def test_api_generate_quiz_validation_failure(mock_completion: MagicMock) -> None:
    """Tests endpoint handles validation failure cleanly, returning INVALID_LLM_OUTPUT (HTTP 200)."""
    # LLM returns too few questions (less than 3)
    mock_choice = MagicMock()
    mock_choice.message.content = """
    [
        {"question": "Q1", "options": ["A", "B"], "correct_index": 0}
    ]
    """
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-LLM-Model": "gpt-4o"
    }
    payload = {
        "action": "generate_quiz",
        "data": {
            "lesson_context": "Short text.",
            "num_questions": 4
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "INVALID_LLM_OUTPUT"
    assert data["action"] == "generate_quiz"
    assert "compreso tra 3 e 5" in data["message"]


@patch("litellm.completion")
def test_api_generate_quiz_provider_error(mock_completion: MagicMock) -> None:
    """Tests endpoint handles LLM provider completion failure defensively, returning INVALID_LLM_OUTPUT (HTTP 200)."""
    # Simulate an error raised by litellm
    import litellm
    mock_completion.side_effect = litellm.exceptions.APIError(
        message="Simulated rate limit error",
        status_code=429,
        llm_provider="openai",
        model="gpt-4o-mini"
    )

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-LLM-Model": "gpt-4o"
    }
    payload = {
        "action": "generate_quiz",
        "data": {
            "lesson_context": "Photosynthesis.",
            "num_questions": 3
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "INVALID_LLM_OUTPUT"
    assert data["action"] == "generate_quiz"
    assert "Simulated rate limit error" in data["message"]
