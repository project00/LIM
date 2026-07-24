# Sprint Status and Bug Audit — LIM-AI Copilot

This document provides a comprehensive audit of the LIM-AI Copilot repository against the Sprint backlog (§14) and the PoC bug list (§2) described in `docs/project-plan.md`.

---

## 1. Sprint Backlog Audit (docs/project-plan.md §14)

| Sprint | Story | Status | Evidence/Notes |
|:---|:---|:---|:---|
| **Sprint 0** | **S0.1**: Repository structure (`widget/`, `daemon/`, `server/`, `docs/`) | **Implemented** | Folders exist; files organized cleanly across directories. |
| **Sprint 0** | **S0.2**: Product Backlog prioritization | **Implemented** | Present in `docs/project-plan.md` §14. |
| **Sprint 0** | **S0.3**: Message contract documentation | **Implemented** | Documented in detail inside `docs/api-contract.md`. |
| **Sprint 0** | **S0.4**: Docker Compose and Mock Server environment | **Implemented** | `server/main.py` (FastAPI mock), `server/Dockerfile`, and root `docker-compose.yml` are fully configured. |
| **Sprint 1** | **S1.1**: Fix malformed URLs in `local_bridge.py` and `index.html` | **Implemented** | Stripped all Markdown brackets from URLs. Plain strings used in `daemon/local_bridge.py` and `widget/index.html`. |
| **Sprint 1** | **S1.2**: Minimal settings web page (`/setup`) and APIs | **Implemented** | Implemented `daemon/settings_api.py` and `daemon/setup.html` serving configurations with masked tokens and live connectivity checks. |
| **Sprint 1** | **S1.3**: Show connection state (ONLINE/DEGRADED/OFFLINE) | **Implemented** | Connection state and status badge dynamically updated in `widget/index.html`. |
| **Sprint 1** | **S1.4**: Safe reconnect loop every 3s on close | **Implemented** | Hardened in `widget/index.html` via `onclose` and `reconnectTimeoutId` checks to avoid duplicating socket connections. |
| **Sprint 1** | **S1.5**: Degraded auto-ping health loop every 8s | **Implemented** | Implemented `ping_remote` health checks inside `widget/index.html` when `DEGRADED`, recovering back to `ONLINE` state on `pong_remote`. |
| **Sprint 1** | **S1.6**: Safeguard `ws.onmessage` JSON parsing with try/catch | **Implemented** | Implemented `try/catch` around `JSON.parse` in `widget/index.html` with console error logging and `#toast-banner` notifications. |
| **Sprint 2** | **S2.1**: Simplification of algebraic equations via SymPy | **Implemented** | `LocalEngine.process_math` in `daemon/local_bridge.py` processes math locally using SymPy. |
| **Sprint 2** | **S2.2**: Implement local `fast_ocr` fallback handler | **Implemented** | Handled explicitly as NOT_IMPLEMENTED error shape in `daemon/local_bridge.py` and verified via pytest. |
| **Sprint 2** | **S2.3**: Screen capture and OCR engine (EasyOCR/Tesseract) | **Not started** | Captured screenshots and fast OCR engines are not yet built. |
| **Sprint 2** | **S2.4**: Remove dead SymPy symbol code | **Implemented** | `x = sp.Symbol("x")` removed from `LocalEngine.process_math` in `daemon/local_bridge.py`. |
| **Sprint 2** | **S2.5**: OpenDyslexic DSA mode toggle | **Implemented** | `toggleDSA()` class toggle is implemented in `widget/index.html`. |
| **Sprint 3** | **S3.1**: Server-side FastAPI scaffold | **Implemented** | Fully running at `server/main.py` with GET `/health` and POST `/api/v1/analyze` endpoints. |
| **Sprint 3** | **S3.2**: Request authentication via Bearer token | **Implemented** | Token injection implemented in `daemon/local_bridge.py` and authorization headers validated in `daemon/settings_api.py`. |
| **Sprint 3** | **S3.3**: Prompt Engineering / LLM concept map generation | **Not started** | Complete Vision-LLM services not yet implemented. |
| **Sprint 3** | **S3.4**: Mermaid syntax verification/sanitization | **Not started** | Mermaid output verification is pending. |
| **Sprint 4** | **S4.1 - S4.4**: Live subtitles, audio streaming, translation, Speech synthesis fallback | **Not started** | Audio streaming STT and translation engines are not yet implemented. |
| **Sprint 5** | **S5.1 - S5.5**: Plotly graphs, 3D model loaders, proxy cache, verification quiz, correct index handling | **Partially implemented** | Mock payload rendering (math, concept_map, 3D model, quiz) is present in `widget/index.html`, but actual index/cache/Plotly integrations are pending. |
| **Sprint 6** | **S6.1 - S6.4**: Automatic synthesis, export to PDF, html2canvas/jsPDF, session backups | **Not started** | No post-lesson export or backup systems are started yet. |
| **Sprint 7** | **S7.1 - S7.5**: HTTPS security, load test, accessibility audit, UAT, packaging (.wgt) | **Not started** | CI/CD testing via `pytest` is configured, but HTTPS, deployment packaging, and load tests are pending. |

---

## 2. Bug List Audit (docs/project-plan.md §2)

| Bug # | Description | Status | Evidence/Notes |
|:---|:---|:---|:---|
| **#1** | **URL malformati**: Markdown syntax used for CDN/endpoint links. | **Fully Fixed** | Plain URLs used in `daemon/local_bridge.py` and `widget/index.html`. |
| **#2** | **`fast_ocr` mappato ma non gestito**: LOCAL route missing branch. | **Fully Fixed** | Added `action == "fast_ocr"` LOCAL route branch returning explicit NOT_IMPLEMENTED JSON error payload. |
| **#3** | **Simbolo SymPy inutilizzato**: dead `x = sp.Symbol("x")` variable. | **Fully Fixed** | Removed dead definition from `LocalEngine.process_math`. |
| **#4** | **Configurazione hardcoded**: duplicated server IPs, no env/config file. | **Fully Fixed** | Loaded config dynamically from `config.yaml` using setup web settings. |
| **#5** | **Nessuna autenticazione daemon → server remoto**: authorization headers missing. | **Fully Fixed** | Token injection dynamically added to `daemon/local_bridge.py` requests. |
| **#6** | **`mss` e `PIL.Image` importati ma non usati**: unused local capture imports. | **Still Present** | Imports remain in `daemon/local_bridge.py` as local screen capture is a future task. |
| **#7** | **`ws.onmessage` senza try/catch**: unhandled JSON parsing failures. | **Fully Fixed** | Wrapped `JSON.parse` in try/catch with toast notification banner inside `widget/index.html`. |
| **#8** | **Payload di richiesta statico**: `requestAction()` always sends static math data. | **Still Present** | `requestAction` in `widget/index.html` still hardcodes `"2*x + 6 - 12"` payload. |
| **#9** | **Gestione errori generica nel motore matematico**: general exceptions caught but not logged. | **Partially Fixed** | General exceptions handled with error responses, but detailed server-side logger is not fully implemented. |
