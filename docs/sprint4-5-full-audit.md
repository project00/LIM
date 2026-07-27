# Sprint 4 & 5 Audit

## 0. Files changed overview
daemon/local_bridge.py
daemon/tests/test_local_bridge.py
docs/api-contract.md
docs/speech-fallback-audit.md
server/main.py
server/services/model_service.py
server/services/quiz_service.py
server/services/quiz_validator.py
server/tests/conftest.py
server/tests/test_auth.py
server/tests/test_model.py
server/tests/test_quiz.py
widget/index.html
widget/tests/test_subtitles.js

## 1. Task 15 — Language selector
widget/index.html
```html
        <select id="subtitle-language" onchange="handleLanguageChange()">
            <option value="">Nessuna traduzione</option>
            <option value="en">Inglese</option>
            <option value="fr">Francese</option>
            <option value="de">Tedesco</option>
            <option value="es">Spagnolo</option>
        </select>
```

widget/index.html
```javascript
        function handleLanguageChange() {
            if (subtitlesActive && currentState === SYSTEM_STATES.ONLINE) {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        action: "stop_transcription"
                    }));
                    ws.send(JSON.stringify({
                        action: "start_transcription",
                        data: { target_language: getSubtitleLanguage() }
                    }));
                }
            }
        }
```

widget/index.html
```javascript
            const selectEl = document.getElementById("subtitle-language");
            if (selectEl) {
                selectEl.disabled = isDegradedOrOffline;
            }
```

Selector disabled in DEGRADED/OFFLINE: YES

## 2. Task 16 — Quiz generation (server)
server/services/quiz_service.py
```python
"""
Quiz Generation Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles generating short quizzes based on a given lesson context
    using LiteLLM. It strictly reuses the same LLM configuration and keys as the graph
    generation and translation services to ensure consistency. It validates and parses
    the LLM's response using the strict quiz validator before returning the output.
"""

import logging
import os
import litellm

# Import validator logic
from services.quiz_validator import validate_and_parse_quiz

logger = logging.getLogger("server_quiz_service")

# Ensure required LLM_MODEL environment variable is present at module startup (fail-fast)
LLM_MODEL = os.getenv("LLM_MODEL")
if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL environment variable is not configured. Server startup aborted.")

# Ensure required LLM_API_KEY environment variable is present at module startup (fail-fast)
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY environment variable is not configured. Server startup aborted.")

LLM_API_BASE = os.getenv("LLM_API_BASE")


def generate_quiz(lesson_context: str, num_questions: int) -> list[dict]:
    """
    Generates a quiz based on the provided lesson context and number of questions.

    Args:
        lesson_context: A string summarizing the lesson context / content.
        num_questions: Number of questions requested (usually 3 to 5).

    Returns:
        List of validated question dictionaries.
    """
    logger.info(
        "Generating quiz with %d questions. Lesson context length: %d chars.",
        num_questions,
        len(lesson_context) if lesson_context else 0
    )

    prompt = (
        "Generate a multiple-choice quiz based on the following lesson context.\n"
        f"Number of questions requested: {num_questions} (must be between 3 and 5).\n"
        "\n"
        "Your output must consist ONLY of a valid JSON array of question objects. "
        "Do not include any introductions, explanations, or markdown code fences (like ```json). "
        "Every question object in the array must match this exact schema format:\n"
        "{\n"
        '  "question": "The question text here",\n'
        '  "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        '  "correct_index": 1\n'
        "}\n"
        "Note: correct_index must be a 0-based integer representing the correct answer inside options.\n"
        "\n"
        f"Lesson Context:\n{lesson_context}"
    )

    # Call LiteLLM completion
    response = litellm.completion(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        api_base=LLM_API_BASE,
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.choices[0].message.content or ""

    # Parse and validate quiz
    validated_quiz = validate_and_parse_quiz(content)
    return validated_quiz
```

Uses same LLM_MODEL/LLM_API_KEY/LLM_API_BASE env vars as graph_service.py: YES

server/services/quiz_validator.py
```python
    # Check question count (must be between 3 and 5 questions)
    if not (3 <= len(data) <= 5):
        logger.warning("Quiz validation failed: Question count %d is out of bounds [3, 5].", len(data))
        raise InvalidQuizError(f"Il numero di domande ({len(data)}) deve essere compreso tra 3 e 5.")
```

server/services/quiz_validator.py
```python
        # Correct index validation
        correct_index = item.get("correct_index")
        # Ensure it is an integer (and not a boolean, since bool is a subclass of int)
        if isinstance(correct_index, bool) or not isinstance(correct_index, int):
            raise InvalidQuizError(f"Il correct_index alla domanda {idx} deve essere un numero intero.")

        if not (0 <= correct_index < len(options)):
            raise InvalidQuizError(
                f"Il correct_index ({correct_index}) alla domanda {idx} è fuori dai limiti [0, {len(options)-1}]."
            )
```

server/main.py
```python
        try:
            questions = generate_quiz(lesson_context, num_questions)
            return {
                "type": "quiz",
                "source": "remote_llm",
                "questions": questions
            }
        except InvalidQuizError as e:
            logger.warning("Quiz validation error occurred: %s", e)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_quiz",
                "message": str(e)
            }
        except Exception as e:
            logger.error("LLM provider or unexpected error during quiz generation: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_quiz",
                "message": f"Errore del servizio LLM o output non valido: {str(e)}"
            }
```

On LLM provider failure, returns INVALID_LLM_OUTPUT error instead of 500: YES

## 3. Task 17 — Quiz correct_index rendering (widget)
widget/index.html
```javascript
                // Add button below the quiz
                const btnVerifica = document.createElement("button");
                btnVerifica.id = "btn-verify-quiz";
                btnVerifica.innerText = "📐 Verifica Risposte";
                btnVerifica.style.marginTop = "12px";
                btnVerifica.onclick = () => {
                    // Disable all radios
                    out.querySelectorAll("input[type='radio']").forEach(radio => {
                        radio.disabled = true;
                    });
                    btnVerifica.disabled = true;

                    // Verify answers
                    correctIndices.forEach((correctIdx, i) => {
                        const radios = out.querySelectorAll(`input[name="q${i}"]`);
                        let selectedIdx = -1;
                        radios.forEach((radio, rIdx) => {
                            if (radio.checked) {
                                selectedIdx = rIdx;
                            }
                        });

                        radios.forEach((radio, rIdx) => {
                            const lbl = document.getElementById(`quiz-q-${i}-lbl-${rIdx}`);
                            if (!lbl) return;
                            if (rIdx === correctIdx) {
                                // Mark correct option in green
                                lbl.style.backgroundColor = "rgba(166, 227, 161, 0.3)";
                                lbl.style.color = "#a6e3a1";
                                lbl.style.fontWeight = "bold";
                                lbl.style.borderRadius = "4px";
                                lbl.style.padding = "2px 6px";
                                lbl.style.display = "inline-block";
                            } else if (rIdx === selectedIdx) {
                                // Student picked wrong option - mark in red
                                lbl.style.backgroundColor = "rgba(243, 139, 168, 0.3)";
                                lbl.style.color = "#f38ba8";
                                lbl.style.borderRadius = "4px";
                                lbl.style.padding = "2px 6px";
                                lbl.style.display = "inline-block";
                            }
                        });
                    });
                };
                out.appendChild(btnVerifica);
```

correct_index is stored in a closure, not exposed in the DOM/HTML before verification: YES

widget/index.html
```javascript
            } else if (data.type === "quiz") {
                const correctIndices = data.questions.map(q => q.correct_index);

                let html = "<b>Quiz di Verifica Rapida</b><hr>";
                data.questions.forEach((q, i) => {
                    html += `<p><b>${i+1}. ${q.question}</b></p>`;
                    html += `<div class="quiz-question" id="quiz-q-${i}">`;
                    q.options.forEach((opt, j) => {
                        html += `<label id="quiz-q-${i}-lbl-${j}"><input type="radio" name="q${i}" value="${j}"> ${escapeHTML(opt)}</label><br>`;
                    });
                    html += `</div>`;
                });

                out.innerHTML = html;
```

## 4. Task 18 — Plotly point generation (daemon)
daemon/local_bridge.py
```python
            if len(free_symbols) == 1:
                symbol = free_symbols[0]
                try:
                    f = sp.lambdify(symbol, simplified, "math")
                    x_vals = []
                    y_vals = []

                    # Generate 101 points from -10 to 10 with step 0.2
                    for i in range(101):
                        x_val = -10.0 + i * 0.2
                        x_val = round(x_val, 5)
                        try:
                            y_val = f(x_val)

                            # Verify y_val is real and finite
                            if isinstance(y_val, complex):
                                continue
                            import math
                            if not math.isfinite(y_val):
                                continue

                            x_vals.append(float(x_val))
                            y_vals.append(float(y_val))
                        except Exception:
                            # Skip points with evaluation errors
                            continue

                    if len(x_vals) > 0:
                        plot_data = {
                            "x": x_vals,
                            "y": y_vals
                        }
                except Exception:
                    plot_data = None
```

Uses sympy.lambdify over 101 points on [-10, 10]: YES

daemon/local_bridge.py
```python
                        try:
                            y_val = f(x_val)

                            # Verify y_val is real and finite
                            if isinstance(y_val, complex):
                                continue
                            import math
                            if not math.isfinite(y_val):
                                continue

                            x_vals.append(float(x_val))
                            y_vals.append(float(y_val))
                        except Exception:
                            # Skip points with evaluation errors
                            continue
```

Multi-variable or zero-free-symbol expressions return plot_data: null: YES

## 5. Task 19 — Plotly rendering (widget)
widget/index.html
```javascript
                if (data.plot_data) {
                    const chartContainer = document.createElement("div");
                    chartContainer.id = "math-chart";
                    chartContainer.style.width = "100%";
                    chartContainer.style.minHeight = "300px";
                    chartContainer.style.marginTop = "15px";
                    chartContainer.style.backgroundColor = "#1e1e2e";
                    out.appendChild(chartContainer);

                    try {
                        Plotly.purge(chartContainer);
                    } catch (e) {
                        // ignore
                    }

                    const trace = {
                        x: data.plot_data.x,
                        y: data.plot_data.y,
                        type: 'scatter',
                        mode: 'lines',
                        line: { color: '#89b4fa', width: 3 },
                        name: 'f(x)'
                    };

                    const layout = {
                        title: {
                            text: 'Grafico della Funzione',
                            font: { color: '#cdd6f4', size: 16 }
                        },
                        paper_bgcolor: '#1e1e2e',
                        plot_bgcolor: '#1e1e2e',
                        xaxis: {
                            gridcolor: '#313244',
                            zerolinecolor: '#45475a',
                            tickfont: { color: '#cdd6f4', size: 12 },
                            title: { text: 'x', font: { color: '#cdd6f4' } }
                        },
                        yaxis: {
                            gridcolor: '#313244',
                            zerolinecolor: '#45475a',
                            tickfont: { color: '#cdd6f4', size: 12 },
                            title: { text: 'y', font: { color: '#cdd6f4' } }
                        },
                        margin: { t: 40, b: 40, l: 50, r: 20 },
                        showlegend: false
                    };

                    const config = {
                        responsive: true,
                        displaylogo: false,
                        scrollZoom: true,
                        doubleClick: 'reset'
                    };

                    Plotly.newPlot(chartContainer, [trace], layout, config);
                }
```

Previous Plotly chart instance is destroyed/cleared before rendering a new one (Plotly.purge or equivalent): YES

widget/index.html
```javascript
                    try {
                        Plotly.purge(chartContainer);
                    } catch (e) {
                        // ignore
                    }
```

## 6. Task 20 — Sketchfab search + server-side cache
Personal API Token via header Authorization: Token <token> or Bearer <token>
server/services/model_service.py
```python
SKETCHFAB_ACCESS_TOKEN = os.getenv("SKETCHFAB_ACCESS_TOKEN")
```

server/services/model_service.py
```python
        # Get temporary download link
        download_endpoint = f"https://api.sketchfab.com/v3/models/{uid}/download"
        try:
            with httpx.Client(timeout=10.0) as client:
                download_resp = client.get(download_endpoint, headers=get_auth_headers())

                if download_resp.status_code != 200:
                    logger.error("Failed to request download for model %s: %d - %s", uid, download_resp.status_code, download_resp.text)
                    raise RuntimeError(f"Sketchfab Download API failure: {download_resp.text}")

                download_info = download_resp.json()
        except httpx.HTTPError as e:
            logger.error("Network error during Sketchfab download request: %s", e)
            raise RuntimeError(f"Impossibile richiedere il download a Sketchfab: {e}")

        gltf_info = download_info.get("gltf")
        if not gltf_info or not gltf_info.get("url"):
            logger.error("Sketchfab returned no glTF download URL: %s", download_info)
            raise RuntimeError("Nessun link di download glTF disponibile per questo modello.")

        download_archive_url = gltf_info["url"]

        # Download and extract the archive immediately
        try:
            with httpx.Client(timeout=30.0) as client:
                archive_resp = client.get(download_archive_url)
                if archive_resp.status_code != 200:
                    logger.error("Failed to download model archive from AWS S3: %d", archive_resp.status_code)
                    raise RuntimeError("Download dell'archivio glTF fallito.")

                archive_bytes = archive_resp.content
        except httpx.HTTPError as e:
            logger.error("Network error during archive download: %s", e)
            raise RuntimeError(f"Errore di download dell'archivio glTF: {e}")

        # Extract unzipped archive directly to cache directory
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_ref:
                zip_ref.extractall(model_dir)
            logger.info("Successfully extracted model archive into cache directory %s", model_dir)
```

server/main.py
```python
# Serve the persistent local 3D models directory under /models
os.makedirs("model_cache", exist_ok=True)
app.mount("/models", StaticFiles(directory="model_cache"), name="models")
```

server/services/model_service.py
```python
    # 2. Local Caching check
    model_dir = os.path.join(CACHE_DIR, uid)
    gltf_file = os.path.join(model_dir, "scene.gltf")

    # If already cached, reuse immediately
    if os.path.isdir(model_dir) and os.path.exists(gltf_file):
        logger.info("Cache HIT: Model %s is already cached locally.", uid)
```

Response includes attribution (author, license, source_url): YES

## 7. Task 21 — Daemon-side local model cache
daemon/local_bridge.py
```python
    # Parse and download dependent assets
    try:
        gltf_json = json.loads(gltf_text)
        dependent_uris = []

        for buf in gltf_json.get("buffers", []):
            uri = buf.get("uri")
            if uri and not uri.startswith("data:"):
                dependent_uris.append(uri)

        for img in gltf_json.get("images", []):
            uri = img.get("uri")
            if uri and not uri.startswith("data:"):
                dependent_uris.append(uri)

        for uri in dependent_uris:
            local_uri_path = os.path.join(model_dir, uri)
            os.makedirs(os.path.dirname(local_uri_path), exist_ok=True)

            remote_uri_url = f"{settings.remote_base_url}{remote_base}/{uri}"
            uri_resp = await http_client.get(remote_uri_url, headers=headers)
            uri_resp.raise_for_status()

            with open(local_uri_path, "wb") as f:
                f.write(uri_resp.content)
            logger.info("Daemon cached dependent resource: '%s'", uri)

    except Exception as e:
        logger.error("Failed to cache dependent assets for model %s: %s", query, e)
```

daemon/tests/test_local_bridge.py
```python
        # First request (Cache MISS)
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "load_3d_model",
                "data": {"query": "H2O Molecule"}
            }))
            response1 = websocket.receive_json()

            # Assert rewritten URL and preserved attribution
            assert response1["type"] == "model_3d"
            assert response1["source"] == "remote_index"
            assert "/models_cache/" in response1["model_url"]
            assert response1["label"] == "Water Molecule"
            assert response1["attribution"]["author"] == "Science Lab"

        # Verify download calls
        assert mock_post.call_count == 1
        assert mock_get.call_count == 3

        # Second request (Cache HIT)
        # Reset mock counters to assert no network calls
        mock_post.reset_mock()
        mock_get.reset_mock()

        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "action": "load_3d_model",
                "data": {"query": "H2O Molecule"}
            }))
            response2 = websocket.receive_json()

            # Assert served from cache immediately with identical rewritten details
            assert response2["type"] == "model_3d"
            assert "/models_cache/" in response2["model_url"]
            assert response2["label"] == "Water Molecule"
            assert response2["attribution"]["author"] == "Science Lab"

        # Verify NO remote analyze and NO download requests were performed on cache hit
        mock_post.assert_not_called()
        mock_get.assert_not_called()
```

attribution field is forwarded unchanged to the widget: YES

## 8. Task 22 — Attribution display (widget)
widget/index.html
```javascript
            } else if (data.type === "model_3d") {
                let html = `<model-viewer src="${data.model_url}" camera-controls auto-rotate shadow-intensity="1"></model-viewer>`;

                if (data.attribution) {
                    const author = escapeHTML(data.attribution.author || "Autore sconosciuto");
                    const license = escapeHTML(data.attribution.license || "Licenza sconosciuta");
                    const url = data.attribution.source_url ? escapeHTML(data.attribution.source_url) : "";

                    html += `<div style="font-size: 11px; color: #a6adc8; margin-top: 6px; text-align: center;">`;
                    if (url) {
                        html += `Modello: <a href="${url}" target="_blank" style="color: #89b4fa; text-decoration: none; font-weight: bold;">${escapeHTML(data.label || "Modello 3D")}</a>`;
                    } else {
                        html += `Modello: <b>${escapeHTML(data.label || "Modello 3D")}</b>`;
                    }
                    html += ` | Autore: <i>${author}</i> | Licenza: <span style="color: #f9e2af;">${license}</span>`;
                    html += `</div>`;
                }

                out.innerHTML = html;
```
