# LIM-AI Copilot NFR (Non-Functional Requirements) Benchmark Report

This report documents the performance, latency, and resource utilization measurements of the LIM-AI Local Daemon and Remote Server, as specified in the **docs/project-plan.md** (§9 and §14 Sprint 7).

The benchmarks were executed in the sandbox environment on July 30, 2026.

---

## 1. Local Daemon Performance & Resource Usage

These measurements were captured using `psutil` and high-resolution timers (`time.perf_counter()`) under idle and active workloads over **100 iterations** each.

| Metric / Action | NFR Target | Actual (p95 / max / idle) | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **`sympy_math` Latency** | < 50 ms | **27.60 ms** (p95) / 12.30 ms (median) | **PASS** | SymPy symbolic processing is highly efficient. |
| **`fast_ocr` Latency** | < 50 ms | **289.30 ms** (p95) / 148.89 ms (median) | **FAIL** | Tesseract CPU-based OCR on a synthetic image takes ~149ms on average. This runs locally without any cloud dependency, ensuring privacy and robust offline execution. |
| **Daemon RAM (Idle)** | < 150 MB | **87.01 MB** | **PASS** | Well within the lightweight profile target. |
| **Daemon RAM (Active)** | < 150 MB | **87.26 MB** (max active) | **PASS** | Memory usage remains extremely stable during continuous calculations. |
| **Daemon CPU (Idle)** | < 5.00% | **0.00%** | **PASS** | Zero idle overhead when no operations are being performed. |
| **Daemon CPU during OCR/Screenshot** | < 15.00% | **16.63%** (Average system-wide during realistic OCR) | **FAIL** | Measuring the actual target of the NFR—resource consumption during screen captures/OCR—at a realistic teacher usage frequency of once every 2 seconds registers as **16.63%** CPU on average when audited system-wide. This slightly exceeds the `< 15%` target due to the multi-threaded CPU overhead of spawning the Tesseract subprocess. |

---

## 2. Remote Server Pipeline Overhead

To isolate our server's internal pipeline execution overhead (JSON serialization, schema validation, auth checks, and request parsing) from external cloud network and inference latency, the benchmark mocked `litellm.completion` to return instantly.

The overhead was measured using FastAPI's `TestClient` over **100 iterations** per endpoint.

| Action / Endpoint | NFR Target | Isolated Pipeline Overhead (p95) | Real End-to-End Latency | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **`concept_map`** | < 1.5 s (E2E) | **3.98 ms** | *NOT MEASURABLE* | The validation and serialization overhead is virtually instantaneous. |
| **`generate_quiz`** | < 1.5 s (E2E) | **4.30 ms** | *NOT MEASURABLE* | High-speed JSON parsing and quiz schema validation. |
| **`generate_summary`** | < 1.5 s (E2E) | **4.16 ms** | *NOT MEASURABLE* | Minimal overhead for markdown formatting and prompt prep. |

### Critical Notice: Real End-to-End LLM Inference
Because real LLM inference times depend on external provider networks, token lengths, and active API credentials, complete end-to-end measurements against the **< 1.5 second target** are **not measurable** in this sandbox environment.

To run end-to-end performance benchmarks:
1. Provide real `LLM_MODEL` and `LLM_API_KEY` credentials in your environment.
2. Spin up the server: `poetry run uvicorn main:app`.
3. Generate traffic using a load-testing tool (e.g., `locust` or `autocannon`) querying `/api/v1/analyze` with the authorized `Authorization: Bearer <token>` header.

---

## Conclusion & Recommendations

1. **Deterministic Edge Actions (PASS)**: Symbolic math, access control, routing, and data structures are highly performant and meet the latency budgets perfectly.
2. **Local OCR Latency (FAIL/Trade-off)**: Pytesseract on typical school hardware (headless/non-GPU accelerated) will exceed the 50ms mark. However, maintaining local execution is vital for FERPA/GDPR compliance and robust offline functionality.
3. **Resource Profile (PASS/FAIL/Trade-off)**: Both CPU idle and active memory are exceptionally lightweight. While system-wide active CPU utilization during OCR (16.63%) slightly exceeds the 15% threshold due to spawning the external Tesseract binary via subprocesses, the idle and runtime impact is extremely benign, making it highly safe for older classroom hardware.
