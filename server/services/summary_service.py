"""
Summary Generation Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles generating a lesson summary based on the provided
    lesson log using LiteLLM. It strictly reuses the same LLM configuration and keys as the other
    services. It formats the lesson log entries, constructs a structured prompt, and queries
    the LLM to return a plain text summary split into paragraphs by \\n\\n.
"""

import logging
import os
import litellm
from typing import Any, Dict, List

logger = logging.getLogger("server_summary_service")

def generate_summary(
    lesson_log: List[Dict[str, Any]],
    llm_model: str,
    llm_api_key: str | None,
    llm_api_base: str | None
) -> str:
    """
    Generates a lesson summary based on the provided lesson log.

    Args:
        lesson_log: A list of dict entries representing the lesson log.
        llm_model: The LLM model to use (e.g. gpt-4o).
        llm_api_key: Optional API key.
        llm_api_base: Optional API base.

    Returns:
        A string containing the summary, split into paragraphs by \\n\\n.
    """
    logger.info("Generating summary for lesson log with %d entries.", len(lesson_log))

    # Format the lesson log into a human-readable text for the prompt
    formatted_log = []
    for entry in lesson_log:
        entry_type = entry.get("type", "unknown")
        content = entry.get("content", "")
        timestamp = entry.get("timestamp", "")
        formatted_log.append(f"[{timestamp}] Type: {entry_type} | Content: {content}")

    log_text = "\n".join(formatted_log)

    prompt = (
        "Sei un assistente didattico per docenti di scuole italiane. "
        "Genera un riassunto strutturato e chiaro della lezione scolastica basandoti sul seguente registro delle attività svolte durante la lezione (lesson log).\n"
        "Raggruppa e organizza le attività per argomento/tema laddove sensato.\n\n"
        "Il riassunto deve essere scritto in italiano fluente e in formato testo semplice (plain text), "
        "con i paragrafi separati esattamente da una doppia andata a capo (\\n\\n).\n"
        "NON usare markdown, NON usare HTML, e NON inserire blocchi di codice o recinti (code fences come ```).\n"
        "\n"
        "Registro delle Attività:\n"
        f"{log_text}\n"
    )

    try:
        # Call LiteLLM completion with only configured parameters
        completion_args = {
            "model": llm_model,
            "messages": [{"role": "user", "content": prompt}]
        }
        if llm_api_key:
            completion_args["api_key"] = llm_api_key
        if llm_api_base:
            completion_args["api_base"] = llm_api_base

        response = litellm.completion(**completion_args)
        summary = response.choices[0].message.content or ""
        return summary.strip()
    except litellm.exceptions.AuthenticationError as e:
        logger.error("Authentication error with LLM provider: %s", e, exc_info=True)
        return "Errore di autenticazione con il provider LLM. Verificare la chiave API."
    except litellm.exceptions.APIConnectionError as e:
        logger.error("Connection error with LLM provider: %s", e, exc_info=True)
        return "Errore di connessione con il provider LLM (es. Ollama offline o irraggiungibile)."
