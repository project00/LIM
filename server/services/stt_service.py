"""
Speech-to-Text (STT) Service for LIM-AI Copilot Remote Server.

Design Note:
    This module implements the speech-to-text service utilizing the `faster-whisper`
    library for optimized transcription. A single `WhisperModel` instance is loaded at the
    module level (fail-fast on startup) rather than on every request to avoid high latency and
    unnecessary overhead. Real audio chunks are received as base64-encoded raw PCM bytes
    which are converted to 1-D float32 numpy arrays normalized between -1.0 and 1.0,
    the representation expected by Whisper models.
"""

import base64
import logging
import os
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger("server_stt_service")

# Retrieve and validate environment variables for Whisper configuration at module startup
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE")
if not WHISPER_MODEL_SIZE:
    raise RuntimeError(
        "WHISPER_MODEL_SIZE environment variable is not configured. Server startup aborted."
    )

WHISPER_DEVICE = os.getenv("WHISPER_DEVICE")
if not WHISPER_DEVICE:
    raise RuntimeError(
        "WHISPER_DEVICE environment variable is not configured. Server startup aborted."
    )

try:
    logger.info(
        "Initializing WhisperModel with size: '%s' and device: '%s'.",
        WHISPER_MODEL_SIZE,
        WHISPER_DEVICE,
    )
    # Instantiate the model at module level so it loads only once
    model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE)
except Exception as e:
    logger.error("Failed to initialize WhisperModel at startup: %s", e)
    raise RuntimeError(f"Failed to initialize WhisperModel: {e}") from e


def transcribe_audio(audio_base64: str, sample_rate: int, encoding: str) -> str:
    """
    Decodes base64-encoded audio, converts PCM bytes to a float32 NumPy array,
    and performs speech-to-text using the module-level WhisperModel.

    Args:
        audio_base64: Base64-encoded string of the raw audio bytes.
        sample_rate: Sample rate of the audio (e.g., 16000).
        encoding: Encoding format of the audio (e.g., "pcm_s16le").

    Returns:
        The fully transcribed text string from the audio segment.

    Raises:
        ValueError: If an unsupported audio encoding is provided.
    """
    logger.info(
        "Received transcription request. Sample rate: %d, Encoding: %s",
        sample_rate,
        encoding,
    )

    if encoding != "pcm_s16le":
        logger.error("Unsupported audio encoding requested: %s", encoding)
        raise ValueError(f"Unsupported audio encoding: {encoding}")

    # Decode the base64 string into raw PCM bytes
    try:
        audio_bytes = base64.b64decode(audio_base64)
    except Exception as e:
        logger.error("Failed to decode base64 audio payload: %s", e)
        raise ValueError(f"Invalid base64 payload: {e}") from e

    # Ensure buffer length is a multiple of 2 bytes (16-bit) to avoid numpy errors
    modulo = len(audio_bytes) % 2
    if modulo != 0:
        logger.warning("Audio buffer length is not a multiple of 2. Truncating tail.")
        audio_bytes = audio_bytes[:-modulo]

    # Convert raw PCM 16-bit bytes to float32 NumPy array normalized to [-1.0, 1.0]
    audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    logger.debug("Running transcription on audio array of size: %d", len(audio_array))

    try:
        # Transcribe using faster-whisper. This returns (segments, info)
        segments, info = model.transcribe(audio_array)

        # Iterate through segments and build the complete text string
        text_pieces = []
        for segment in segments:
            text_pieces.append(segment.text)

        full_text = "".join(text_pieces).strip()
        logger.info("Transcription completed. Transcribed length: %d chars.", len(full_text))
        return full_text

    except Exception as e:
        logger.error("Error occurred during Whisper model transcription: %s", e)
        raise
