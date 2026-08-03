# Task 46-48 Verification Audit

## 1. Full Literal Credential Pydantic Model (daemon/settings_api.py)

```python
class Credential(BaseModel):
    """Pydantic model representing LLM or Sketchfab provider credentials."""

    id: str
    name: str
    type: Literal["llm_cloud", "llm_ollama", "sketchfab"]
    scope: Literal[
        "global", "concept_map", "quiz_and_summary", "translation", "ocr"
    ] = "global"
    enabled: bool = False
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    access_token: str | None = None
```

---

## 2. Full Literal Body of enforce_mutual_exclusivity() (daemon/settings_api.py)

```python
def enforce_mutual_exclusivity(active_cred: Credential) -> None:
    # Resolve type group
    active_group = (
        "llm" if active_cred.type in ("llm_cloud", "llm_ollama") else "sketchfab"
    )
    active_scope = getattr(active_cred, "scope", "global")

    for c in settings.credentials:
        if c.id == active_cred.id:
            continue
        c_group = "llm" if c.type in ("llm_cloud", "llm_ollama") else "sketchfab"
        c_scope = getattr(c, "scope", "global")
        if c_group == active_group and c_scope == active_scope:
            c.enabled = False
```

---

## 3. Full Literal Body of get_outgoing_headers() and attach_active_credentials() (daemon/local_bridge.py)

These functions implement the scope-then-global fallback lookup logic utilizing `get_active_llm_credential(action)`:

### get_active_llm_credential(action)
```python
def get_active_llm_credential(action: str | None) -> Credential | None:
    """Resolves active LLM credential based on action scope with fallback to global."""
    scope_map = {
        "concept_map": "concept_map",
        "generate_quiz": "quiz_and_summary",
        "generate_summary": "quiz_and_summary",
        "transcribe_audio": "translation",
        "fast_ocr": "ocr",
        "ocr_vision": "ocr",
        "ocr": "ocr",
    }
    target_scope = scope_map.get(action, "global") if action else "global"

    # 1. Search for specifically scoped LLM credential that is enabled
    for c in settings.credentials:
        if (
            c.enabled
            and c.type in ("llm_cloud", "llm_ollama")
            and getattr(c, "scope", "global") == target_scope
        ):
            return c

    # 2. Fallback to 'global' scope
    if target_scope != "global":
        for c in settings.credentials:
            if (
                c.enabled
                and c.type in ("llm_cloud", "llm_ollama")
                and getattr(c, "scope", "global") == "global"
            ):
                return c

    return None
```

### get_outgoing_headers(action, payload_data)
```python
def get_outgoing_headers(action: str, payload_data: dict) -> dict:
    headers = {}

    # 1. LLM action check
    is_llm_action = action in (
        "concept_map",
        "generate_quiz",
        "generate_summary",
        "ocr_vision",
    )
    is_translation_stt = action == "transcribe_audio" and bool(
        payload_data.get("target_language")
    )

    if is_llm_action or is_translation_stt:
        active_llm = get_active_llm_credential(action)
        if active_llm:
            if active_llm.model:
                headers["X-LLM-Model"] = active_llm.model
            if active_llm.type == "llm_cloud" and active_llm.api_key:
                headers["X-LLM-API-Key"] = active_llm.api_key
            if active_llm.api_base:
                headers["X-LLM-API-Base"] = active_llm.api_base
        else:
            if is_llm_action:
                raise MissingCredentialsError(
                    "Nessuna credenziale LLM configurata e abilitata. Vai su /setup per aggiungerne una."
                )

    # 2. Sketchfab action check
    if action == "load_3d_model":
        active_sf = next(
            (c for c in settings.credentials if c.enabled and c.type == "sketchfab"),
            None,
        )
        if active_sf:
            if active_sf.access_token:
                headers["X-Sketchfab-Token"] = active_sf.access_token
        else:
            raise MissingCredentialsError(
                "Nessuna credenziale Sketchfab configurata e abilitata. Vai su /setup per aggiungerne una."
            )

    return headers
```

### attach_active_credentials(payload)
```python
def attach_active_credentials(payload: dict) -> None:
    """Helper to attach active LLM and Sketchfab credentials from settings into the request payload."""
    action = payload.get("action")
    active_llm = get_active_llm_credential(action)
    active_sf = next(
        (c for c in settings.credentials if c.enabled and c.type == "sketchfab"), None
    )

    daemon_credentials = {}
    if active_llm:
        daemon_credentials["llm"] = {
            "type": active_llm.type,
            "model": active_llm.model,
            "api_key": active_llm.api_key,
            "api_base": active_llm.api_base,
        }
    if active_sf:
        daemon_credentials["sketchfab"] = {"access_token": active_sf.access_token}

    if daemon_credentials:
        payload["credentials"] = daemon_credentials
```

---

## 4. Full Literal HTML/JS for "Ambito" Scope Selector (daemon/setup.html)

### HTML Drodown Definition
```html
    <div id="fields-scope" style="display: block;">
      <label>Ambito
        <select id="cred-scope" style="width:100%; box-sizing:border-box; padding:8px; margin-top:4px; border-radius:6px; border:1px solid #45475a; background:#181825; color:#cdd6f4;">
          <option value="global">Generale (fallback)</option>
          <option value="concept_map">Mappe Concettuali</option>
          <option value="quiz_and_summary">Quiz e Sintesi</option>
          <option value="translation">Traduzione</option>
          <option value="ocr">OCR (richiede un modello con supporto immagini, es. llama3.2-vision o gpt-4o)</option>
        </select>
      </label>
    </div>
```

### JS Submission Logic Including Chosen Scope in POST Body
```javascript
// Handler for adding a new credential
document.getElementById("add-cred-btn").onclick = async () => {
  const name = document.getElementById("cred-name").value.trim();
  if (!name) {
    alert("Inserisci un nome per la credenziale.");
    return;
  }
  const type = credTypeSelect.value;
  const body = { name, type, enabled: false };

  if (type === "llm_cloud" || type === "llm_ollama") {
    body.scope = document.getElementById("cred-scope").value;
  }

  if (type === "llm_cloud") {
    body.model = document.getElementById("cloud-model").value.trim() || "gpt-4o-mini";
    body.api_key = document.getElementById("cloud-key").value.trim() || null;
    body.api_base = document.getElementById("cloud-base").value.trim() || null;
  } else if (type === "llm_ollama") {
    body.model = document.getElementById("ollama-model").value.trim() || "ollama/llama3.1";
    body.api_base = document.getElementById("ollama-base").value.trim() || "http://localhost:11434";
  } else if (type === "sketchfab") {
    body.access_token = document.getElementById("sketchfab-token").value.trim() || null;
  }

  try {
    const r = await fetch("/api/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const res = await r.json();
    if (res.status === "created") {
      showResult(true, "Credenziale aggiunta con successo.");
      // Reset inputs
      document.getElementById("cred-name").value = "";
      document.getElementById("cloud-key").value = "";
      document.getElementById("cloud-base").value = "";
      document.getElementById("ollama-base").value = "";
      document.getElementById("sketchfab-token").value = "";
      await loadCredentials();
    } else {
      showResult(false, "Impossibile aggiungere credenziale.");
    }
  } catch (err) {
    showResult(false, `Errore durante il salvataggio: ${err}`);
  }
};
```

---

## 5. Task 48 (Vision-LLM OCR): Research Finding, Message Construction Code & Fallback to Tesseract

### Research Finding for LiteLLM Multimodal Image Format
- **Finding**: LiteLLM supports standard OpenAI API compatible message payloads for multimodal vision completions. The messages list should contain user role with content blocks composed of multiple objects representing types `"text"` and `"image_url"`. The image URL specifies base64 encoded data with a `data:image/png;base64,` or similar data URI format.
- **Reference**: LiteLLM Multimodal Models documentation (https://docs.litellm.ai/docs/providers/openai#multimodal-gpt-4-vision-gpt-4o).

### Literal Code in server/services/ocr_vision_service.py that Builds Message
```python
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
```

### Fallback-to-Tesseract code in daemon/local_bridge.py
```python
                        # 1. OCR Vision Dynamic Routing Exception:
                        # Check for an enabled credential with scope=="ocr". If found, send the image
                        # (base64) to the server action "ocr_vision" instead of running local Tesseract.
                        # If NOT found, or if the vision call fails, fall back to local Tesseract OCR.
                        active_ocr_cred = get_active_llm_credential("fast_ocr")
                        response_text = None
                        source_engine = "local_engine"

                        if capture_error is not None:
                            response_text = f"[OCR non ancora integrato, cattura fallita a causa di restrizioni display/headless: {capture_error}]"
                        elif active_ocr_cred and img is not None:
                            logger.info(
                                "Enabled 'ocr' scope credential found. Attempting remote Vision-LLM OCR..."
                            )
                            try:
                                import io
                                import base64

                                buffered = io.BytesIO()
                                img.save(buffered, format="PNG")
                                image_base64 = base64.b64encode(
                                    buffered.getvalue()
                                ).decode("utf-8")

                                ocr_vision_payload = {
                                    "action": "ocr_vision",
                                    "data": {"image_base64": image_base64},
                                }

                                remote_analyze_url = (
                                    f"{settings.remote_base_url}/api/v1/analyze"
                                )
                                req_headers = (
                                    {"Authorization": f"Bearer {settings.api_key}"}
                                    if settings.api_key
                                    else {}
                                )
                                custom_headers = get_outgoing_headers("ocr_vision", {})
                                req_headers.update(custom_headers)

                                response = await http_client.post(
                                    remote_analyze_url,
                                    json=ocr_vision_payload,
                                    headers=req_headers,
                                )
                                response.raise_for_status()
                                response_json = response.json()

                                if response_json.get("type") == "error":
                                    logger.warning(
                                        "Remote Vision OCR returned error response: %s. Falling back to Tesseract.",
                                        response_json.get("message"),
                                    )
                                else:
                                    response_text = response_json.get("text")
                                    source_engine = "remote_vision_llm"
                                    logger.info(
                                        "Successfully completed remote Vision-LLM OCR."
                                    )
                            except Exception as ve:
                                logger.error(
                                    "Remote Vision OCR call failed due to: %s. Falling back to Tesseract.",
                                    ve,
                                    exc_info=True,
                                )

                        # Fallback to local Tesseract if remote Vision OCR was not used or failed
                        if response_text is None:
                            if img is not None:
                                try:
                                    response_text = pytesseract.image_to_string(
                                        img
                                    ).strip()
                                    logger.info(
                                        "Screen capture successfully processed with Tesseract OCR (fallback/default)."
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to perform local Tesseract OCR: {e}."
                                    )
                                    response_text = f"[OCR local fallback failed: {e}]"
                            else:
                                response_text = "[OCR failed: capture failed]"
```
