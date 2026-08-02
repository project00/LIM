"""
OCR Vision Service for LIM-AI Copilot Remote Server.

Design Note:
    This module performs OCR on a captured image using a vision-capable LLM
    via LiteLLM. It accepts base64-encoded image data, constructs a proper
    multimodal message block, and calls litellm.completion.
"""

import logging
import litellm

logger = logging.getLogger("server_ocr_vision_service")


def generate_ocr_vision(
    image_base64: str, llm_model: str, llm_api_key: str | None, llm_api_base: str | None
) -> str:
    """
    Performs OCR on the provided base64-encoded image using a vision LLM.

    Args:
        image_base64: The base64-encoded image data.
        llm_model: The vision LLM model to use (e.g. gpt-4o).
        llm_api_key: Optional API key.
        llm_api_base: Optional API base.

    Returns:
        The transcribed text.
    """
    logger.info("Performing remote Vision-LLM OCR using model '%s'", llm_model)

    # Ensure correct data URI prefix for base64 image URL
    if not image_base64.startswith("data:"):
        image_url = f"data:image/png;base64,{image_base64}"
    else:
        image_url = image_base64

    prompt_text = (
        "trascrivi fedelmente il testo scritto in questa immagine, nient'altro"
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }
    ]

    completion_args = {"model": llm_model, "messages": messages}
    if llm_api_key:
        completion_args["api_key"] = llm_api_key
    if llm_api_base:
        completion_args["api_base"] = llm_api_base

    try:
        response = litellm.completion(**completion_args)
        content = response.choices[0].message.content or ""
        return content.strip()
    except Exception as e:
        logger.error("Vision-LLM OCR completion call failed: %s", e, exc_info=True)
        raise e
