# Task 46-48 Verification Audit

## 1. Credential Pydantic Model (with scope field)
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

## 2. Full body of enforce_mutual_exclusivity()
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

## 3. Full body of get_outgoing_headers() and attach_active_credentials()
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

## 4. Full literal HTML/JS for "Ambito" scope selector added to daemon/setup.html
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
