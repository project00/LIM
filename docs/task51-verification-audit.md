# Task 51 Verification Audit

This document presents a detailed verification of Task 51 implementation regarding skipping subtitle translation on low language-detection confidence.

---

## 1. Body of `transcribe_audio()` in `server/services/stt_service.py`

Below is the complete literal body of the `transcribe_audio` function, including the exact return statement:

```python
def transcribe_audio(audio_base64: str, sample_rate: int, encoding: str) -> tuple[str, float]:
    """
    Decodes base64-encoded audio, converts PCM bytes to a float32 NumPy array,
    and performs speech-to-text using the module-level WhisperModel.

    Args:
        audio_base64: Base64-encoded string of the raw audio bytes.
        sample_rate: Sample rate of the audio (e.g., 16000).
        encoding: Encoding format of the audio (e.g., "pcm_s16le").

    Returns:
        A tuple of (transcribed_text, language_probability).

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

        # Extract detected language probability safely (handling mocks without language_probability)
        language_probability = 1.0
        if info is not None:
            prob = getattr(info, "language_probability", None)
            if isinstance(prob, (int, float)):
                language_probability = float(prob)

        logger.info(
            "Transcription completed. Transcribed length: %d chars. Language prob: %.4f",
            len(full_text),
            language_probability,
        )
        return full_text, language_probability

    except Exception as e:
        logger.error("Error occurred during Whisper model transcription: %s", e)
        raise
```

---

## 2. Call Sites of `transcribe_audio()` Service Function

We have grepped the entire `server/` directory for call sites of the service function `transcribe_audio()`. Excluding imports and definitions, the following call sites are active and each correctly unpacks the `(text, lang_prob)` tuple.

### Call Site 1: `server/main.py`
Located within the `transcribe_audio` action route handler inside `server/main.py`:

```python
        try:
            # Transcribe audio using the STT service
            text, lang_prob = transcribe_audio(
                audio_base64=audio_base64,
                sample_rate=int(sample_rate),
                encoding=str(encoding),
            )
```

### Call Site 2: `server/tests/test_stt.py`
In the unit test `test_transcribe_audio_success`:

```python
    result_text, lang_prob = transcribe_audio(
        audio_base64=audio_base64,
        sample_rate=16000,
        encoding="pcm_s16le"
    )

    assert result_text == "Hello world from mocked Whisper"
    assert lang_prob == 0.85
```

Each of these call sites successfully unpacks the return value as a `(text, language_probability)` tuple, rather than treating it as a bare string.

---

## 3. Confidence Threshold Logic and Skip Logging in `server/main.py`

Below is the literal segment of the `transcribe_audio` route handler inside `server/main.py` illustrating how `STT_LANGUAGE_CONFIDENCE_THRESHOLD` is parsed, compared, and logged:

```python
            target_language = data_obj.get("target_language")
            translated_text = None
            if target_language:
                # Retrieve custom confidence threshold from environment variables (default 0.5)
                conf_threshold_str = os.getenv("STT_LANGUAGE_CONFIDENCE_THRESHOLD", "0.5")
                try:
                    conf_threshold = float(conf_threshold_str)
                except ValueError:
                    conf_threshold = 0.5

                if lang_prob < conf_threshold:
                    logger.info(
                        "Traduzione saltata: rilevamento lingua a bassa confidenza (prob=%.2f)",
                        lang_prob,
                    )
                elif x_model:
                    try:
                        translated_text = translate_text(
                            text, str(target_language), x_model, x_key, x_base
                        )
                    except openai.OpenAIError as e:
                        logger.error(
                            f"Translation failed due to LLM provider error: {e}",
                            exc_info=True,
                        )
                else:
                    logger.info("Translation skipped: X-LLM-Model header is missing.")
```

### Confirmations:
- **Silent Default Execution**: The retrieval reads `os.getenv("STT_LANGUAGE_CONFIDENCE_THRESHOLD", "0.5")` and wraps conversion in a `try-except ValueError` block falling back to `0.5`, avoiding any fail-fast behavior.
- **Log Message Uniqueness**: The low confidence skip log message is `"Traduzione saltata: rilevamento lingua a bassa confidenza (prob=%.2f)"` which is entirely distinct from the other skip log messages:
  - Missing LLM credential message: `"Translation skipped: X-LLM-Model header is missing."`

---

## 4. Returned Payload Behavior on Low Confidence

When the language detection confidence falls below the threshold, the transcribed text itself (`text`) is still returned normally to the widget, while only `translated_text` becomes `None`. No other response fields or errors are raised.

Below is the literal response-building code at the end of the `transcribe_audio` block in `server/main.py` showing this behavior:

```python
            return {
                "type": "transcription",
                "source": "remote_stt",
                "text": text,
                "translated_text": translated_text,
            }
```

---

## 5. Changes to `server/tests/test_rate_limit.py`

### Why changes were needed:
The function `test_action_aware_rate_limiting` in `server/tests/test_rate_limit.py` mocks `transcribe_audio` with `@patch("main.transcribe_audio")`.
Before Task 51, the service function `transcribe_audio()` returned a single string value. When Task 51 was implemented, the function's return signature changed to a tuple `tuple[str, float]` containing the transcribed text and the language probability.
If the mock return value had not been updated, the route handler in `server/main.py` calling `text, lang_prob = transcribe_audio(...)` would attempt to unpack a single string (the mock's default or configured string return value), which would throw a `ValueError` (too many values to unpack, or incorrect unpacking), causing the test to fail.

### Specific lines changed:

```python
    # Configure mock completion and stt responses
    mock_stt.return_value = ("Hello", 0.9)
```

By changing `mock_stt.return_value` to `("Hello", 0.9)`, it matches the expected unpacked tuple structure.

---

## 6. Unit Test for Skipping Translation on Low Confidence

Below is the full literal body of the new test confirming that `translate_text` is NOT called when `language_probability` is below threshold:

```python
@patch("litellm.completion")
def test_transcribe_audio_skips_translation_on_low_confidence(mock_completion: MagicMock) -> None:
    """
    Tests that if language detection confidence is below the threshold,
    the translation is skipped and translated_text is returned as None,
    even if target_language and LLM credentials are provided.
    """
    raw_bytes = b"\x00" * 200
    audio_base64 = base64.b64encode(raw_bytes).decode("utf-8")

    # 1. Mock low confidence language detection (prob = 0.28 < default 0.5)
    mock_seg = MagicMock()
    mock_seg.text = "Hello low confidence world"
    mock_info = MagicMock()
    mock_info.language_probability = 0.28
    mocked_model_instance.transcribe.return_value = ([mock_seg], mock_info)

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

    # Use default threshold 0.5 (so 0.28 triggers skip)
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "transcription"
    assert data["text"] == "Hello low confidence world"
    assert data["translated_text"] is None

    # Verify that LiteLLM completion was NOT called
    mock_completion.assert_not_called()
```
