"""
Graph Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles generating mind maps and concept maps in Mermaid.js syntax
    using LiteLLM. It loads model configuration at module startup, failing immediately
    if LLM_MODEL or LLM_API_KEY are unset. It performs completion calls securely, and
    uses the validate_and_sanitize_mermaid helper to clean and validate output formats
    and XSS security.
"""

import logging
import os
import re
import litellm

# Import Mermaid validation helpers
from services.mermaid_validator import validate_and_sanitize_mermaid, InvalidMermaidError

logger = logging.getLogger("server_graph_service")

# Costanti del diagramma Mermaid di fallback valido e minimo
FALLBACK_MERMAID_DIAGRAM = 'graph TD\n    ERROR_NODE["Mappa concettuale non renderizzabile, riprovare"]'
INVALID_MERMAID_FALLBACK = (
    "graph TD\n"
    "    A[\"Impossibile generare la mappa concettuale\"] --> B[\"Riprova con un altro argomento\"]"
)

def generate_concept_map(
    topic: str,
    language: str,
    llm_model: str,
    llm_api_key: str | None,
    llm_api_base: str | None
) -> str:
    """
    Generates Mermaid graph flowchart syntax for a concept map on topic in the given language.

    Args:
        topic: The topic of the concept map.
        language: The target language (e.g. "it").
        llm_model: The LLM model to use.
        llm_api_key: Optional API key.
        llm_api_base: Optional API base.

    Returns:
        The raw Mermaid graph syntax string, cleaned and fully validated.
    """
    logger.info("Generating concept map for topic: '%s' in language: '%s'", topic, language)

    system_prompt = (
        "Sei un generatore di codice Mermaid.js. Devi generare una mappa concettuale sull'argomento richiesto.\n"
        "REGOLE OBBLIGATORIE:\n"
        "1. Inizia la risposta TASSATIVAMENTE con `graph TD`.\n"
        "2. NON usare alcun tipo di stile CSS in-line o classi custom (nessun `:::`).\n"
        "3. Racchiudi ESPLICITAMENTE il testo di ogni singolo nodo tra virgolette doppie. Esempio: ID[\"Testo del nodo\"]\n"
        "4. Restituisci UNICAMENTE la struttura del grafico, senza alcuna introduzione, convenevole o spiegazione conversazionale.\n"
        "5. È TASSATIVAMENTE VIETATO usare i tag <think>...</think> o produrre qualsiasi tipo di ragionamento Chain of Thought (CoT). Non includere nessun pensiero o passaggio intermedio, scrivi direttamente la struttura del grafico."
    )

    user_prompt = f"Topic: {topic}, Language: {language}"

    # Call LiteLLM completion with only configured parameters
    completion_args = {
        "model": llm_model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "extra_body": {
            "options": {
                "num_ctx": 8192,
                "temperature": 0.0
            }
        }
    }
    if llm_api_key:
        completion_args["api_key"] = llm_api_key
    if llm_api_base:
        completion_args["api_base"] = llm_api_base

    try:
        response = litellm.completion(**completion_args)
    except Exception as e:
        logger.error("Errore durante la chiamata LiteLLM completion: %s", e, exc_info=True)
        return FALLBACK_MERMAID_DIAGRAM

    # 1. Rafforzare l'estrazione dell'output di LiteLLM
    content = None
    if response and hasattr(response, "choices") and response.choices:
        choice = response.choices[0]
        if hasattr(choice, "message") and choice.message:
            msg = choice.message

            # Check content
            val = getattr(msg, "content", None)
            if isinstance(val, str):
                content = val
            elif isinstance(msg, dict) and isinstance(msg.get("content"), str):
                content = msg.get("content")

            # Check reasoning_content
            if not content:
                val = getattr(msg, "reasoning_content", None)
                if isinstance(val, str):
                    content = val
                elif isinstance(msg, dict) and isinstance(msg.get("reasoning_content"), str):
                    content = msg.get("reasoning_content")

            # Check text
            if not content:
                val = getattr(msg, "text", None)
                if isinstance(val, str):
                    content = val
                elif isinstance(msg, dict) and isinstance(msg.get("text"), str):
                    content = msg.get("text")

        # Fallback check on the choice object itself
        if not content:
            val = getattr(choice, "text", None)
            if isinstance(val, str):
                content = val
            elif isinstance(choice, dict) and isinstance(choice.get("text"), str):
                content = choice.get("text")

    # Fallback on raw response if still empty
    if not content and response:
        if isinstance(response, dict):
            val = response.get("text") or response.get("content")
            if isinstance(val, str):
                content = val
        else:
            val = getattr(response, "text", None) or getattr(response, "content", None)
            if isinstance(val, str):
                content = val

    # Se content è ancora vuoto, registra nei log l'oggetto grezzo restituito da LiteLLM
    if not content:
        logger.error(f"LiteLLM raw response: {response}")
        content = ""

    # Pulizia e Sanificazione dell'Output (Pre-validazione)
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    content = re.sub(r'```(?:mermaid)?', '', content)
    content = content.strip()

    # 2. Gestione dell'eccezione e Diagramma di Fallback
    try:
        sanitized_mermaid = validate_and_sanitize_mermaid(content)
        return sanitized_mermaid
    except InvalidMermaidError as ime:
        logger.error("Errore di validazione Mermaid: %s", ime, exc_info=True)
        return INVALID_MERMAID_FALLBACK
    except Exception as e:
        logger.error("Errore generico durante la validazione del diagramma Mermaid: %s", e, exc_info=True)
        return FALLBACK_MERMAID_DIAGRAM
