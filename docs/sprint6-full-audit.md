# Sprint 6 Full Audit Report

This document contains the read-only audit of the changes introduced on this branch.

---

## 0. Files changed overview

Below is the literal list of every file added or modified on this branch:

1. `docs/api-contract.md` (Modified)
2. `server/main.py` (Modified)
3. `server/services/summary_service.py` (Added)
4. `server/tests/test_summary.py` (Added)
5. `widget/index.html` (Modified)
6. `widget/tests/test_subtitles.js` (Modified)
7. `daemon/local_bridge.py` (Modified)
8. `daemon/tests/test_local_bridge.py` (Modified)

---

## 1. Task 23/24 — Widget lesson log + summary rendering

### Lesson Log Accumulation Code
In `widget/index.html`, lesson log entries are accumulated inside `renderData()` and `handleSubtitleMessage()`:

```javascript
        function renderData(data) {
            if (!data) return;
            const out = document.getElementById("output");
            out.innerHTML = "";

            if (data.type === "summary") {
                const text = data.text || data.summary || "";
                lastGeneratedSummary = text;
                const normalizedText = text.replace(/\r\n/g, "\n");
                const paragraphs = normalizedText.split("\n\n");
                let html = "";
                paragraphs.forEach(para => {
                    const trimmed = para.trim();
                    if (trimmed) {
                        html += `<p>${escapeHTML(trimmed)}</p>`;
                    }
                });
                out.innerHTML = html;
            } else if (data.type === "math") {
                lessonLog.push({
                    type: "math",
                    content: `Espressione matematica: ${data.latex}`,
                    timestamp: new Date().toISOString()
                });
...
            } else if (data.type === "concept_map") {
                lessonLog.push({
                    type: "concept_map",
                    content: `Mappa concettuale: ${data.mermaid_code}`,
                    timestamp: new Date().toISOString()
                });
                out.innerHTML = `<pre class="mermaid">${data.mermaid_code}</pre>`;
                mermaid.run();
...
            } else if (data.type === "quiz") {
                lessonLog.push({
                    type: "quiz",
                    content: `Quiz: ${data.questions.map(q => q.question).join("; ")}`,
                    timestamp: new Date().toISOString()
                });
...
```

And in `handleSubtitleMessage`:
```javascript
        function handleSubtitleMessage(data) {
            if (!subtitlesActive) return;

            const text = escapeHTML(data.text);
            const translated = data.translated_text ? escapeHTML(data.translated_text) : "";
            const displayText = translated ? `${text} (${translated})` : text;

            if (data.is_final) {
                finalSubtitles.push(displayText);
                interimSubtitle = null;
                lessonLog.push({
                    type: "subtitle",
                    content: data.translated_text ? `${data.text} (${data.translated_text})` : data.text,
                    timestamp: new Date().toISOString()
                });
            } else {
                interimSubtitle = displayText;
            }

            updateSubtitlesDisplay();
        }
```

- Only is_final:true subtitles are logged, never interim ones: **YES**
- Reuses existing escapeHTML: **YES**

---

### "Riassumi Lezione" Button Handler Code
In `widget/index.html`:

```javascript
        function triggerSummary() {
            if (lessonLog.length === 0) {
                const toast = document.getElementById("toast-banner");
                toast.innerText = "Nessun contenuto da riassumere ancora";
                toast.style.display = "block";
                setTimeout(() => { toast.style.display = "none"; }, 5000);
                return;
            }

            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    action: "generate_summary",
                    data: { lesson_log: lessonLog }
                }));
            }
        }
```

---

### Summary Rendering Code
In `widget/index.html`:

```javascript
            if (data.type === "summary") {
                const text = data.text || data.summary || "";
                lastGeneratedSummary = text;
                const normalizedText = text.replace(/\r\n/g, "\n");
                const paragraphs = normalizedText.split("\n\n");
                let html = "";
                paragraphs.forEach(para => {
                    const trimmed = para.trim();
                    if (trimmed) {
                        html += `<p>${escapeHTML(trimmed)}</p>`;
                    }
                });
                out.innerHTML = html;
```

---

## 2. Task 23/24 — Server summary service (final state only)

### Verbatim Full Contents of `server/services/summary_service.py`

```python
"""
Summary Generation Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles generating a lesson summary based on the provided
    lesson log using LiteLLM. It strictly reuses the same LLM configuration and keys as the other
    services. It formats the lesson log entries, constructs a structured prompt, and queries
    the LLM to return a plain text summary split into paragraphs by \\n\\n.
"""

import logging
import os
import litellm
from typing import Any, Dict, List

logger = logging.getLogger("server_summary_service")

# Ensure required LLM_MODEL environment variable is present at module startup (fail-fast)
LLM_MODEL = os.getenv("LLM_MODEL")
if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL environment variable is not configured. Server startup aborted.")

# Ensure required LLM_API_KEY environment variable is present at module startup (fail-fast)
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY environment variable is not configured. Server startup aborted.")

LLM_API_BASE = os.getenv("LLM_API_BASE")


def generate_summary(lesson_log: List[Dict[str, Any]]) -> str:
    """
    Generates a lesson summary based on the provided lesson log.

    Args:
        lesson_log: A list of dict entries representing the lesson log.

    Returns:
        A string containing the summary, split into paragraphs by \\n\\n.
    """
    logger.info("Generating summary for lesson log with %d entries.", len(lesson_log))

    # Format the lesson log into a human-readable text for the prompt
    formatted_log = []
    for entry in lesson_log:
        entry_type = entry.get("type", "unknown")
        content = entry.get("content", "")
        timestamp = entry.get("timestamp", "")
        formatted_log.append(f"[{timestamp}] Type: {entry_type} | Content: {content}")

    log_text = "\n".join(formatted_log)

    prompt = (
        "Sei un assistente didattico per docenti di scuole italiane. "
        "Genera un riassunto strutturato e chiaro della lezione scolastica basandoti sul seguente registro delle attività svolte durante la lezione (lesson log).\n"
        "Raggruppa e organizza le attività per argomento/tema laddove sensato.\n\n"
        "Il riassunto deve essere scritto in italiano fluente e in formato testo semplice (plain text), "
        "con i paragrafi separati esattamente da una doppia andata a capo (\\n\\n).\n"
        "NON usare markdown, NON usare HTML, e NON inserire blocchi di codice o recinti (code fences come ```).\n"
        "\n"
        "Registro delle Attività:\n"
        f"{log_text}\n"
    )

    # Call LiteLLM completion
    response = litellm.completion(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        messages=[{"role": "user", "content": prompt}]
    )

    summary = response.choices[0].message.content or ""
    return summary.strip()
```

- Uses same LLM_MODEL/LLM_API_KEY/LLM_API_BASE env vars as graph_service.py/quiz_service.py: **YES**

---

### Error Handling around LiteLLM Call inside `server/main.py`

```python
    elif action == "generate_summary":
        data_obj = payload.get("data") or {}
        lesson_log = data_obj.get("lesson_log", [])

        if not lesson_log:
            return {
                "type": "error",
                "code": "EMPTY_LESSON_LOG",
                "action": "generate_summary",
                "message": "Nessun contenuto da riassumere ancora"
            }

        try:
            summary_text = generate_summary(lesson_log)
            return {
                "type": "summary",
                "source": "remote_llm",
                "summary": summary_text
            }
        except Exception as e:
            logger.error("LLM provider or unexpected error during summary generation: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_summary",
                "message": f"Errore del servizio LLM o output non valido: {str(e)}"
            }
```

- On LLM failure, returns INVALID_LLM_OUTPUT instead of 500: **YES**

---

### Rejecting Empty lesson_log code inside `server/main.py`

```python
        if not lesson_log:
            return {
                "type": "error",
                "code": "EMPTY_LESSON_LOG",
                "action": "generate_summary",
                "message": "Nessun contenuto da riassumere ancora"
            }
```

- No dead code/leftover from the rename found: **YES**

---

## 3. Task 25 — Daemon backup

### Session Backup file path on WebSocket connect inside `daemon/local_bridge.py`

```python
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Widget LIM connesso via WebSocket.")

    # Create session backup path under daemon/lesson_backups/<timestamp>.jsonl
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    now_clean = now_iso.replace(":", "-")
    backup_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "lesson_backups"))
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"{now_clean}.jsonl")
```

---

### `send_and_backup` Helper inside `daemon/local_bridge.py`

```python
async def send_and_backup(websocket: WebSocket, message: dict | str, backup_path: str | None) -> None:
    """
    Sends the message over the websocket and, if the message represents valid lesson content,
    appends it as a single JSON line to the session's backup file.
    """
    message_str = message if isinstance(message, str) else json.dumps(message)
    await websocket.send_text(message_str)

    if not backup_path:
        return

    try:
        msg_dict = json.loads(message_str) if isinstance(message, str) else message
    except Exception:
        return

    # Filter out non-content messages (errors, warnings, ping/pong, and non-final subtitles)
    msg_type = msg_dict.get("type")
    if msg_type in ("error", "system_warning", "pong_remote"):
        return

    if msg_type == "subtitle" and not msg_dict.get("is_final", False):
        return

    # Only backup valid lesson content (sympy_math, concept_map, load_3d_model, generate_quiz, generate_summary, and final subtitle)
    backup_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "message": msg_dict
    }

    try:
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        with open(backup_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(backup_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to backup file {backup_path}: {e}")
```

- LOCAL sympy_math success: **YES**
- REMOTE proxy success (concept_map/load_3d_model/generate_quiz/generate_summary): **YES**
- Final subtitle forwarding (is_final:true only): **YES**

- ping/pong: NOT backed up: **YES**
- system_warning: NOT backed up: **YES**
- error messages: NOT backed up: **YES**
- interim (is_final:false) subtitles: NOT backed up: **YES**

---

## 4. Task 26 — PDF export

### CDN Script Tags inside `<head>` in `widget/index.html`

```html
    <!-- html2canvas per PDF Export -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <!-- jsPDF per PDF Export -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
```

---

### PDF Export Button Handler Code (`exportToPDF`) inside `widget/index.html`

```javascript
        async function exportToPDF() {
            if (!window.html2canvas || !window.jspdf) {
                const toast = document.getElementById("toast-banner");
                toast.innerText = "Errore: Impossibile esportare il PDF. Le librerie html2canvas o jsPDF non sono state caricate (connessione CDN assente o bloccata).";
                toast.style.display = "block";
                setTimeout(() => { toast.style.display = "none"; }, 5000);
                return;
            }

            const { jsPDF } = window.jspdf;
            const html2canvas = window.html2canvas;
            const doc = new jsPDF();
            let currentY = 15;

            // Header Title
            doc.setFont("Helvetica", "bold");
            doc.setFontSize(16);
            doc.text("AI LIM Copilot — Report Lezione", 15, currentY);
            currentY += 10;

            // Log lessonStartTime
            doc.setFont("Helvetica", "normal");
            doc.setFontSize(10);
            doc.text(`Inizio Sessione: ${sessionStartTime.toLocaleString('it-IT')}`, 15, currentY);
            currentY += 10;

            // 1. Render the current lessonLog as a simple text section at the top of the PDF.
            doc.setFont("Helvetica", "bold");
            doc.setFontSize(12);
            doc.text("Registro Attività (Lesson Log):", 15, currentY);
            currentY += 6;

            doc.setFont("Helvetica", "normal");
            doc.setFontSize(10);
            if (lessonLog.length === 0) {
                doc.text("Nessuna attività registrata in questa sessione.", 15, currentY);
                currentY += 6;
            } else {
                lessonLog.forEach(entry => {
                    const timeStr = new Date(entry.timestamp).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    const typeStr = entry.type.toUpperCase();
                    const textLine = `[${timeStr}] [${typeStr}] ${entry.content}`;

                    const splitLines = doc.splitTextToSize(textLine, 180);
                    splitLines.forEach(line => {
                        if (currentY > 280) {
                            doc.addPage();
                            currentY = 15;
                        }
                        doc.text(line, 15, currentY);
                        currentY += 5;
                    });
                });
                currentY += 5;
            }

            // 2. If a summary was already generated, include its full text.
            if (lastGeneratedSummary) {
                if (currentY > 250) {
                    doc.addPage();
                    currentY = 15;
                }
                doc.setFont("Helvetica", "bold");
                doc.setFontSize(12);
                doc.text("Sintesi della Lezione:", 15, currentY);
                currentY += 6;

                doc.setFont("Helvetica", "normal");
                doc.setFontSize(10);

                const summaryParagraphs = lastGeneratedSummary.split("\n\n");
                summaryParagraphs.forEach(para => {
                    const splitSummary = doc.splitTextToSize(para.trim(), 180);
                    splitSummary.forEach(line => {
                        if (currentY > 280) {
                            doc.addPage();
                            currentY = 15;
                        }
                        doc.text(line, 15, currentY);
                        currentY += 5;
                    });
                    currentY += 4;
                });
                currentY += 5;
            }

            // 3. Capture #output-container using html2canvas
            const container = document.getElementById("output-container");
            if (container) {
                try {
                    const canvas = await html2canvas(container, {
                        useCORS: true,
                        allowTaint: true,
                        scale: 2
                    });
                    const imgData = canvas.toDataURL("image/png");

                    if (currentY > 180) {
                        doc.addPage();
                        currentY = 15;
                    }

                    doc.setFont("Helvetica", "bold");
                    doc.setFontSize(12);
                    doc.text("Visualizzazione Attuale della Lavagna:", 15, currentY);
                    currentY += 6;

                    const imgWidth = 180;
                    const imgHeight = (canvas.height * imgWidth) / canvas.width;

                    doc.addImage(imgData, "PNG", 15, currentY, imgWidth, imgHeight);
                } catch (e) {
                    console.error("html2canvas capture failed: ", e);
                }
            }

            // Save PDF
            doc.save(formatSessionFilename());
        }
```

---

### Fallback Toast Code on script load failure inside `exportToPDF()`

```javascript
            if (!window.html2canvas || !window.jspdf) {
                const toast = document.getElementById("toast-banner");
                toast.innerText = "Errore: Impossibile esportare il PDF. Le librerie html2canvas o jsPDF non sono state caricate (connessione CDN assente o bloccata).";
                toast.style.display = "block";
                setTimeout(() => { toast.style.display = "none"; }, 5000);
                return;
            }
```
