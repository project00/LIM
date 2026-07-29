# LIM-AI Copilot Daemon — Packaging Guide

This guide describes how to package the FastAPI Local Bridge Daemon into a standalone directory using PyInstaller.

---

## 1. Environment & Prerequisites

We use Python 3.12 (specifically compatible with `>=3.11,<3.16` to meet PyInstaller and library constraint requirements) and Poetry for dependency management.

### System Dependencies
- **Linux (Ubuntu/Debian):**
  The daemon requires `PortAudio` (for microphone audio capture via PyAudio) and `Tesseract OCR` (for screen-capture OCR) to be installed on the host OS.
  ```bash
  sudo apt-get update
  sudo apt-get install -y portaudio19-dev tesseract-ocr
  ```

- **Windows:**
  Install standard Python 3.12, and ensure Tesseract OCR is installed on the system (and added to the system PATH).

---

## 2. PyAudio/PortAudio Bundling Analysis & Research

Before writing the PyInstaller spec, we researched how PyAudio's PortAudio native library is bundled on both platforms:

- **Windows (Precompiled Wheels):**
  PyAudio distributes precompiled Windows wheels. For Python 3.11+, these wheels statically link PortAudio v19 directly into the compiled C extension module `_portaudio.cpXXX-win_amd64.pyd` (using native compiler toolchains with `--static-link`).
  Consequently, there is **no external `portaudio.dll`** file required or bundled within PyAudio. PyInstaller's static analyzer correctly discovers and bundles the compiled `_portaudio.pyd` extension automatically as a standard compiled Python extension module. No custom `--add-binary` or PyInstaller hooks are required.

- **Linux (Dynamic Linking):**
  On Linux, PyAudio is compiled from source and dynamically links against the host's system PortAudio shared library (`libportaudio.so`).
  PyInstaller is designed **not** to bundle standard host-system-level dynamic libraries (like `libasound.so`, `libportaudio.so`) inside the package because they are expected to be provided by the host environment. Therefore, PortAudio (`portaudio19-dev` or `libportaudio2`) must be installed on the target machine prior to running the daemon executable.

---

## 3. How to Build the Standalone Package

### Linux Build Steps
1. Navigate to the `daemon` directory:
   ```bash
   cd daemon
   ```
2. Build the directory output using PyInstaller with the defined `.spec` file:
   ```bash
   poetry run pyinstaller daemon.spec --clean -y
   ```
3. The build outputs will be generated in `daemon/dist/lim_ai_daemon/`.
4. Run the executable to test:
   ```bash
   ./dist/lim_ai_daemon/lim_ai_daemon
   ```

### Windows Build Steps
> **CRITICAL WARNING:** This Linux build only proves the spec is structurally correct. A real Windows build, run on real Windows hardware with a real microphone connected, is required before this is considered verified — see `LIM-AI-Copilot_Debito_Tecnico.md` / `docs/project-plan.md`. PyInstaller **cannot** cross-compile Windows binaries from a Linux machine.

To package for Windows:
1. Boot a physical or virtual machine running **Windows**.
2. Clone the repository, install Python 3.12, and install the dependencies using Poetry:
   ```powershell
   cd daemon
   poetry install
   ```
3. Run PyInstaller on Windows:
   ```powershell
   poetry run pyinstaller daemon.spec --clean -y
   ```
4. Verify the executable inside `dist\lim_ai_daemon\lim_ai_daemon.exe` runs correctly with a physical microphone connected.

---

## 4. Spec File Design (`daemon.spec`)

Our spec file (`daemon/daemon.spec`) uses `--onedir` mode to produce a clean folder that is easy to inspect and extend (e.g., for bundling Tesseract or other dependencies later).

Key features of the spec:
- **Hidden Imports:** Explicitly collects submodules for dynamic/heavy libraries (`fastapi`, `uvicorn`, `pydantic`, `pydantic_core`, `httpx`, `sympy`, `pyaudio`) to guarantee they are bundled successfully even when imported dynamically.
- **Bundled Datas:** Copies `setup.html` from the source directory to the package root so that the daemon can load and serve it on demand at `/setup`.
