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

# Ensure required LLM_MODEL environment variable is present at module startup (fail-fast)
LLM_MODEL = os.getenv("LLM_MODEL")
if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL environment variable is not configured. Server startup aborted.")

# LLM_API_KEY is optional (e.g., for local providers like Ollama). If missing or placeholder, set as empty string.
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
if LLM_API_KEY:
    LLM_API_KEY = LLM_API_KEY.strip()
    if LLM_API_KEY.startswith("replace_") or "placeholder" in LLM_API_KEY.lower() or LLM_API_KEY == "your_llm_provider_api_key_here":
        LLM_API_KEY = ""

LLM_API_BASE = os.getenv("LLM_API_BASE")
if LLM_API_BASE:
    LLM_API_BASE = LLM_API_BASE.strip()
    if not LLM_API_BASE or "placeholder" in LLM_API_BASE.lower():
        LLM_API_BASE = None


def generate_summary(lesson_log: List[Dict[str, Any]], credentials: dict | None = None) -> str:
    """
    Generates a lesson summary based on the provided lesson log.

    Args:
        lesson_log: A list of dict entries representing the lesson log.
        credentials: Optional dictionary containing client-side/daemon-side LLM credentials.

    Returns:
        A string containing the summary, split into paragraphs by \\n\\n.
    """
    logger.info("Generating summary for lesson log with %d entries.", len(lesson_log))

    # Resolve credentials
    llm_creds = (credentials or {}).get("llm") or {}
    model = llm_creds.get("model") or LLM_MODEL
    api_key = llm_creds.get("api_key") if "api_key" in llm_creds else LLM_API_KEY
    api_base = llm_creds.get("api_base") if "api_base" in llm_creds else LLM_API_BASE

    if api_key:
        api_key = api_key.strip()
        if api_key.startswith("replace_") or "placeholder" in api_key.lower() or api_key == "your_llm_provider_api_key_here":
            api_key = ""
    else:
        api_key = ""

    if api_base:
        api_base = api_base.strip()
        if not api_base or "placeholder" in api_base.lower():
            api_base = None

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
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }
        if api_key:
            completion_args["api_key"] = api_key
        if api_base:
            completion_args["api_base"] = api_base

        response = litellm.completion(**completion_args)
        summary = response.choices[0].message.content or ""
        return summary.strip()
    except litellm.exceptions.AuthenticationError as e:
        logger.error("Authentication error with LLM provider: %s", e, exc_info=True)
        return "Errore di autenticazione con il provider LLM. Verificare la chiave API."
    except litellm.exceptions.APIConnectionError as e:
        logger.error("Connection error with LLM provider: %s", e, exc_info=True)
        return "Errore di connessione con il provider LLM (es. Ollama offline o irraggiungibile)."
