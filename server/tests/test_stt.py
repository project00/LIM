"""
Unit and Integration Tests for Speech-to-Text (STT) Service.

Design Note:
    This module tests the STT transcription pipeline end-to-end.
    The WhisperModel is mocked globally via `conftest.py` to prevent any real model download.
    We import `services.stt_service.model` (which is our shared global mock) to configure
    mock transcription segments and assert on transcription arguments.
"""

import sys
import base64
import wave
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock
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
            "target_language": "en"  # Target language is ignored and translated_text remains null
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
