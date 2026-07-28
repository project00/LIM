# Local Backup & Retention Audit

## 1. Gitignore Status for `daemon/lesson_backups/`

Verbatim section of `.gitignore` listing the local backups and model caching directories:
```gitignore
# LIM-AI local & remote caches and backups
daemon/lesson_backups/
daemon/model_cache/
server/model_cache/
```

- `daemon/lesson_backups/ is gitignored: YES`

---

## 2. Verbatim Test Setup for Cleanup & Backup Isolation

Both cleanup and backup unit/integration tests are strictly isolated inside sandboxed temporary directories created dynamically via `tempfile.mkdtemp()`.

### Verbatim test setups from `daemon/tests/test_local_bridge.py`:

```python
def test_cleanup_old_backups_retention(monkeypatch) -> None:
    """Tests that old backup files are deleted while new ones are retained based on retention settings."""
    import tempfile
    import shutil
    import datetime
    from local_bridge import cleanup_old_backups

    # Create a temporary directory for backups
    tmp_dir = tempfile.mkdtemp()

    # We will patch local_bridge to look at our tmp_dir instead of the default lesson_backups
    monkeypatch.setattr("local_bridge.os.path.dirname", lambda path: tmp_dir)
    # Ensure the backup directory exists internally inside mock
    os.makedirs(os.path.join(tmp_dir, "lesson_backups"), exist_ok=True)
    real_backup_dir = os.path.join(tmp_dir, "lesson_backups")
```

```python
@pytest.mark.asyncio
async def test_send_and_backup_respects_disable_toggle() -> None:
    """Tests that send_and_backup bypasses file writes when settings.disable_local_backup is active."""
    from local_bridge import send_and_backup, settings
    import tempfile
    import shutil

    mock_ws = AsyncMock()
    message = {"type": "math", "source": "local_engine", "latex": "f(x) = x"}

    tmp_dir = tempfile.mkdtemp()
    backup_file = os.path.join(tmp_dir, "test_session.jsonl")
```

- `Tests are isolated to a temp directory: YES`

---

## 3. Reading `disable_local_backup` in `DaemonSettings`

The `disable_local_backup` property is part of the central `DaemonSettings` Pydantic model inside `daemon/settings_api.py`, ensuring consistent parsing, loading, and saving alongside `remote_base_url` and `api_key`.

Verbatim model code from `daemon/settings_api.py`:
```python
class DaemonSettings(BaseModel):
    """Pydantic model representing local daemon configuration settings."""
    remote_base_url: str = "http://192.168.1.100:8000"
    api_key: str = ""
    disable_local_backup: bool = False
```

---

## 4. setup.html Checkbox HTML/JS Wiring

### Verbatim checkbox HTML structure:
```html
  <label style="display: flex; align-items: center; margin-top: 14px; cursor: pointer; user-select: none;">
    <input id="disable-backup" type="checkbox" style="width: auto; margin-top: 0; margin-right: 8px; transform: scale(1.2);">
    Disabilita il backup locale delle lezioni
  </label>
```

### Verbatim JavaScript Wiring (load & save):
```javascript
async function loadConfig() {
  const r = await fetch("/api/config"); const d = await r.json();
  document.getElementById("url").value = d.remote_base_url;
  document.getElementById("key").placeholder = d.api_key_masked || "Nessuna chiave impostata";
  document.getElementById("disable-backup").checked = d.disable_local_backup || false;
}
document.getElementById("save").onclick = async () => {
  const body = {
    remote_base_url: document.getElementById("url").value,
    disable_local_backup: document.getElementById("disable-backup").checked
  };
  const key = document.getElementById("key").value;
  if (key) body.api_key = key;
  await fetch("/api/config", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body) });
  showResult(true, "Impostazioni salvate."); loadConfig();
};
```

---

## 5. Verbatim Reading of `LESSON_BACKUP_RETENTION_DAYS`

Verbatim code from `daemon/local_bridge.py`:
```python
        retention_days = int(os.getenv("LESSON_BACKUP_RETENTION_DAYS", "30"))
```

### Confirmation & Rationale:
A silent fallback default of `30` is intentionally and safely used here because local backup retention is an optimization and storage management task. Standardizing a default limit of 30 days is extremely safe and keeps filesystem space optimized on LIM PCs without disrupting classroom functionalities. This stands in contrast to security-critical environment variables (such as `API_KEY` or `LLM_MODEL`) which must fail-fast and crash immediately to protect access control.
