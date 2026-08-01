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

def translate_text(
    text: str,
    target_language: str,
    llm_model: str,
    llm_api_key: str | None,
    llm_api_base: str | None
) -> str:
    """
    Translates the given text into target_language using LiteLLM.

    Args:
        text: The text to translate.
        target_language: The target language (e.g. "en").
        llm_model: The LLM model to use.
        llm_api_key: Optional API key.
        llm_api_base: Optional API base.

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
        "model": llm_model,
        "messages": [{"role": "user", "content": prompt}]
    }
    if llm_api_key:
        completion_args["api_key"] = llm_api_key
    if llm_api_base:
        completion_args["api_base"] = llm_api_base

    response = litellm.completion(**completion_args)

    content = response.choices[0].message.content or ""
    return content.strip()
