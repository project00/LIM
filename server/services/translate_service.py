"""
Translation Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles translating transcribed text into a target language
    using LiteLLM. It reuses the exact same model configuration and client pattern
    as the graph generation service to ensure maximum simplicity and consistency.
    It performs completion calls securely and fails immediately at startup if the required
    LLM_MODEL or LLM_API_KEY environments are not configured.
"""

import logging
import os
import litellm

logger = logging.getLogger("server_translate_service")

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


def translate_text(text: str, target_language: str) -> str:
    """
    Translates the given text into target_language using LiteLLM.

    Args:
        text: The text to translate.
        target_language: The target language (e.g. "en").

    Returns:
        The translated text only.
    """
    if not text.strip():
        return text

    logger.info("Translating text to target language: '%s'", target_language)

    prompt = (
        f"Translate the following text into the target language: '{target_language}'.\n"
        "Your output must consist ONLY of the translated text. Do not include any explanations, "
        "no introduction, no markdown formatting, no quotes, and no extra formatting.\n"
        f"Text to translate:\n{text}"
    )

    # Call LiteLLM completion with only configured parameters
    completion_args = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }
    if LLM_API_KEY:
        completion_args["api_key"] = LLM_API_KEY
    if LLM_API_BASE:
        completion_args["api_base"] = LLM_API_BASE

    response = litellm.completion(**completion_args)

    content = response.choices[0].message.content or ""
    return content.strip()
