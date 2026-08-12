import pytest
from unittest.mock import MagicMock
import litellm
from services.mermaid_validator import validate_and_sanitize_mermaid, InvalidMermaidError
from services.graph_service import generate_concept_map

def test_mermaid_validation_markdown_fence():
    """Test that markdown-wrapped code blocks are correctly stripped and sanitized."""
    raw_markdown = (
        "Ecco la mappa concettuale:\n"
        "```mermaid\n"
        "graph TD\n"
        "    A[\"Inizio\"] --> B[\"Fine\"]\n"
        "```\n"
        "Spero sia utile."
    )
    sanitized = validate_and_sanitize_mermaid(raw_markdown)
    assert "graph TD" in sanitized
    assert "A[\"Inizio\"]" in sanitized
    assert "B[\"Fine\"]" in sanitized
    assert "```" not in sanitized
    assert "Ecco la mappa" not in sanitized

def test_mermaid_validation_raw_text():
    """Test that raw text inputs starting directly with valid keywords are untouched."""
    raw_text = (
        "flowchart TD\n"
        "    A[\"Nodo 1\"] --> B[\"Nodo 2\"]\n"
        "    B --> C[\"Nodo 3\"]"
    )
    sanitized = validate_and_sanitize_mermaid(raw_text)
    assert sanitized == raw_text

def test_mermaid_validation_raw_text_with_intro():
    """Test raw text output with conversational text before keyword is handled correctly."""
    raw_with_intro = (
        "Sicuramente! Ecco il codice della mappa concettuale:\n"
        "graph TD\n"
        "A[\"Acqua\"] --> B[\"Idrogeno\"]"
    )
    sanitized = validate_and_sanitize_mermaid(raw_with_intro)
    assert sanitized.startswith("graph TD")
    assert "Acqua" in sanitized

def test_mermaid_validation_invalid_keyword():
    """Test that invalid start keywords trigger InvalidMermaidError."""
    bad_code = "not_a_keyword TD\nA --> B"
    with pytest.raises(InvalidMermaidError) as exc:
        validate_and_sanitize_mermaid(bad_code)
    assert "non inizia con una parola chiave valida" in str(exc.value)

def test_mermaid_validation_empty_content():
    """Test empty input handling."""
    with pytest.raises(InvalidMermaidError) as exc:
        validate_and_sanitize_mermaid("   ")
    assert "vuoto" in str(exc.value)

def test_generate_concept_map_success(monkeypatch):
    """
    Test that generate_concept_map utilizes the system prompt
    and successfully generates the map without throwing "contenuto vuoto" errors.
    """
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "```mermaid\ngraph TD\n    A[\"Acqua\"] --> B[\"Idrogeno\"]\n```"
    mock_response.choices = [mock_choice]

    captured_args = {}

    def mock_completion(**kwargs):
        captured_args.update(kwargs)
        return mock_response

    monkeypatch.setattr(litellm, "completion", mock_completion)

    result = generate_concept_map(
        topic="acqua",
        language="it",
        llm_model="qwen-4b",
        llm_api_key="mock-key",
        llm_api_base="http://localhost:11434"
    )

    # Verify return value is clean Mermaid syntax
    assert result.startswith("graph TD")
    assert "Acqua" in result
    assert "Idrogeno" in result

    # Check that system and user prompts are passed correctly
    messages = captured_args.get("messages")
    assert messages is not None
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Sei un generatore di codice Mermaid.js." in messages[0]["content"]
    assert "graph TD" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Topic: acqua" in messages[1]["content"]
