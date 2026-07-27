# User Manual and Configuration Guide

This guide describes how teachers and end-users interact with the LIM-AI Copilot dashboard and its intelligent assistant features during live classroom sessions.

---

## 1. Interface Layout Overview

The LIM-AI Copilot interface is optimized for large touchscreens (LIM) and features:
- **Status Indicators (Top Right):** Shows the current connection state of the local daemon (e.g., Connected, Degraded, Offline, Disconnected).
- **Subtitles & Transcriptions Bar (Top Header):** Displays real-time live captions and translations.
- **Interactive Control Bar (Toolbar):** Button actions to trigger interactive tools and configure preferences.
- **Main Output Area (Canvas):** A dark-themed workspace that dynamically renders math formulas, interactive coordinate plots, concept maps, 3D models, and quick quizzes.

---

## 2. Live Subtitles & Dynamic Translation

### How to Use Live Captions
- **Toggle Subtitles:** Click the **🎙️ Sottotitoli** button in the toolbar. This connects to your PC microphone via the local daemon to stream audio.
- **Language Selector:** The dropdown list adjacent to the subtitles button permits dynamic translation. You can choose:
  - **Nessuna traduzione** (Original captured language)
  - **Inglese** (English translation)
  - **Francese** (French translation)
  - **Tedesco** (German translation)
  - **Spagnolo** (Spanish translation)
- **Automatic Restart:** Selecting a new language restarts the active subtitle capture session instantly without requiring a manual toggle off and on.

### Offline / Degraded Fallback Behavior
- If network latency spikes or the server goes offline (**DEGRADED** or **OFFLINE** states):
  - The language dropdown selector becomes disabled.
  - The system automatically activates the browser's native **Web Speech API** for local transcription.
  - No translation takes place during local fallback ("Sottotitoli senza traduzione").
  - On returning online, a temporary notification bar warns: `"Sottotitoli: passaggio alla trascrizione cloud"`.
  - If the browser does not support the Web Speech API, the subtitle bar explicitly shows: `"Sottotitoli non disponibili: browser non supportato"`.

---

## 3. Math SymPy & Plotting Tools

### Generating Math Charts
- Clicking **📐 Math SymPy** prompts the local daemon engine to process algebraic or calculus expressions (e.g., `2*x + 6 - 12` or `1/x`).
- The formula is beautifully rendered in publication-quality **LaTeX** using KaTeX.

### Interactive Plot Controls
- If the expression is a single-variable function (exactly one free variable), a touch-optimized **Plotly Scatter Chart** renders below the formula.
- **Touch Gestures:**
  - **Pinch-to-Zoom / Scroll Wheel:** Magnifies or shrinks the coordinate window.
  - **Click & Drag:** Pans across the x and y axes.
  - **Double-Click:** Resets the chart view to the default scale.
- **Discontinuity Resilience:** Complex results or undefined divisions (like evaluating `1/x` at `x=0`) are skipped automatically without breaking the graph or freezing the interface.

---

## 4. 3D Model Viewer with Caching

### Loading 3D Models
- Click **🧊 3D Model** to search and retrieve glTF 3D objects (e.g., `"Water Molecule H2O"`).
- On first-time fetch (Cache Miss), the remote server retrieves the model from Sketchfab, caches it on the server, and transfers it to the daemon.
- **Local Daemon Cache (Offline Support):** The daemon downloads the parsed `.gltf` and its local references (`.bin` files and textures) into its local cache. Subsequent requests for the same query load immediately from local storage with **zero network latency**, allowing offline teaching.

### Interaction & Touch Controls
- **Rotate:** Drag a single finger (touch) or click-and-drag (mouse) to rotate the object in three dimensions.
- **Pan:** Drag with two fingers (touch) or right-click-and-drag (mouse) to move the camera view.
- **Zoom:** Pinch inward/outward with two fingers (touch) or use the mouse scroll wheel.
- **Attribution Banner:** Creative Commons attribution (Author, License Type, and link to Original Source URL) is displayed immediately beneath the `<model-viewer>` element.

---

## 5. Quick Check Quizzes

### Generating Quizzes
- Clicking **❓ Quiz** generates a multiple-choice check with 3 to 5 questions based on current lesson contexts.

### Quiz Execution & Anti-Cheat Safeguards
- Students pick their options by clicking or touching the circular radio buttons.
- **Verifica Risposte:** Click the **📐 Verifica Risposte** button to instantly grade the submissions.
- **Visual Feedback:**
  - Correct options are marked with a solid **green background** (`#a6e3a1`).
  - Student mistakes are marked with a **red background** (`#f38ba8`).
  - Inputs are immediately locked (disabled) to prevent changing answers after submitting.
- **Inspect Element Safety:** Correct indices are scoped within JS closure execution memory and are never written to HTML attributes, making inspection-cheating impossible.

---

## 6. DSA (Dyslexia-friendly) Mode

- Click the **👁️ DSA Mode** toggle in the toolbar to activate dyslexia-friendly layouts.
- Adjusts letter-spacing, line-heights, and applies high-contrast readability fonts across all active windows and subtitles.
