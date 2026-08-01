# Task 34 JS Verification Audit

This document lists the verbatim JavaScript logic and mutual exclusivity checks for Task 34.

---

## 1. Verbatim enforce_mutual_exclusivity() Implementation from settings_api.py

```python
def enforce_mutual_exclusivity(active_cred: Credential) -> None:
    if active_cred.type in ("llm_cloud", "llm_ollama"):
        for c in settings.credentials:
            if c.id != active_cred.id and c.type in ("llm_cloud", "llm_ollama"):
                c.enabled = False
    elif active_cred.type == "sketchfab":
        for c in settings.credentials:
            if c.id != active_cred.id and c.type == "sketchfab":
                c.enabled = False
```

### Confirmation

Yes, `enforce_mutual_exclusivity()` scopes exclusivity **correctly**:
- When enabling an entry of type `llm_cloud` or `llm_ollama`, it disables **OTHER** entries of those two types (`llm_cloud` and `llm_ollama`).
- Separately, when enabling a `sketchfab` entry, it disables **only other** `sketchfab` entries.
- It is **not** a blanket "disable everything else regardless of type".

---

## 2. Verbatim Javascript from daemon/setup.html

```javascript
// Toggle conditional fields based on chosen type
const credTypeSelect = document.getElementById("cred-type");
credTypeSelect.onchange = () => {
  const type = credTypeSelect.value;
  document.getElementById("fields-llm-cloud").style.display = type === "llm_cloud" ? "block" : "none";
  document.getElementById("fields-llm-ollama").style.display = type === "llm_ollama" ? "block" : "none";
  document.getElementById("fields-sketchfab").style.display = type === "sketchfab" ? "block" : "none";
};

// Fetch and display all credentials
async function loadCredentials() {
  const tbody = document.getElementById("credentials-list");
  tbody.innerHTML = "";
  try {
    const r = await fetch("/api/credentials");
    const creds = await r.json();
    if (creds.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#89b4fa; padding:10px;">Nessuna credenziale salvata</td></tr>`;
      return;
    }
    creds.forEach(c => {
      const tr = document.createElement("tr");

      // Resolve masked value to display
      let valDisplay = "";
      if (c.type === "llm_cloud") {
        valDisplay = c.api_key_masked || "No key";
      } else if (c.type === "llm_ollama") {
        valDisplay = c.api_base || "No base";
      } else if (c.type === "sketchfab") {
        valDisplay = c.access_token_masked || "No token";
      }

      // Readable type mapping
      let typeLabel = "";
      if (c.type === "llm_cloud") typeLabel = "Cloud LLM";
      else if (c.type === "llm_ollama") typeLabel = "Ollama";
      else if (c.type === "sketchfab") typeLabel = "Sketchfab";

      tr.innerHTML = `
        <td><strong>${c.name}</strong></td>
        <td>${typeLabel}</td>
        <td style="font-family:monospace; font-size:11px;">${valDisplay}</td>
        <td>
          <input type="checkbox" style="width:auto; margin:0;" ${c.enabled ? "checked" : ""} data-id="${c.id}" class="toggle-enabled-cb">
        </td>
        <td style="text-align:center;">
          <button class="action-btn delete-btn" data-id="${c.id}">🗑️</button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    // Wire up checkbox toggles calling PATCH immediately
    document.querySelectorAll(".toggle-enabled-cb").forEach(cb => {
      cb.onchange = async (e) => {
        const id = e.target.getAttribute("data-id");
        const enabled = e.target.checked;
        await fetch(`/api/credentials/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled })
        });
        showResult(true, "Stato credenziale aggiornato.");
        await loadCredentials(); // Refresh to reflect mutual exclusivity modifications
      };
    });

    // Wire up delete buttons
    document.querySelectorAll(".delete-btn").forEach(btn => {
      btn.onclick = async (e) => {
        const id = btn.getAttribute("data-id");
        if (confirm("Sei sicuro di voler eliminare questa credenziale?")) {
          await fetch(`/api/credentials/${id}`, { method: "DELETE" });
          showResult(true, "Credenziale eliminata.");
          await loadCredentials();
        }
      };
    });

  } catch (err) {
    console.error("Failed to load credentials:", err);
  }
}

// Handler for adding a new credential
document.getElementById("add-cred-btn").onclick = async () => {
  const name = document.getElementById("cred-name").value.trim();
  if (!name) {
    alert("Inserisci un nome per la credenziale.");
    return;
  }
  const type = credTypeSelect.value;
  const body = { name, type, enabled: false };

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
