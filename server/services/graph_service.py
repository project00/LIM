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

# Ensure required LLM_MODEL environment variable is present at module startup
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


def generate_concept_map(topic: str, language: str, credentials: dict | None = None) -> str:
    """
    Generates Mermaid graph flowchart syntax for a concept map on topic in the given language.

    Args:
        topic: The topic of the concept map.
        language: The target language (e.g. "it").
        credentials: Optional dictionary containing client-side/daemon-side LLM credentials.

    Returns:
        The raw Mermaid graph syntax string, cleaned and fully validated.
    """
    logger.info("Generating concept map for topic: '%s' in language: '%s'", topic, language)

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

    prompt = (
        f"Generate a concept map using only valid Mermaid graph/flowchart syntax on the topic: '{topic}' "
        f"in the language: '{language}'.\n"
        "Your output must consist ONLY of valid Mermaid graph syntax. "
        "Do not include any explanations, do not include markdown code fences (like ```mermaid), and do not include backticks."
    )

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

    content = response.choices[0].message.content or ""

    # Run strict validation and sanitization
    sanitized_mermaid = validate_and_sanitize_mermaid(content)
    return sanitized_mermaid
