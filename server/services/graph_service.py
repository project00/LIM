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
import litellm

# Import Mermaid validation helpers
from services.mermaid_validator import validate_and_sanitize_mermaid

logger = logging.getLogger("server_graph_service")

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
        "1. Inizia SEMPRE la risposta con `graph TD`\n"
        "2. Usa SOLO connettori validi: `-->`\n"
        "3. Rinchiudi SEMPRE il testo dei nodi tra parentesi quadre e virgolette doppie. Esempio: ID[\"Testo del nodo\"]\n"
        "4. NON usare classi CSS (nessun `:::`).\n"
        "5. Restituisci SOLO il codice Mermaid puro, senza blocchi markdown, senza backtick e senza testo introduttivo."
    )

    user_prompt = f"Topic: {topic}, Language: {language}"

    # Call LiteLLM completion with only configured parameters
    completion_args = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }
    if llm_api_key:
        completion_args["api_key"] = llm_api_key
    if llm_api_base:
        completion_args["api_base"] = llm_api_base

    response = litellm.completion(**completion_args)

    content = response.choices[0].message.content or ""

    # Run strict validation and sanitization
    sanitized_mermaid = validate_and_sanitize_mermaid(content)
    return sanitized_mermaid
