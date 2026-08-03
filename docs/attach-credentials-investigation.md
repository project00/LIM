# attach_active_credentials() Investigation

## 1. Literal Call Sites and Surrounding Context

The function `attach_active_credentials()` is called in the following two places within `daemon/local_bridge.py`:

### Call Site 1: Inside `TranscriptionSession._capture_loop`
```python
                        # Base64-encode chunk and send to remote server
                        audio_b64 = base64.b64encode(chunk_to_process).decode("utf-8")
                        payload = {
                            "action": "transcribe_audio",
                            "data": {
                                "audio_base64": audio_b64,
                                "sample_rate": 16000,
                                "encoding": "pcm_s16le",
                                "target_language": self.target_language,
                            },
                        }
                        attach_active_credentials(payload)

                        headers = {}
                        if settings.api_key:
                            headers["Authorization"] = f"Bearer {settings.api_key}"
```

### Call Site 2: Inside `websocket_endpoint` for REMOTE targets
```python
                    elif action == "stop_transcription":
                        await transcription_session.stop()

                # --- ROUTE REMOTA ---
                elif target == RouteTarget.REMOTE:
                    attach_active_credentials(payload)
                    try:
                        # Extract the data object safely and resolve custom headers
                        payload_data = payload.get("data") or {}
                        custom_headers = get_outgoing_headers(action, payload_data)
                    except MissingCredentialsError as e:
```

---

## 2. Explanation and Proposed Cleanup

### Why both exist and redundancy explanation
Both `attach_active_credentials()` and `get_outgoing_headers()` exist in the codebase for transmitting user credentials. In practice, they send the same active credentials via two different pathways:
- `attach_active_credentials(payload)` injects active LLM/Sketchfab credentials directly into the JSON POST payload body under a `"credentials"` field.
- `get_outgoing_headers(action, payload_data)` translates the active credentials into standard HTTP Headers (`X-LLM-Model`, `X-LLM-API-Key`, `X-LLM-API-Base`, and `X-Sketchfab-Token`).

Because the server-side endpoints in `server/main.py` extract credentials exclusively from the HTTP Headers (`request.headers.get(...)`), the JSON body-payload-based `"credentials"` field added by `attach_active_credentials()` is redundant and unused.

### Proposed Cleanup Diff
To align with the headers-only credentials propagation specified in the Task 35 design, we will remove `attach_active_credentials()` and its call sites entirely.

```diff
diff --git a/daemon/local_bridge.py b/daemon/local_bridge.py
index b6297ea..e093ca0 100644
--- a/daemon/local_bridge.py
+++ b/daemon/local_bridge.py
@@ -304,26 +304,6 @@ def get_outgoing_headers(action: str, payload_data: dict) -> dict:
     return headers


-def attach_active_credentials(payload: dict) -> None:
-    """Helper to attach active LLM and Sketchfab credentials from settings into the request payload."""
-    action = payload.get("action")
-    active_llm = get_active_llm_credential(action)
-    active_sf = next(
-        (c for c in settings.credentials if c.enabled and c.type == "sketchfab"), None
-    )
-
-    daemon_credentials = {}
-    if active_llm:
-        daemon_credentials["llm"] = {
-            "type": active_llm.type,
-            "model": active_llm.model,
-            "api_key": active_llm.api_key,
-            "api_base": active_llm.api_base,
-        }
-    if active_sf:
-        daemon_credentials["sketchfab"] = {"access_token": active_sf.access_token}
-
-    if daemon_credentials:
-        payload["credentials"] = daemon_credentials
-
-
 class RouteTarget(Enum):
     LOCAL = "local"
     REMOTE = "remote"
@@ -700,7 +680,6 @@ class TranscriptionSession:
                                 "target_language": self.target_language,
                             },
                         }
-                        attach_active_credentials(payload)

                         headers = {}
                         if settings.api_key:
@@ -996,7 +975,6 @@ async def websocket_endpoint(websocket: WebSocket):

                 # --- ROUTE REMOTA ---
                 elif target == RouteTarget.REMOTE:
-                    attach_active_credentials(payload)
                     try:
                         # Extract the data object safely and resolve custom headers
                         payload_data = payload.get("data") or {}
```
