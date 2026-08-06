# Diagnostico Installazione Dipendenze Piper

## 1. Dry-Run Check
Command: `poetry add piper-tts --dry-run`

Literal Output:
```
Using version ^1.6.0 for piper-tts

Updating dependencies
Resolving dependencies...

Package operations: 6 installs, 0 updates, 0 removals, 39 skipped

  - Installing flatbuffers (25.12.19)
  - Installing numpy (2.4.6)
  - Installing protobuf (7.35.1)
  - Installing onnxruntime (1.28.0)
  - Installing pathvalidate (3.3.1)
  - Installing altgraph (0.17.5): Skipped for the following reason: Already installed
  - Installing annotated-types (0.8.0): Skipped for the following reason: Already installed
  - Installing anyio (4.14.2): Skipped for the following reason: Already installed
  - Installing certifi (2026.7.22): Skipped for the following reason: Already installed
  - Installing click (8.4.2): Skipped for the following reason: Already installed
  - Installing fastapi (0.110.3): Skipped for the following reason: Already installed
  - Installing h11 (0.16.0): Skipped for the following reason: Already installed
  - Installing httpcore (1.0.9): Skipped for the following reason: Already installed
  - Installing httptools (0.8.0): Skipped for the following reason: Already installed
  - Installing httpx (0.25.2): Skipped for the following reason: Already installed
  - Installing idna (3.18): Skipped for the following reason: Already installed
  - Installing iniconfig (2.3.0): Skipped for the following reason: Already installed
  - Installing mpmath (1.3.0): Skipped for the following reason: Already installed
  - Installing mss (10.2.0): Skipped for the following reason: Already installed
  - Installing packaging (26.2): Skipped for the following reason: Already installed
  - Installing pillow (10.4.0): Skipped for the following reason: Already installed
  - Installing piper-tts (1.6.0)
  - Installing pluggy (1.6.0): Skipped for the following reason: Already installed
  - Installing psutil (7.2.2): Skipped for the following reason: Already installed
  - Installing pyaudio (0.2.14): Skipped for the following reason: Already installed
  - Installing pydantic (2.13.4): Skipped for the following reason: Already installed
  - Installing pydantic-core (2.46.4): Skipped for the following reason: Already installed
  - Installing pygments (2.20.0): Skipped for the following reason: Already installed
  - Installing pyinstaller (6.21.0): Skipped for the following reason: Already installed
  - Installing pyinstaller-hooks-contrib (2026.6): Skipped for the following reason: Already installed
  - Installing pytesseract (0.3.13): Skipped for the following reason: Already installed
  - Installing pytest (8.4.2): Skipped for the following reason: Already installed
  - Installing pytest-asyncio (0.23.8): Skipped for the following reason: Already installed
  - Installing python-dotenv (1.2.2): Skipped for the following reason: Already installed
  - Installing pyyaml (6.0.3): Skipped for the following reason: Already installed
  - Installing setuptools (83.0.0): Skipped for the following reason: Already installed
  - Installing sniffio (1.3.1): Skipped for the following reason: Already installed
  - Installing starlette (0.37.2): Skipped for the following reason: Already installed
  - Installing sympy (1.14.0): Skipped for the following reason: Already installed
  - Installing typing-extensions (4.16.0): Skipped for the following reason: Already installed
  - Installing typing-inspection (0.4.2): Skipped for the following reason: Already installed
  - Installing uvicorn (0.52.0): Skipped for the following reason: Already installed
  - Installing uvloop (0.22.1): Skipped for the following reason: Already installed
  - Installing watchfiles (1.2.0): Skipped for the following reason: Already installed
  - Installing websockets (17.0.1): Skipped for the following reason: Already installed
```

## 2. Real Installation
Command: `poetry add piper-tts`

Literal Output:
```
Using version ^1.6.0 for piper-tts

Updating dependencies
Resolving dependencies...

Package operations: 6 installs, 0 updates, 0 removals

  - Installing flatbuffers (25.12.19)
  - Installing numpy (2.4.6)
  - Installing protobuf (7.35.1)
  - Installing onnxruntime (1.28.0)
  - Installing pathvalidate (3.3.1)
  - Installing piper-tts (1.6.0)

Writing lock file
```

### Observation
The resolution and installation both completed cleanly and instantly without hanging. All dependencies, including `onnxruntime` (1.28.0), were downloaded as prebuilt binary wheels. No compilation or source builds from source were triggered.

## 3. Fallback Investigation
Since the dry-run and actual installation both resolved cleanly without any hang, no fallback pinning or workarounds were necessary.

## 4. Environment Audit
- **Python Version:** 3.12.13
- **OS:** Linux
- **Architecture:** x86_64
