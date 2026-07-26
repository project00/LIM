```python
            target_language = data_obj.get("target_language")
            translated_text = None
            if target_language:
                try:
                    translated_text = translate_text(text, str(target_language))
                except openai.OpenAIError as e:
                    logger.error(
                        f"Translation failed due to LLM provider error: {e}",
                        exc_info=True
                    )
```

```python
import logging
import os
import litellm

logger = logging.getLogger("server_translate_service")

# Ensure required LLM_MODEL environment variable is present at module startup
LLM_MODEL = os.getenv("LLM_MODEL")
if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL environment variable is not configured. Server startup aborted.")

# Ensure required LLM_API_KEY environment variable is present at module startup (fail-fast)
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY environment variable is not configured. Server startup aborted.")

LLM_API_BASE = os.getenv("LLM_API_BASE")
```
Uses the same env vars as graph_service.py (Task 8): YES

```python
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
```
translate_text signature matches (text: str, target_language: str) -> str as specified: YES
