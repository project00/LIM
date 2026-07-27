# API Contract — LIM-AI Copilot

Versione: 0.1 — sincronizzato con `LIM-AI-Copilot_Project-Plan.md` §5.4 e §6.
Ogni modifica a questo contratto va fatta qui **prima** di essere implementata nel codice.

---

## 1. WebSocket — Widget ↔ Demone Locale

Endpoint: `ws://127.0.0.1:5000/ws`

**Richiesta generica dal Widget:**
```json
{ "action": "string", "data": {} }
```

### `sympy_math` (Locale)
```json
// Richiesta
{ "action": "sympy_math", "data": "2*x + 6 - 12" }
// Risposta
{
  "type": "math",
  "source": "local_engine",
  "latex": "f(x) = 2x - 6",
  "plot_data": {
    "x": [-10, -9.8, -9.6, "..."],
    "y": [-26, -25.6, -25.2, "..."]
  }
}
```

### `fast_ocr` (Locale — vedi bug #2, non ancora implementato)
```json
// Richiesta
{ "action": "fast_ocr", "data": { "region": {"x": 0, "y": 0, "width": 1920, "height": 1080} } }
// Risposta
{ "type": "ocr", "source": "local_engine", "text": "testo riconosciuto" }
```

### `concept_map` (Remoto)
```json
// Richiesta
{ "action": "concept_map", "data": { "topic": "apparato circolatorio", "language": "it" } }
// Risposta
{ "type": "concept_map", "source": "remote_llm", "mermaid_code": "graph TD; Cuore-->Arterie;" }
```

### `load_3d_model` (Remoto)
```json
// Richiesta
{ "action": "load_3d_model", "data": { "query": "molecola acqua H2O" } }
// Risposta
{ "type": "model_3d", "source": "remote_index", "model_url": "https://.../h2o.glb", "label": "Molecola d'acqua" }
```

### `generate_quiz` (Remoto)
```json
// Richiesta
{ "action": "generate_quiz", "data": { "lesson_context": "riassunto ultimi 10 minuti", "num_questions": 4 } }
// Risposta
{
  "type": "quiz",
  "source": "remote_llm",
  "questions": [
    { "question": "...", "options": ["A", "B", "C", "D"], "correct_index": 1 }
  ]
}
```
> Il renderer del PoC mostra le opzioni ma non gestisce `correct_index` — da aggiungere lato widget.

### `generate_summary` (Remoto)
```json
// Richiesta
{
  "action": "generate_summary",
  "data": {
    "lesson_log": [
      { "type": "subtitle", "content": "testo trascritto", "timestamp": "2026-07-23T10:00:00.000Z" },
      { "type": "math", "content": "Espressione matematica: f(x) = 2x - 6", "timestamp": "2026-07-23T10:01:00.000Z" }
    ]
  }
}
// Risposta
{
  "type": "summary",
  "source": "remote_llm",
  "summary": "Questo è il riassunto della lezione.\n\nSotto forma di paragrafi separati da doppia andata a capo."
}
```

### Messaggi di sistema
```json
{ "action": "ping_remote" }
{ "type": "pong_remote" }
{ "type": "system_warning", "message": "Server remoto offline. Passaggio a Modalità Locale." }
```

### `error` (da introdurre, vedi bug #7)
```json
{ "type": "error", "code": "PARSE_ERROR", "action": "sympy_math", "message": "Impossibile interpretare l'espressione" }
```

### `Sottotitoli Live & Traduzione` (Remoto)
#### `start_transcription` (Richiesta dal Widget)
Inviato dal Widget per avviare la trascrizione live.
```json
{ "action": "start_transcription", "data": { "target_language": null } }
```
#### `stop_transcription` (Richiesta dal Widget)
Inviato dal Widget per arrestare la trascrizione live.
```json
{ "action": "stop_transcription" }
```
#### `subtitle` (Messaggio in arrivo)
Inviato dal demone/server al Widget con i sottotitoli in tempo reale.
```json
{
  "type": "subtitle",
  "text": "testo trascritto",
  "translated_text": "translated text if requested",
  "is_final": false
}
```
> **`is_final`**: `false` = risultato parziale/interinale (può ancora cambiare) — va mostrato
> come riga temporanea. `true` = segmento consolidato, va accodato in modo permanente,
> non sovrascritto dal prossimo parziale.
>
> **Fallback DEGRADED/OFFLINE**: se demone o server remoto non sono raggiungibili, il Widget
> passa da solo al fallback locale via Web Speech API del browser (`SpeechRecognition`),
> senza traduzione — gestito interamente lato client, nessun messaggio verso il demone.

> **Nota importante:** Quando restituiti tramite l'endpoint REST `POST /api/v1/analyze` (e non tramite WebSocket), i messaggi di errore utilizzano lo stato HTTP **200** con il corpo `{"type": "error", ...}` — non uno stato 4xx. Questo perché il proxy di `local_bridge.py` chiama `response.raise_for_status()` prima di inoltrare la risposta al widget, il che solleverebbe un'eccezione non gestita in caso di stato non-2xx.

### `transcribe_audio` (via `POST /api/v1/analyze`, azione interna demone↔server)

Non è un'azione che il Widget invia mai direttamente — il Demone la usa internamente per
ogni chunk audio catturato via PyAudio (Task 11), per poi tradurre il risultato in un
messaggio push `subtitle` verso il Widget.

```json
// Richiesta (demone -> server)
{
  "action": "transcribe_audio",
  "data": {
    "audio_base64": "...",
    "sample_rate": 16000,
    "encoding": "pcm_s16le",
    "target_language": "en"
  }
}
// Risposta
{
  "type": "transcription",
  "source": "remote_stt",
  "text": "testo trascritto del chunk",
  "translated_text": "translated text or null if no target_language"
}
```
> **Semplificazione deliberata per l'MVP**: ogni chunk (~1s) viene trascritto in blocco,
> non in streaming con ipotesi parziali — quindi il Demone inoltra al Widget ogni risultato
> come `subtitle` con `is_final: true`. Sottotitoli davvero "parola per parola" in tempo
> reale (is_final: false progressivi) richiederebbero streaming ASR continuo, non chunk
> discreti — rimandato a un miglioramento futuro, non necessario per l'obiettivo dello
> sprint (sottotitoli utilizzabili in classe, non trascrizione professionale word-by-word).
---

## 2. REST — Endpoint di Amministrazione (Demone Locale)

Solo su `127.0.0.1:5000`, non esposti in rete. Vedi §5.4 del project-plan per l'implementazione completa.

### `GET /setup`
Serve la pagina HTML statica `setup.html`. Nessun payload.

### `GET /api/config`
```json
// Risposta
{ "remote_base_url": "http://192.168.1.100:8000", "api_key_masked": "••••••1234" }
```

### `POST /api/config`
```json
// Richiesta (api_key omessa/vuota = non modificare la chiave esistente)
{ "remote_base_url": "http://192.168.1.100:8000", "api_key": "opzionale" }
// Risposta
{ "status": "saved" }
```

### `POST /api/test-connection`
Nessun payload — usa la configurazione correntemente salvata.
```json
// Risposta OK
{ "status": "ok", "latency_ms": 123 }
// Risposta errore
{ "status": "error", "latency_ms": null, "message": "Server remoto non raggiungibile" }
```

---

## 3. REST — Demone Locale ↔ Server Remoto

### `POST /api/v1/analyze`
Proxy del payload WebSocket per ogni `action` instradata a `REMOTO` (vedi §7 del project-plan).
```
Headers: Authorization: Bearer <api_key>
Body: stesso payload ricevuto dal Widget, es. { "action": "concept_map", "data": {...} }
```
Risposta: stesso schema del tipo di messaggio corrispondente in §1 (es. `concept_map`, `model_3d`, `quiz`).

### `GET /health`
```json
// Risposta
{ "status": "ok" }
```
