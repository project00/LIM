"""
Shared Pytest Configuration and Global Mocks.

Design Note:
    To prevent any real faster-whisper model from being initialized or downloaded
    at module-import time (which happens as soon as fastapi or main are imported),
    we globally patch `faster_whisper.WhisperModel` at the very start of the test session.
    This ensures that CI never hangs or fails due to network/model loading.
"""

import os
from unittest.mock import MagicMock, patch

# Configure global mock environment variables
os.environ["API_KEY"] = "test_secret_token"
os.environ["LLM_MODEL"] = "gpt-4o-mini"
os.environ["LLM_API_KEY"] = "test_provider_key"
os.environ["WHISPER_MODEL_SIZE"] = "tiny"
os.environ["WHISPER_DEVICE"] = "cpu"

# Globally patch the WhisperModel class
whisper_patcher = patch("faster_whisper.WhisperModel")
mock_whisper_model_class = whisper_patcher.start()

# Create a shared mock model instance
mock_model_instance = MagicMock()
mock_whisper_model_class.return_value = mock_model_instance

# Make transcribe a MagicMock explicitly
mock_transcribe = MagicMock()
mock_model_instance.transcribe = mock_transcribe
