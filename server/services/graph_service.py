"""
Graph Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles generating mind maps and concept maps in Mermaid.js syntax
    using LiteLLM. It loads model configuration at module startup, failing immediately
    if LLM_MODEL or LLM_API_KEY are unset. It performs completion calls securely and cleans/strips
    potential Markdown code fences before returning raw Mermaid graph syntax.
"""

import logging
import os
import litellm

logger = logging.getLogger("server_graph_service")

# Ensure required LLM_MODEL environment variable is present at module startup
LLM_MODEL = os.getenv("LLM_MODEL")
if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL environment variable is not configured. Server startup aborted.")

# Ensure required LLM_API_KEY environment variable is present at module startup (fail-fast)
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY environment variable is not configured. Server startup aborted.")

LLM_API_BASE = os.getenv("LLM_API_BASE")


def generate_concept_map(topic: str, language: str) -> str:
    """
    Generates Mermaid graph flowchart syntax for a concept map on topic in the given language.

    Args:
        topic: The topic of the concept map.
        language: The target language (e.g. "it").

    Returns:
        The raw Mermaid graph syntax string, cleaned of any markdown fences.
    """
    logger.info("Generating concept map for topic: '%s' in language: '%s'", topic, language)

    prompt = (
        f"Generate a concept map using only valid Mermaid graph/flowchart syntax on the topic: '{topic}' "
        f"in the language: '{language}'.\n"
        "Your output must consist ONLY of valid Mermaid graph syntax. "
        "Do not include any explanations, do not include markdown code fences (like ```mermaid), and do not include backticks."
    )

    # Call LiteLLM completion
    response = litellm.completion(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.choices[0].message.content or ""

    # Light strip of markdown/mermaid code fences if present
    content_stripped = content.strip()
    if content_stripped.startswith("```"):
        lines = content_stripped.splitlines()
        if len(lines) >= 2:
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            content_stripped = "\n".join(lines).strip()

    content_stripped = content_stripped.replace("```mermaid", "").replace("```", "").strip()
    return content_stripped
