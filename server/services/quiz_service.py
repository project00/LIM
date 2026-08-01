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

def generate_quiz(
    lesson_context: str,
    num_questions: int,
    llm_model: str,
    llm_api_key: str | None,
    llm_api_base: str | None
) -> list[dict]:
    """
    Generates a quiz based on the provided lesson context and number of questions.

    Args:
        lesson_context: A string summarizing the lesson context / content.
        num_questions: Number of questions requested (usually 3 to 5).
        llm_model: The LLM model to use.
        llm_api_key: Optional API key.
        llm_api_base: Optional API base.

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

    # Parse and validate quiz
    validated_quiz = validate_and_parse_quiz(content)
    return validated_quiz
