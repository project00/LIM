# OCR CPU Measurement Audit

This document confirms the process execution and CPU resource profiling characteristics of Tesseract OCR within the LIM-AI Local Daemon environment, verifying that the `pytesseract` library invokes Tesseract as a separate OS subprocess.

---

## 1. Pytesseract Subprocess Invocations (Verbatim Source Code)

From the installed version of `pytesseract` (verified at `/home/jules/.cache/pypoetry/virtualenvs/lim-ai-copilot-daemon-JibB61WF-py3.12/lib/python3.12/site-packages/pytesseract/pytesseract.py`), the `pytesseract.image_to_string()` function processes images by calling the underlying helper `run_tesseract(...)`.

This helper literally uses **`subprocess.Popen`** to run the compiled Tesseract binary, spawning it as a separate OS process with its own PID:

```python
    try:
        proc = subprocess.Popen(cmd_args, **subprocess_args())
    except OSError as e:
        if e.errno != ENOENT:
            raise
        else:
            raise TesseractNotFoundError()
```

Additionally, utility commands such as checking the version or retrieving languages likewise invoke subprocesses:

```python
@run_once
def get_tesseract_version():
    """
    Returns Version object of the Tesseract version
    """
    try:
        output = subprocess.check_output(
            [tesseract_cmd, '--version'],
            stderr=subprocess.STDOUT,
            env=environ,
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        raise TesseractNotFoundError()
```

---

## 2. Explanation of Misleading Process-Only CPU Utilization

Because `pytesseract` delegates all optical character recognition computation to the external `tesseract` binary via `subprocess.Popen`, executing `process.cpu_percent(interval=None)` on the daemon's own PID will **not** register the CPU cycles consumed by the OCR engine. The heavy multi-threaded or single-threaded image processing work takes place within the spawned child process, which completes and terminates quickly.

Consequently, the previous active OCR measurement of **0.17%** was misleadingly low as it represented purely the main Python daemon process waiting on the subprocess's standard streams, missing the actual CPU cost of Tesseract's OCR work.

---

## 3. Corrected Robust Measurement Methodology

To obtain an honest, accurate, and NFR-compliant active resource measurement, we modified `daemon/scripts/benchmark_local.py` to capture the resource utilization of the system as a whole during the active OCR processing window using **`psutil.cpu_percent(interval=None)`** at the system-wide level. This ensures that any and all CPU cycles consumed by spawned child processes (including Tesseract and its internal threads) are fully accounted for.

### Measurement Procedure:
- Sample system-wide CPU% prior to triggering the active OCR window.
- Execute OCR queries sequentially.
- Collect system-wide CPU% changes during the OCR window.
- Present the robust, system-wide CPU utilization.
