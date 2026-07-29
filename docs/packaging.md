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
  Install standard Python 3.12, and ensure Tesseract OCR is installed on the system (and added to the system PATH) for development.

---

## 2. Tesseract OCR Windows Portability Research & Findings

For the production Windows distribution, the daemon bundles a portable Tesseract OCR binary and specific language models. We researched redistributable sources:

- **Official Tesseract OCR repository:** Does not build or maintain official precompiled Windows ZIP binaries.
- **De facto community standard (UB-Mannheim Windows Builds):**
  UB-Mannheim provides Windows installers on [their GitHub Wiki page](https://github.com/UB-Mannheim/tesseract/wiki). They do not officially distribute a raw extractable ZIP archive.
- **Portability Extraction / Vendoring Process:**
  A true portable distribution of UB-Mannheim requires a build-time preparation step. You must download their NSIS `.exe` installer (e.g., `tesseract-ocr-w64-setup-v5.3.x.xxxx.exe`) and extract the binaries without running the installer. This can be done by using **7-Zip** (e.g. `7z x tesseract-ocr-w64-setup.exe` on Windows or Linux) or by installing it on a Windows staging machine and copying/zipping the folder.
- **Vendored Location:**
  The extracted binaries (including `tesseract.exe` and its supporting `.dll` files) should be placed in `daemon/tesseract/` on the build machine.
- **Language Models (Tessdata):**
  Only the English (`eng.traineddata`) and Italian (`ita.traineddata`) fast models are bundled inside `daemon/tesseract/tessdata/` to keep the distribution size minimal (Italian schools target). They are downloaded directly from the official [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) repository.

## 3. PyAudio/PortAudio Bundling Analysis & Research

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
> **CRITICAL WARNING:** This Linux build only proves the spec is structurally correct. A real Windows build, run on real Windows hardware with a real microphone connected and real Tesseract Windows binaries, is required before this is considered verified. PyInstaller **cannot** cross-compile Windows binaries from a Linux machine. We cannot and do not verify the actual runtime execution of the bundled Windows `tesseract.exe` binary in this Linux sandbox.

To package for Windows:
1. Boot a physical or virtual machine running **Windows**.
2. Clone the repository, install Python 3.12, and prepare the dependencies:
   ```powershell
   cd daemon
   poetry install
   ```
3. Vendor the real Windows Tesseract binaries:
   - Run `python .\vendor_tesseract.py` to create the folder structure and download English/Italian traineddata files.
   - Replace the placeholder `daemon/tesseract/tesseract.exe` and append any required Tesseract DLL files (e.g. from the UB-Mannheim installation/extraction) to the `daemon/tesseract/` folder.
4. Run PyInstaller on Windows:
   ```powershell
   poetry run pyinstaller daemon.spec --clean -y
   ```
5. Verify the executable inside `dist\lim_ai_daemon\lim_ai_daemon.exe` runs correctly with a physical microphone connected and that screenshot OCR executes successfully.

---

## 5. Dynamic Configuration & Path Selection

In `daemon/local_bridge.py`, we dynamically detect whether the application is running as a packaged bundle:
- **Packaged (Frozen) Mode:** Detected using `getattr(sys, "frozen", False)`. Pytesseract is configured to point directly to the bundled Windows binary: `pytesseract.pytesseract.tesseract_cmd = os.path.join(mei_dir, "tesseract", "tesseract.exe")`.
- **Development/CI Mode:** Pytesseract is left completely untouched so that it defaults to the system-installed Tesseract path (keeping local development and CI workflows 100% clean and unblocked).

---

## 6. Spec File Design (`daemon.spec`)

Our spec file (`daemon/daemon.spec`) uses `--onedir` mode to produce a clean folder that is easy to inspect and extend.

Key features of the spec:
- **Hidden Imports:** Explicitly collects submodules for dynamic/heavy libraries (`fastapi`, `uvicorn`, `pydantic`, `pydantic_core`, `httpx`, `sympy`, `pyaudio`) to guarantee they are bundled successfully even when imported dynamically.
- **Bundled Datas:** Copies `setup.html` and the `tesseract/` directory containing binaries and traineddata models into the distribution folder on build.
