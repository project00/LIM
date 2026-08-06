# Task 49 Verification Audit

## 1. Git Status & Config File Analysis

### Git Status Output
```
On branch jules-15470643155332969227-daf8c78b
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	modified:   .gitignore
	deleted:    daemon/config.yaml
	modified:   daemon/local_bridge.py
	new file:   daemon/tests/conftest.py

```

### Git Diff for daemon/config.yaml
```
diff --git a/daemon/config.yaml b/daemon/config.yaml
deleted file mode 100644
index 6c2ba11..0000000
--- a/daemon/config.yaml
+++ /dev/null
@@ -1,30 +0,0 @@
-api_key: ''
-credentials:
-- api_base: null
-  api_key: null
-  enabled: true
-  id: 87620d16-dacf-430d-a2d7-f02119051042
-  model: qwen
-  name: Concept Map Qwen
-  scope: concept_map
-  type: llm_cloud
-- api_base: null
-  api_key: null
-  enabled: false
-  id: 31197316-2fae-4a96-b8f7-8bb985f4bfe6
-  model: gemma
-  name: Translate Gemma
-  scope: translation
-  type: llm_ollama
-- api_base: null
-  api_key: null
-  enabled: true
-  id: b809fc2e-b190-4769-9b67-f3c3abe85fa2
-  model: deepseek
-  name: Translate DeepSeek
-  scope: translation
-  type: llm_cloud
-disable_local_backup: false
-remote_action_timeout_seconds: 30
-remote_base_url: http://192.168.1.100:8000
-silence_rms_threshold: 400
```

### Gitignore Status
`daemon/config.yaml` is not listed in `.gitignore` originally. It is now added to `.gitignore` and removed from tracking via `git rm --cached daemon/config.yaml`.

### Edits to daemon/config.yaml explanation
During test execution, settings endpoints in `settings_api.py` (such as `add_credential`, `toggle_credential`, and `delete_credential`) are invoked. These endpoints call `save_settings(settings)`, which calls `yaml.safe_dump(s.model_dump(), f)` directly on `CONFIG_PATH` pointing to the file `daemon/config.yaml` on disk. Because the tests do not mock this file path or use a separate mock/fixture configuration file, the settings API writes directly to `daemon/config.yaml` during tests, modifying the credential IDs and states.

---

## 2. Server Mocks Cleanliness

### Explanation
There are no references to "piper", "tts", or "text_to_speech" inside `server/` code or server tests. The Text-To-Speech feature is a local daemon-only feature. Because `server/` code does not reference or load any piper-related modules, no mock is required inside `server/tests/conftest.py`. The mocks have been removed, and the server tests still pass successfully:

```
============================== 68 passed in 6.73s ==============================
```

---

## 3. Lazy Import Piper Code

### Local Bridge Grep Output
```
983:                                import piper
```

### Context from daemon/local_bridge.py
```python
                    elif action == "text_to_speech":
                        data_obj = payload.get("data") or {}
                        text = data_obj.get("text", "")

                        voice_model_path = os.getenv("PIPER_VOICE_MODEL_PATH")
                        if not voice_model_path or not os.path.exists(voice_model_path):
                            err_res = {
                                "type": "error",
                                "code": "TTS_NOT_CONFIGURED",
                                "action": "text_to_speech",
                                "message": "Nessun modello vocale Piper configurato. Scarica un modello .onnx (es. da rhasspy/piper-voices su Hugging Face) e imposta PIPER_VOICE_MODEL_PATH."
                            }
                            await websocket.send_text(json.dumps(err_res))
                        else:
                            temp_wav_path = None
                            try:
                                import tempfile
                                import base64
                                import subprocess
                                import piper

                                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
```

---

## 4. Sys.Modules-Level Mock Setup

### Content of daemon/tests/conftest.py
```python
import sys
from unittest.mock import MagicMock

# Mock piper and onnxruntime entirely at the import level
# to prevent any real onnxruntime / piper loading or initialization in tests.
sys.modules["piper"] = MagicMock()
sys.modules["onnxruntime"] = MagicMock()
```

---

## 5. UI Elements & Client Code

### "🔊 Ascolta" Button Code
```javascript
                // Add TTS Listen button and audio player
                html += `
                    <div style="margin-top: 15px; display: flex; align-items: center; gap: 10px;">
                        <button onclick="synthesizeSummary()" style="padding: 8px 12px; font-weight: bold; border-radius: 6px; background: #a6e3a1; color: #11111b; border: none; cursor: pointer;">🔊 Ascolta</button>
                        <audio id="tts-audio-player" name="tts-audio-player" controls style="display: none; height: 32px;"></audio>
                    </div>
                `;
```

### Click Handler Code
```javascript
        function synthesizeSummary() {
            if (!lastGeneratedSummary) return;
            if (ws && ws.readyState === WebSocket.OPEN) {
                const toast = document.getElementById("toast-banner");
                toast.innerText = "Sintesi vocale in corso...";
                toast.style.display = "block";
                setTimeout(() => { if (toast.innerText === "Sintesi vocale in corso...") toast.style.display = "none"; }, 3000);

                ws.send(JSON.stringify({
                    action: "text_to_speech",
                    data: { text: lastGeneratedSummary }
                }));
            }
        }
```

### Native Playback Code
```javascript
        function handleTTSAudioMessage(data) {
            const player = document.getElementById("tts-audio-player");
            if (player) {
                player.src = "data:audio/wav;base64," + data.audio_base64;
                player.style.display = "block";
                player.play();

                const toast = document.getElementById("toast-banner");
                toast.innerText = "Sintesi vocale completata. Riproduzione in corso.";
                toast.style.display = "block";
                setTimeout(() => { toast.style.display = "none"; }, 3000);
            }
        }
```

---

## 6. Test Code

### PIPER_VOICE_MODEL_PATH Unset Test
```python
@pytest.mark.asyncio
async def test_text_to_speech_model_path_unset(monkeypatch) -> None:
    """Tests that text_to_speech action returns TTS_NOT_CONFIGURED error when PIPER_VOICE_MODEL_PATH is unset."""
    monkeypatch.delenv("PIPER_VOICE_MODEL_PATH", raising=False)
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_text(
            json.dumps({"action": "text_to_speech", "data": {"text": "Test summary text"}})
        )
        response = websocket.receive_json()
        assert response["type"] == "error"
        assert response["code"] == "TTS_NOT_CONFIGURED"
        assert response["action"] == "text_to_speech"
        assert "Nessun modello vocale" in response["message"]
```
