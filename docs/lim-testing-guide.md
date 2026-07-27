# LIM Real-World Testing Protocol

This document outlines standard physical testing protocols to evaluate usability, visibility, and touchscreen responsiveness on Interactive Whiteboards (Lavagna Interattiva Multimediale - LIM) in a physical classroom environment.

---

## 1. Hardware and Touchscreen Responsiveness

Interactive whiteboards utilize infrared (IR) frames, resistive touch, or capacitive glass. This protocol tests precision and latency.

### Test Protocol 1.1: Single-Finger Drag & Plot Panning
1. Open the LIM-AI Copilot interface on the whiteboard.
2. Request a math expression to display a SymPy plot (e.g. `2*x + 6 - 12`).
3. Touch the chart container with one finger and drag horizontally.
4. **Pass Criteria:**
   - The plot pans smoothly following your finger without jitter or sudden jumps.
   - Panning latency is sub-100ms.
   - Lifting the finger halts panning instantly.

### Test Protocol 1.2: Pinch-to-Zoom (Multi-Touch Validation)
1. Load a single-variable plot or a 3D model.
2. Place two fingers on the interactive canvas.
3. Spread fingers apart to zoom in, and pinch together to zoom out.
4. **Pass Criteria:**
   - On IR-sensor whiteboards, ensure no "ghost touches" or zoom inversion occurs.
   - Dynamic scale updating (Plotly layout scale or `<model-viewer>` camera zoom) tracks finger spacing linearly.

### Test Protocol 1.3: 3D Model Rotation
1. Load a 3D model (e.g. "Water Molecule").
2. Perform a sweeping gesture with a single touch to spin the molecule.
3. Perform a double-finger drag to pan the camera.
4. **Pass Criteria:**
   - Rotating is fluid; frame rate remains above 30 FPS.
   - Panning and zooming gestures do not conflict with each other.

---

## 2. Display, Scaling, and Classroom Visibility

LIM projectors often project at 1080p, 720p, or 4:3 resolutions (e.g. 1024x768). Contrast and readability from a classroom distance are critical.

### Test Protocol 2.1: Classroom Readability & Contrast
1. Display live subtitles at full length on the subtitles bar.
2. Step to the back of the classroom (approx. 6–8 meters away).
3. Evaluate font legibility and contrast against the dark background.
4. **Pass Criteria:**
   - Subtitle text must be easily readable without squinting.
   - The dark slate palette (`#1e1e2e` slate base, `#cdd6f4` text, `#89b4fa` accent) preserves color definition under typical overhead classroom lighting (avoiding glare washed-out effects).

### Test Protocol 2.2: Dyslexia-Friendly (DSA) Mode Verification
1. Activate the **👁️ DSA Mode** button on the toolbar.
2. Step back to the classroom distance (approx. 6–8 meters).
3. **Pass Criteria:**
   - Enhanced character letter-spacing and augmented line-height spacing are visually distinct.
   - Specialized high-legibility styling correctly enhances visual parsing for students with learning difficulties.

### Test Protocol 2.3: Quiz Input Precision on Projector Interfaces
1. Generate a quick quiz.
2. Stand close to the whiteboard and attempt to select multiple options using your fingers.
3. Click the **Verifica Risposte** button.
4. **Pass Criteria:**
   - Radio buttons and their text label bounds are large enough to touch accurately without misclicking adjacent options (Target size > 44x44 pixels).
   - Once verified, correct indices render with green highlights and student mistakes render in red, providing immediately identifiable visual feedback from the back of the room.

---

## 3. Network Latency & Offline Resilience

Evaluating system stability under volatile school Wi-Fi networks.

### Test Protocol 3.1: Graceful Degraded/Offline Local Fallback
1. Activate live subtitles (🎙️ Sottotitoli).
2. Physically disconnect the remote server (or simulate network disruption via Chrome DevTools: Network -> Offline).
3. **Pass Criteria:**
   - The connection status banner transitions from "ONLINE" to "DEGRADED" or "OFFLINE".
   - The translation language dropdown selector is disabled.
   - The browser-side SpeechRecognition instance starts listening immediately via browser microphone access.
   - Spoken words continue to transcribe locally in the subtitles bar (in Italian, untranslated).
   - Reconnecting the network returns the banner to "ONLINE", triggers the `"Sottotitoli: passaggio alla trascrizione cloud"` toast notification, and resumes cloud-based translation seamlessly.
