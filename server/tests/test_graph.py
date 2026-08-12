import pytest
import re
from unittest.mock import MagicMock
import litellm
from services.mermaid_validator import validate_and_sanitize_mermaid, InvalidMermaidError
from services.graph_service import generate_concept_map, FALLBACK_MERMAID_DIAGRAM

def test_mermaid_validation_markdown_fence():
    """Caso 1: Codice racchiuso in ```mermaid graph TD ... ```."""
    raw_markdown = (
        "Ecco la mappa concettuale:\n"
        "```mermaid\n"
        "graph TD\n"
        "    A[\"Inizio\"] --> B[\"Fine\"]\n"
        "```\n"
        "Spero sia utile."
    )
    sanitized = validate_and_sanitize_mermaid(raw_markdown)
    assert sanitized.startswith("graph TD")
    assert "A[\"Inizio\"]" in sanitized
    assert "B[\"Fine\"]" in sanitized
    assert "```" not in sanitized
    assert "Ecco la mappa" not in sanitized

def test_mermaid_validation_raw_text_with_intro():
    """Caso 2: Testo grezzo con introduzione conversazionale e codice senza backtick."""
    raw_with_intro = (
        "Sicuramente! Ecco il codice della mappa concettuale senza markdown blocks:\n"
        "graph TD\n"
        "A[\"Acqua\"] --> B[\"Idrogeno\"]\n"
        "Spero che questo ti aiuti!"
    )
    sanitized = validate_and_sanitize_mermaid(raw_with_intro)
    assert sanitized.startswith("graph TD")
    assert "Acqua" in sanitized
    assert "Idrogeno" in sanitized
    assert "Sicuramente!" not in sanitized
    assert "Spero che questo ti aiuti!" not in sanitized

def test_mermaid_validation_corrupted_repairable():
    """Caso 3: Sintassi corrotta ma riparabile: frecce ->, assenza di graph TD, e classi non definite :::root_part."""
    corrupted_code = (
        "A[Testo Nodo] -> B[Secondo Nodo]:::root_part"
    )
    sanitized = validate_and_sanitize_mermaid(corrupted_code)
    # L'intestazione graph TD deve essere iniettata perché mancante
    assert sanitized.startswith("graph TD")
    # Il connettore -> deve essere normalizzato in -->
    assert "-->" in sanitized
    # Verifica che non ci siano frecce a puntatore singolo "->" spuri (escluse quelle all'interno di "-->")
    assert re.search(r"(?<![-.=])->(?![->])", sanitized) is None
    # La classe CSS non definita :::root_part deve essere rimossa
    assert ":::root_part" not in sanitized
    # Il testo dei nodi contenente spazi deve essere racchiuso tra virgolette doppie
    assert 'A["Testo Nodo"]' in sanitized
    assert 'B["Secondo Nodo"]' in sanitized

def test_mermaid_validation_totally_invalid():
    """Caso 4: Input totalmente invalido -> verifica che scatti il diagramma di fallback anziché l'errore o il crash."""
    # Testiamo validate_and_sanitize_mermaid che solleva InvalidMermaidError per input vuoto o non interpretabile
    with pytest.raises(InvalidMermaidError):
        validate_and_sanitize_mermaid("Questo è solo un testo conversazionale senza alcuna mappa concettuale.")

def test_generate_concept_map_fallback_on_invalid_output(monkeypatch):
    """Verifica che generate_concept_map restituisca il diagramma di fallback pulito se l'output dell'LLM è invalido."""
    from services.graph_service import INVALID_MERMAID_FALLBACK
    mock_response = MagicMock()
    mock_choice = MagicMock()
    # Output completamente non interpretabile che non contiene relazioni o parole chiave
    mock_choice.message.content = "Questo è solo del testo conversazionale che fallirà la validazione strutturale."
    mock_response.choices = [mock_choice]

    monkeypatch.setattr(litellm, "completion", lambda **kwargs: mock_response)

    result = generate_concept_map(
        topic="argomento_invalido",
        language="it",
        llm_model="qwen-4b",
        llm_api_key="mock-key",
        llm_api_base="http://localhost:11434"
    )

    # Dovrebbe restituire il diagramma di fallback per errore di validazione
    assert result == INVALID_MERMAID_FALLBACK
    assert "Impossibile generare la mappa concettuale" in result

def test_generate_concept_map_fallback_invalid_mermaid_error(monkeypatch):
    """Verifica che generate_concept_map intercetti InvalidMermaidError e restituisca INVALID_MERMAID_FALLBACK."""
    from services.graph_service import INVALID_MERMAID_FALLBACK
    mock_response = MagicMock()
    mock_choice = MagicMock()
    # Questo testo scatenerà esplicitamente un InvalidMermaidError (vuoto o non conforme)
    mock_choice.message.content = ""
    mock_response.choices = [mock_choice]

    monkeypatch.setattr(litellm, "completion", lambda **kwargs: mock_response)

    result = generate_concept_map(
        topic="argomento_vuoto",
        language="it",
        llm_model="qwen-4b",
        llm_api_key="mock-key",
        llm_api_base="http://localhost:11434"
    )

    assert result == INVALID_MERMAID_FALLBACK
    assert "Impossibile generare la mappa concettuale" in result

def test_generate_concept_map_alternative_content_extraction(monkeypatch):
    """Verifica che generate_concept_map estragga il contenuto da campi alternativi come reasoning_content o text."""
    # Scenario A: reasoning_content popolato su messaggio
    mock_response = MagicMock()
    mock_choice = MagicMock()
    del mock_choice.message.content
    mock_choice.message.reasoning_content = "graph TD\n    A[\"Reasoning\"] --> B[\"Done\"]"
    mock_choice.message.text = None
    mock_response.choices = [mock_choice]

    monkeypatch.setattr(litellm, "completion", lambda **kwargs: mock_response)

    result = generate_concept_map(
        topic="test",
        language="it",
        llm_model="qwen-4b",
        llm_api_key="mock-key",
        llm_api_base="http://localhost:11434"
    )
    assert "Reasoning" in result

    # Scenario B: text popolato su scelta (choice)
    mock_response_b = MagicMock()
    mock_choice_b = MagicMock()
    del mock_choice_b.message
    mock_choice_b.text = "graph TD\n    A[\"TextOnChoice\"] --> B[\"Done\"]"
    mock_response_b.choices = [mock_choice_b]

    monkeypatch.setattr(litellm, "completion", lambda **kwargs: mock_response_b)

    result_b = generate_concept_map(
        topic="test",
        language="it",
        llm_model="qwen-4b",
        llm_api_key="mock-key",
        llm_api_base="http://localhost:11434"
    )
    assert "TextOnChoice" in result_b

def test_generate_concept_map_success(monkeypatch):
    """Test standard di successo del servizio di generazione della mappa concettuale."""
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

    # Verifica che ritorni il codice Mermaid pulito e ben strutturato
    assert result.startswith("graph TD")
    assert "Acqua" in result
    assert "Idrogeno" in result

    # Controlla la correttezza del system prompt passato a LiteLLM
    messages = captured_args.get("messages")
    assert messages is not None
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Sei un generatore di codice Mermaid.js." in messages[0]["content"]
    assert "graph TD" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Topic: acqua" in messages[1]["content"]

def test_generate_concept_map_litellm_optimization_and_cleaning(monkeypatch):
    """Verifica che i parametri LiteLLM siano ottimizzati e che l'output venga ripulito da <think> e delimitatori markdown."""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    # Output contenente tag <think> (CoT internal) e delimitatori markdown
    mock_choice.message.content = (
        "<think>Ragionamento del modello Ollama/Qwen...\n"
        "Voglio proporre un diagramma semplice.</think>\n"
        "```mermaid\n"
        "graph TD\n"
        "    A[\"Inizio\"] --> B[\"Fine\"]\n"
        "```"
    )
    mock_response.choices = [mock_choice]

    captured_args = {}

    def mock_completion(**kwargs):
        captured_args.update(kwargs)
        return mock_response

    monkeypatch.setattr(litellm, "completion", mock_completion)

    result = generate_concept_map(
        topic="ottimizzazione",
        language="it",
        llm_model="qwen-4b",
        llm_api_key="mock-key",
        llm_api_base="http://localhost:11434"
    )

    # 1. Verifica i parametri di completamento LiteLLM
    assert captured_args.get("temperature") == 0.0
    assert captured_args.get("extra_body") == {
        "options": {
            "num_ctx": 8192,
            "temperature": 0.0
        }
    }

    # 2. Verifica che i tag <think> e i backtick siano stati rimossi prima della validazione
    assert result.startswith("graph TD")
    assert "Ragionamento del modello" not in result
    assert "<think>" not in result
    assert "```" not in result

    # 3. Verifica le nuove istruzioni nel system prompt
    messages = captured_args.get("messages")
    assert messages is not None
    system_prompt = messages[0]["content"]
    assert "tag <think>" in system_prompt
    assert "Chain of Thought" in system_prompt or "CoT" in system_prompt
    assert "TASSATIVAMENTE" in system_prompt
