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

# Ensure required LLM_API_KEY environment variable is present at module startup (fail-fast)
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY environment variable is not configured. Server startup aborted.")

LLM_API_BASE = os.getenv("LLM_API_BASE")


def generate_summary(lesson_log: List[Dict[str, Any]]) -> str:
    """
    Generates a lesson summary based on the provided lesson log.

    Args:
        lesson_log: A list of dict entries representing the lesson log.

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

    # Call LiteLLM completion
    response = litellm.completion(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        messages=[{"role": "user", "content": prompt}]
    )

    summary = response.choices[0].message.content or ""
    return summary.strip()
