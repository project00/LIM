# Task 34 UI Verification Audit

This document lists the verbatim code for Task 34's Credential Pydantic model, GET/POST/PATCH/DELETE endpoints, and setup HTML interface.

---

## 1. Verbatim Credential Pydantic Model from daemon/settings_api.py

```python
class Credential(BaseModel):
    """Pydantic model representing LLM or Sketchfab provider credentials."""
    id: str
    name: str
    type: Literal["llm_cloud", "llm_ollama", "sketchfab"]
    enabled: bool = False
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    access_token: str | None = None
```

---

## 2. Verbatim GET/POST/PATCH/DELETE Endpoint Implementations

### GET /api/credentials
```python
@router.get("/api/credentials")
async def list_credentials() -> list[dict]:
    logger.info("Listing credentials.")
    result = []
    for cred in settings.credentials:
        result.append({
            "id": cred.id,
            "name": cred.name,
            "type": cred.type,
            "enabled": cred.enabled,
            "model": cred.model,
            "api_key_masked": mask_key(cred.api_key),
            "api_base": cred.api_base,
            "access_token_masked": mask_key(cred.access_token)
        })
    return result
```

### POST /api/credentials
```python
@router.post("/api/credentials")
async def add_credential(payload: CredentialCreate) -> dict:
    logger.info("Creating a new credential.")
    new_id = str(uuid.uuid4())
    cred = Credential(
        id=new_id,
        name=payload.name,
        type=payload.type,
        enabled=payload.enabled,
        model=payload.model,
        api_key=payload.api_key,
        api_base=payload.api_base,
        access_token=payload.access_token
    )
    if cred.enabled:
        enforce_mutual_exclusivity(cred)
    settings.credentials.append(cred)
    save_settings(settings)
    return {"status": "created", "id": new_id}
```

### PATCH /api/credentials/{id}
```python
@router.patch("/api/credentials/{id}")
async def toggle_credential(id: str, payload: CredentialToggle) -> dict:
    logger.info("Patching credential %s.", id)
    target = None
    for c in settings.credentials:
        if c.id == id:
            target = c
            break
    if not target:
        return {"status": "error", "message": "Credential not found"}
    target.enabled = payload.enabled
    if target.enabled:
        enforce_mutual_exclusivity(target)
    save_settings(settings)
    return {"status": "updated"}
```

### DELETE /api/credentials/{id}
```python
@router.delete("/api/credentials/{id}")
async def delete_credential(id: str) -> dict:
    logger.info("Deleting credential %s.", id)
    settings.credentials = [c for c in settings.credentials if c.id != id]
    save_settings(settings)
    return {"status": "deleted"}
```

---

## 3. Verbatim HTML for the "Credenziali" section in daemon/setup.html

```html
  <!-- Credentials Management System -->
  <h2 class="section-title">🔑 Gestione Credenziali</h2>
  <table id="credentials-table">
    <thead>
      <tr>
        <th>Nome</th>
        <th>Tipo</th>
        <th>Valore</th>
        <th>Abilitato</th>
        <th></th>
      </tr>
    </thead>
    <tbody id="credentials-list">
      <!-- Dynamically populated -->
    </tbody>
  </table>

  <div class="add-form">
    <h3>+ Aggiungi Credenziale</h3>
    <label>Nome Credenziale
      <input id="cred-name" placeholder="es. OpenAI Scuola / Ollama locale" required>
    </label>
    <label>Tipo
      <select id="cred-type" style="width:100%; box-sizing:border-box; padding:8px; margin-top:4px; border-radius:6px; border:1px solid #45475a; background:#181825; color:#cdd6f4;">
        <option value="llm_cloud">LLM Cloud (OpenAI)</option>
        <option value="llm_ollama">LLM Ollama (locale)</option>
        <option value="sketchfab">Sketchfab</option>
      </select>
    </label>

    <div id="fields-llm-cloud" class="cond-field" style="display: block;">
      <label>Modello (es. gpt-4o, gpt-4o-mini)
        <input id="cloud-model" placeholder="gpt-4o-mini">
      </label>
      <label>API Key
        <input id="cloud-key" type="password" placeholder="sk-...">
      </label>
      <label>API Base URL (opzionale)
        <input id="cloud-base" placeholder="https://api.openai.com/v1">
      </label>
    </div>

    <div id="fields-llm-ollama" class="cond-field">
      <label>Modello (es. ollama/llama3.1, ollama/mistral)
        <input id="ollama-model" placeholder="ollama/llama3.1">
      </label>
      <label>API Base URL (es. http://localhost:11434)
        <input id="ollama-base" placeholder="http://localhost:11434">
      </label>
      <p style="font-size: 11px; color: #a6e3a1; margin-top: 4px; margin-bottom: 0;">* nessuna API key necessaria per Ollama</p>
    </div>

    <div id="fields-sketchfab" class="cond-field">
      <label>Access Token (Sketchfab V3)
        <input id="sketchfab-token" type="password" placeholder="token...">
      </label>
    </div>

    <button id="add-cred-btn" class="inline-btn">➕ Aggiungi</button>
  </div>
```

---

## 5. Continuous Session Confirmation

Yes, this branch (`flexible-llm-provider-config`) was built as **ONE continuous session** where multiple task prompts (from dynamic provider config to headers resolution, audio timeouts, action-aware rate limits, silence detection, and error toasts rendering) were pasted and implemented sequentially.
