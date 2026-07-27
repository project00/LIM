"""
Quiz Generation Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles generating short quizzes based on a given lesson context
    using LiteLLM. It strictly reuses the same LLM configuration and keys as the graph
    generation and translation services to ensure consistency. It validates and parses
    the LLM's response using the strict quiz validator before returning the output.
"""

import logging
import os
import litellm

# Import validator logic
from services.quiz_validator import validate_and_parse_quiz

logger = logging.getLogger("server_quiz_service")

# Ensure required LLM_MODEL environment variable is present at module startup (fail-fast)
LLM_MODEL = os.getenv("LLM_MODEL")
if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL environment variable is not configured. Server startup aborted.")

# Ensure required LLM_API_KEY environment variable is present at module startup (fail-fast)
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY environment variable is not configured. Server startup aborted.")

LLM_API_BASE = os.getenv("LLM_API_BASE")


def generate_quiz(lesson_context: str, num_questions: int) -> list[dict]:
    """
    Generates a quiz based on the provided lesson context and number of questions.

    Args:
        lesson_context: A string summarizing the lesson context / content.
        num_questions: Number of questions requested (usually 3 to 5).

    Returns:
        List of validated question dictionaries.
    """
    logger.info(
        "Generating quiz with %d questions. Lesson context length: %d chars.",
        num_questions,
        len(lesson_context) if lesson_context else 0
    )

    prompt = (
        "Generate a multiple-choice quiz based on the following lesson context.\n"
        f"Number of questions requested: {num_questions} (must be between 3 and 5).\n"
        "\n"
        "Your output must consist ONLY of a valid JSON array of question objects. "
        "Do not include any introductions, explanations, or markdown code fences (like ```json). "
        "Every question object in the array must match this exact schema format:\n"
        "{\n"
        '  "question": "The question text here",\n'
        '  "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        '  "correct_index": 1\n'
        "}\n"
        "Note: correct_index must be a 0-based integer representing the correct answer inside options.\n"
        "\n"
        f"Lesson Context:\n{lesson_context}"
    )

    # Call LiteLLM completion
    response = litellm.completion(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.choices[0].message.content or ""

    # Parse and validate quiz
    validated_quiz = validate_and_parse_quiz(content)
    return validated_quiz
