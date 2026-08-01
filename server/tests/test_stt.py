"""
Unit and Integration Tests for Speech-to-Text (STT) Service.

Design Note:
    This module tests the STT transcription pipeline end-to-end.
    The WhisperModel is mocked globally via `conftest.py` to prevent any real model download.
    We import `services.stt_service.model` (which is our shared global mock) to configure
    mock transcription segments and assert on transcription arguments.
"""

import os
import sys
import base64
import wave
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.stt_service import transcribe_audio, model as mocked_model_instance
from main import app


@pytest.fixture(autouse=True)
def reset_mock_model() -> None:
    """Resets the mocked WhisperModel instance between test cases."""
    mocked_model_instance.transcribe.reset_mock()


def test_transcribe_audio_success() -> None:
    """Tests that transcribe_audio successfully decodes base64, runs transcription, and returns text."""
    # Generate 100 samples of 16-bit PCM silent audio (200 bytes)
    raw_bytes = b"\x00" * 200
    audio_base64 = base64.b64encode(raw_bytes).decode("utf-8")

    # Set up mock transcription segments
    mock_seg = MagicMock()
    mock_seg.text = "Hello world from mocked Whisper"
    mocked_model_instance.transcribe.return_value = ([mock_seg], MagicMock())

    result_text = transcribe_audio(
        audio_base64=audio_base64,
        sample_rate=16000,
        encoding="pcm_s16le"
    )

    assert result_text == "Hello world from mocked Whisper"

    # Verify faster-whisper was called with the correct numpy array
    mocked_model_instance.transcribe.assert_called_once()
    called_array = mocked_model_instance.transcribe.call_args[0][0]
    assert isinstance(called_array, np.ndarray)
    assert called_array.dtype == np.float32
    assert len(called_array) == 100
    assert np.allclose(called_array, 0.0)


def test_transcribe_audio_invalid_encoding() -> None:
    """Tests that transcribe_audio raises ValueError for unsupported audio encodings."""
    with pytest.raises(ValueError, match="Unsupported audio encoding"):
        transcribe_audio(
            audio_base64="aaaa",
            sample_rate=16000,
            encoding="mp3"
        )


def test_transcribe_audio_invalid_base64() -> None:
    """Tests that transcribe_audio handles invalid base64 payloads gracefully."""
    with pytest.raises(ValueError, match="Invalid base64 payload"):
        transcribe_audio(
            audio_base64="!!!not-base64!!!",
            sample_rate=16000,
            encoding="pcm_s16le"
        )


def test_analyze_endpoint_missing_parameters() -> None:
    """Tests that POST /api/v1/analyze returns 400 when required fields are missing."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}

    # Missing audio_base64
    payload_missing_audio = {
        "action": "transcribe_audio",
        "data": {
            "sample_rate": 16000,
            "encoding": "pcm_s16le"
        }
    }
    resp = client.post("/api/v1/analyze", json=payload_missing_audio, headers=headers)
    assert resp.status_code == 400
    assert "Missing required fields" in resp.json()["detail"]


def test_wav_fixture_end_to_end(tmp_path: Path) -> None:
    """
    Tests end-to-end transcription routing using a real short WAV file fixture.
    Verifies that base64-decode-to-bytes plumbing works end-to-end with real audio bytes,
    while WhisperModel.transcribe remains mocked.
    """
    # 1. Create a real short WAV file as a fixture on disk
    wav_path = tmp_path / "short_fixture.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(16000)
        # Write 0.1 seconds of silence (1600 frames * 2 bytes = 3200 bytes)
        wav_file.writeframes(b"\x00" * 3200)

    # 2. Read the real WAV file's raw PCM frames
    with wave.open(str(wav_path), "rb") as wav_file:
        params = wav_file.getparams()
        assert params.framerate == 16000
        raw_pcm_bytes = wav_file.readframes(params.nframes)

    # 3. Base64 encode the raw PCM bytes (the body expected by transcribe_audio endpoint)
    audio_base64 = base64.b64encode(raw_pcm_bytes).decode("utf-8")

    # 4. Configure mocked Whisper return value
    mock_seg = MagicMock()
    mock_seg.text = "This is a real WAV test."
    mocked_model_instance.transcribe.return_value = ([mock_seg], MagicMock())

    # 5. Call `/api/v1/analyze` endpoint
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "transcribe_audio",
        "data": {
            "audio_base64": audio_base64,
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "target_language": None  # Target language is None so translation is skipped
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "transcription"
    assert data["source"] == "remote_stt"
    assert data["text"] == "This is a real WAV test."
    assert data["translated_text"] is None

    # 6. Verify WhisperModel was called with correct NumPy floats
    mocked_model_instance.transcribe.assert_called_once()
    called_array = mocked_model_instance.transcribe.call_args[0][0]
    assert isinstance(called_array, np.ndarray)
    assert called_array.dtype == np.float32
    assert len(called_array) == 1600  # 3200 bytes / 2 bytes per sample = 1600 samples
    assert np.allclose(called_array, 0.0)


def test_import_fails_when_whisper_model_size_unset() -> None:
    """Tests that importing stt_service raises RuntimeError if WHISPER_MODEL_SIZE is unset."""
    import importlib
    import sys

    # Save current env values
    orig_size = os.environ.get("WHISPER_MODEL_SIZE")

    # Remove from env and from sys.modules to force a fresh re-import/re-evaluation
    if "WHISPER_MODEL_SIZE" in os.environ:
        del os.environ["WHISPER_MODEL_SIZE"]
    if "services.stt_service" in sys.modules:
        del sys.modules["services.stt_service"]

    try:
        with pytest.raises(RuntimeError, match="WHISPER_MODEL_SIZE environment variable is not configured"):
            importlib.import_module("services.stt_service")
    finally:
        # Restore env and re-import/restore sys.modules to original state so other tests are unaffected
        if orig_size is not None:
            os.environ["WHISPER_MODEL_SIZE"] = orig_size
        else:
            os.environ["WHISPER_MODEL_SIZE"] = "tiny"
        if "services.stt_service" in sys.modules:
            del sys.modules["services.stt_service"]
        importlib.import_module("services.stt_service")


@patch("litellm.completion")
def test_transcribe_audio_with_translation_success(mock_completion: MagicMock) -> None:
    """
    Tests that POST /api/v1/analyze with a 'transcribe_audio' action and truthy target_language
    calls the translation service using LiteLLM and returns the translated text.
    """
    # 1. Create silent audio
    raw_bytes = b"\x00" * 200
    audio_base64 = base64.b64encode(raw_bytes).decode("utf-8")

    # 2. Mock STT transcription response
    mock_seg = MagicMock()
    mock_seg.text = "Hello world"
    mocked_model_instance.transcribe.return_value = ([mock_seg], MagicMock())

    # 3. Mock LiteLLM translation response
    mock_choice = MagicMock()
    mock_choice.message.content = "Ciao mondo"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-LLM-Model": "gpt-4o-mini",
        "X-LLM-API-Key": "test_provider_key"
    }
    payload = {
        "action": "transcribe_audio",
        "data": {
            "audio_base64": audio_base64,
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "target_language": "it"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "transcription"
    assert data["text"] == "Hello world"
    assert data["translated_text"] == "Ciao mondo"

    # Verify that LiteLLM completion was called with the correct prompt and parameters
    mock_completion.assert_called_once()
    called_kwargs = mock_completion.call_args[1]
    assert called_kwargs["model"] == "gpt-4o-mini"
    assert called_kwargs["api_key"] == "test_provider_key"
    messages = called_kwargs["messages"]
    assert len(messages) == 1
    assert "Translate" in messages[0]["content"]
    assert "it" in messages[0]["content"]
    assert "Hello world" in messages[0]["content"]


@patch("litellm.completion")
def test_transcribe_audio_without_translation_skips(mock_completion: MagicMock) -> None:
    """
    Tests that POST /api/v1/analyze with target_language omitted or null
    does not call the translation service and leaves translated_text as None.
    """
    raw_bytes = b"\x00" * 200
    audio_base64 = base64.b64encode(raw_bytes).decode("utf-8")

    mock_seg = MagicMock()
    mock_seg.text = "Hello world"
    mocked_model_instance.transcribe.return_value = ([mock_seg], MagicMock())

    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "transcribe_audio",
        "data": {
            "audio_base64": audio_base64,
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "target_language": None
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "transcription"
    assert data["text"] == "Hello world"
    assert data["translated_text"] is None

    # Verify LiteLLM completion was NOT called
    mock_completion.assert_not_called()


@patch("litellm.completion")
def test_transcribe_audio_with_translation_error(mock_completion: MagicMock) -> None:
    """
    Tests that if translation fails with a LiteLLM error (e.g. APIError),
    the endpoint still returns status 200 with the correct transcription text and translated_text set to None.
    """
    # 1. Create silent audio
    raw_bytes = b"\x00" * 200
    audio_base64 = base64.b64encode(raw_bytes).decode("utf-8")

    # 2. Mock STT transcription response
    mock_seg = MagicMock()
    mock_seg.text = "Hello world"
    mocked_model_instance.transcribe.return_value = ([mock_seg], MagicMock())

    # 3. Mock LiteLLM to raise an APIError
    import litellm
    mock_completion.side_effect = litellm.exceptions.APIError(
        message="Simulated LLM provider error",
        status_code=500,
        llm_provider="openai",
        model="gpt-4o-mini"
    )

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-LLM-Model": "gpt-4o-mini",
        "X-LLM-API-Key": "test_provider_key"
    }
    payload = {
        "action": "transcribe_audio",
        "data": {
            "audio_base64": audio_base64,
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "target_language": "it"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "transcription"
    assert data["text"] == "Hello world"
    assert data["translated_text"] is None


@patch("litellm.completion")
def test_transcribe_audio_translation_graceful_degradation_missing_model(mock_completion: MagicMock) -> None:
    """
    Tests that if target_language is set but X-LLM-Model header is missing,
    the request succeeds with translated_text set to None (graceful degradation).
    """
    raw_bytes = b"\x00" * 200
    audio_base64 = base64.b64encode(raw_bytes).decode("utf-8")

    mock_seg = MagicMock()
    mock_seg.text = "Hello world"
    mocked_model_instance.transcribe.return_value = ([mock_seg], MagicMock())

    client = TestClient(app)
    # X-LLM-Model is missing in headers!
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "transcribe_audio",
        "data": {
            "audio_base64": audio_base64,
            "sample_rate": 16000,
            "encoding": "pcm_s16le",
            "target_language": "it"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "transcription"
    assert data["text"] == "Hello world"
    assert data["translated_text"] is None

    # Verify LiteLLM completion was NOT called
    mock_completion.assert_not_called()


def test_import_fails_when_whisper_device_unset() -> None:
    """Tests that importing stt_service raises RuntimeError if WHISPER_DEVICE is unset."""
    import importlib
    import sys

    # Save current env values
    orig_device = os.environ.get("WHISPER_DEVICE")

    # Remove from env and from sys.modules to force a fresh re-import/re-evaluation
    if "WHISPER_DEVICE" in os.environ:
        del os.environ["WHISPER_DEVICE"]
    if "services.stt_service" in sys.modules:
        del sys.modules["services.stt_service"]

    try:
        with pytest.raises(RuntimeError, match="WHISPER_DEVICE environment variable is not configured"):
            importlib.import_module("services.stt_service")
    finally:
        # Restore env and re-import/restore sys.modules to original state so other tests are unaffected
        if orig_device is not None:
            os.environ["WHISPER_DEVICE"] = orig_device
        else:
            os.environ["WHISPER_DEVICE"] = "cpu"
        if "services.stt_service" in sys.modules:
            del sys.modules["services.stt_service"]
        importlib.import_module("services.stt_service")
