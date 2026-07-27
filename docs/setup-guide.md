# Setup and Installation Guide

This guide provides step-by-step instructions for installing and setting up the LIM-AI Copilot development environment, configuring environment variables, installing system-level dependencies, and launching the application services.

---

## Prerequisites

Before starting, ensure you have the following installed on your host machine:

- **Python 3.11 or Python 3.12**
- **Node.js** (v18+) and **npm**
- **Poetry** (Python dependency manager)
- **PortAudio** development headers (required for `PyAudio` audio capture)
- **Tesseract OCR** (required for screenshot-to-text processing)

### Installing System Dependencies (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y portaudio19-dev tesseract-ocr
```

### Installing System Dependencies (macOS)

```bash
brew install portaudio tesseract
```

---

## 1. Repository Layout

The codebase is organized into three main directories:
- `server/`: Remote cloud service handles heavy processing (AI-based quiz generation, translation, Sketchfab 3D model search/caching, concept mapping).
- `daemon/`: Local bridge service running on the school PC connects hardware (capturing microphone, screen OCR, offline SymPy plot calculation, and proxying to the remote server).
- `widget/`: The interactive HTML5 web frontend displayed on the LIM interactive whiteboard.

---

## 2. Server Installation & Configuration

### Step 1: Install Python Dependencies
Navigate to the `server/` directory and install the packages using Poetry:

```bash
cd server
poetry install
```

### Step 2: Configure Environment Variables
Create a `.env` file inside the `server/` directory or set them in your environment. Refer to `.env.example`:

```env
# Shared API key token for authenticating daemon-to-server requests
API_KEY=your-shared-secret-api-key

# LiteLLM Configuration (Concept Maps, Translation, Quiz Generation)
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=your-openai-or-litellm-compatible-api-key
LLM_API_BASE=https://api.openai.com/v1   # Optional custom API base

# Sketchfab Download API Configuration (3D Models)
SKETCHFAB_ACCESS_TOKEN=your-sketchfab-api-personal-token
```

### Step 3: Launch the Server
Start the Uvicorn web server in development reload mode:

```bash
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
The server will start and be available at `http://localhost:8000`.

---

## 3. Daemon (Local Bridge) Installation & Configuration

### Step 1: Install Python Dependencies
Navigate to the `daemon/` directory and install the packages using Poetry:

```bash
cd daemon
poetry install
```

### Step 2: Configure Settings
Configure environmental variables for the local bridge daemon. You can use standard environment variables or a `.env` file in the `daemon/` directory:

```env
# Shared secret token matching the remote server
API_KEY=your-shared-secret-api-key

# Remote server URL endpoints
REMOTE_BASE_URL=http://localhost:8000
```

### Step 3: Launch the Daemon
Start the local daemon service:

```bash
poetry run python local_bridge.py
```
The daemon runs a WebSocket server on `ws://localhost:8765` for widget communication.

---

## 4. Frontend Widget Setup

The frontend widget is a zero-build client built with vanilla HTML5, CSS, and JS.

### Launching the Widget Locally
You can open `widget/index.html` directly in any modern browser, or host it using a simple HTTP server:

```bash
cd widget
npx serve .
```
Access the widget dashboard in your browser at `http://localhost:3000`.

---

## 5. Running the Tests

To verify that the installation has succeeded and all units are functional:

### Running Server Tests
```bash
cd server
poetry run pytest
```

### Running Daemon Tests
```bash
cd daemon
poetry run pytest
```

### Running Widget Frontend Tests
```bash
node widget/tests/test_subtitles.js
```
