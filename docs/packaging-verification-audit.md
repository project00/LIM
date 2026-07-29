# Packaging Verification Audit

This audit document verifies the build systems and configurations for both the frontend widget packaging and the backend daemon standalone packaging.

---

## 1. Task 31a Status (Widget .wgt Packaging)

Task 31a was completed successfully in this pull request. The build script `widget/build.py` was created to package the widget into an `AI_LIM.wgt` (ZIP) archive under the ignored `dist/` directory.

### Literal Build Script (`widget/build.py`)
```python
#!/usr/bin/env python3
"""
Build script to package the OpenBoard widget into a .wgt distribution archive.

Following Salvatore "antirez" Sanfilippo's simplicity guidelines, this script
takes a minimal and explicit approach:
1. Validates presence of the required distribution files.
2. Creates the target output directory if missing.
3. Builds the ZIP archive, preserving relative directory structure.
"""

import os
import sys
import zipfile
from pathlib import Path


def main():
    print("=== Starting LIM-AI Copilot Widget Packaging ===")

    # Define paths relative to this script
    script_dir = Path(__file__).parent.resolve()
    repo_root = script_dir.parent.resolve()

    # Target output zip file path
    dist_dir = repo_root / "dist"
    output_wgt = dist_dir / "AI_LIM.wgt"

    # Distribution files that MUST be present and bundled
    required_files = [
        "config.xml",
        "index.html",
        "css/style.css",
        "js/dsa.js",
        "js/export.js",
        "js/renderer.js",
        "js/ws-client.js",
    ]

    # Verify all required files exist before zipping
    missing_files = []
    for rel_path in required_files:
        full_path = script_dir / rel_path
        if not full_path.exists():
            missing_files.append(rel_path)

    if missing_files:
        print(f"Error: Missing required files for distribution: {missing_files}", file=sys.stderr)
        sys.exit(1)

    # Ensure output directory exists
    dist_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating package: {output_wgt}")
    try:
        with zipfile.ZipFile(output_wgt, "w", zipfile.ZIP_DEFLATED) as zipf:
            for rel_path in required_files:
                full_path = script_dir / rel_path
                # Write to zip with rel_path as the archive name
                zipf.write(full_path, arcname=rel_path)
                print(f"  Added: {rel_path}")

        print("=== Packaging completed successfully ===")
        print(f"Output generated at: {output_wgt}")
    except Exception as e:
        print(f"Error while creating ZIP archive: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Verification of Generated `AI_LIM.wgt` Content
We ran `python3 widget/tests/test_build.py` to verify that `dist/AI_LIM.wgt` is a valid ZIP archive containing precisely the expected distribution files:
```
=== Running Widget Build Tests ===
Executing build script: /app/widget/build.py
✓ Build script executed with exit code 0
✓ Output file AI_LIM.wgt exists
✓ Output file is a valid zip archive
Files found in archive: {'config.xml', 'js/renderer.js', 'js/dsa.js', 'css/style.css', 'index.html', 'js/ws-client.js', 'js/export.js'}
✓ Archive contains exactly the expected file list (no missing or extraneous files)
=== ALL BUILD TESTS PASSED ===
```

---

## 2. PyAudio/PortAudio Windows Portability Evidence

To verify the PyAudio/PortAudio Windows static-linking behavior, we consulted PyAudio's official compilation documentation and source structure:

- **Official PyAudio Windows Wheel/Compilation Guidelines:**
  According to PyAudio's official compilation guide (available at [MIT CSAIL PyAudio Compilation Hints](https://people.csail.mit.edu/hubert/pyaudio/compilation.html) and in the source `INSTALL` documentation at `https://github.com/jleb/pyaudio/blob/master/INSTALL`):
  > "The `--static-link` option statically links in the PortAudio library to the PyAudio module, which is probably the most hassle-free way to go on Windows."

  Official precompiled wheels distributed on PyPI for Windows (specifically Python 3.11+) use this `--static-link` compiler option. This compiles the PortAudio native code directly inside the dynamic library extension (`_portaudio.cpXXX-win_amd64.pyd`), meaning **no external `portaudio.dll`** is shipped or needed to run PyAudio on Windows.
- **PyInstaller Hooks Repository (`pyinstaller-hooks-contrib`):**
  We reviewed the `pyinstaller-hooks-contrib` hooks directory list and verified that **no hook exists for `pyaudio`** in standard hooks because PyInstaller's analyzer automatically and successfully extracts standard binary Python extension modules (like `_portaudio.pyd` or `_portaudio.so`) from standard directories without requiring explicit workarounds.

---

## 3. PyAudio/PortAudio Linux Dynamic-Linking Empirical Check

On Linux, PyAudio is dynamically compiled against the host system's `libportaudio` shared object.
We executed `ldd` against the built `_portaudio*.so` extension compiled in this sandbox.

### Verbatim `ldd` Output
```
	linux-vdso.so.1 (0x00007fffc10f3000)
	libportaudio.so.2 => /lib/x86_64-linux-gnu/libportaudio.so.2 (0x00007f4b43e27000)
	libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f4b43c15000)
	libasound.so.2 => /lib/x86_64-linux-gnu/libasound.so.2 (0x00007f4b43b0b000)
	libjack.so.0 => /lib/x86_64-linux-gnu/libjack.so.0 (0x00007f4b43ab8000)
	libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007f4b439cf000)
	/lib64/ld-linux-x86-64.so.2 (0x00007f4b43e70000)
	libdb-5.3.so => /lib/x86_64-linux-gnu/libdb-5.3.so (0x00007f4b4381d000)
	libstdc++.so.6 => /lib/x86_64-linux-gnu/libstdc++.so.6 (0x00007f4b4359f000)
	libgcc_s.so.1 => /lib/x86_64-linux-gnu/libgcc_s.so.1 (0x00007f4b43571000)
```

### PyInstaller Bundling Behavior
Our empirical check confirms that PyInstaller actually **successfully collected and bundled `libportaudio.so.2`** into the distribution's `_internal` directory:
- Path: `daemon/dist/lim_ai_daemon/_internal/libportaudio.so.2`

---

## 4. Standalone Daemon Sanity Build and Runtime Verification

We executed `poetry run pyinstaller daemon.spec --clean -y` inside this sandbox.

### Verbatim PyInstaller Tail Build Log
```
98209 INFO: checking PYZ
98209 INFO: Building PYZ because PYZ-00.toc is non existent
98209 INFO: Building PYZ (ZlibArchive) /app/daemon/build/daemon/PYZ-00.pyz
101947 INFO: Building PYZ (ZlibArchive) /app/daemon/build/daemon/PYZ-00.pyz completed successfully.
102053 INFO: checking PKG
102053 INFO: Building PKG because PKG-00.toc is non existent
102053 INFO: Building PKG (CArchive) lim_ai_daemon.pkg
102259 INFO: Building PKG (CArchive) lim_ai_daemon.pkg completed successfully.
102261 INFO: Bootloader /home/jules/.cache/pypoetry/virtualenvs/lim-ai-copilot-daemon-JibB61WF-py3.12/lib/python3.12/site-packages/PyInstaller/bootloader/Linux-64bit-intel/run
102261 INFO: checking EXE
102261 INFO: Building EXE because EXE-00.toc is non existent
102261 INFO: Building EXE from EXE-00.toc
102261 INFO: Copying bootloader EXE to /app/daemon/build/daemon/lim_ai_daemon
102263 INFO: Appending PKG archive to custom ELF section in EXE
102967 INFO: Building EXE from EXE-00.toc completed successfully.
102970 INFO: checking COLLECT
102970 INFO: Building COLLECT because COLLECT-00.toc is non existent
102970 INFO: Removing dir /app/daemon/dist/lim_ai_daemon
103245 INFO: Building COLLECT COLLECT-00.toc
104872 INFO: Building COLLECT COLLECT-00.toc completed successfully.
104877 INFO: Build complete! The results are available in: /app/daemon/dist
```

### Verbatim Runtime HTTP GET Response (`GET /setup`)
```
HTTP/1.1 200 OK
date: Wed, 29 Jul 2026 14:08:38 GMT
server: uvicorn
content-type: text/html; charset=utf-8
content-length: 2962
last-modified: Wed, 29 Jul 2026 14:08:10 GMT
etag: "cdfb8fe779ca328361f24ee8ebcb7ab8"

<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>LIM-AI Copilot — Impostazioni</title>
<style>
  body { font-family: Arial, sans-serif; background: #1e1e2e; color: #cdd6f4; max-width: 420px; margin: 40px auto; padding: 0 16px; }
  label { display:block; margin-top:14px; font-size:13px; }
  input { width:100%; box-sizing:border-box; padding:8px; margin-top:4px; border-radius:6px; border:1px solid #45475a; background:#181825; color:#cdd6f4; }
  button { margin-top:16px; padding:10px 14px; border:none; border-radius:6px; font-weight:bold; cursor:pointer; }
  #save { background:#89b4fa; color:#11111b; }
  #test { background:#f9e2af; color:#11111b; margin-left:8px; }
  #result { margin-top:12px; font-size:13px; padding:8px; border-radius:6px; display:none; }
  .ok { background:#a6e3a1; color:#11111b; }
  .err { background:#f38ba8; color:#11111b; }
</style>
</head>
<body>
  <h1>⚙️ LIM-AI Copilot — Impostazioni</h1>
  <label>Server Remoto (URL)<input id="url" placeholder="http://192.168.1.100:8000"></label>
  <label>API Key<input id="key" type="password" placeholder="Lascia vuoto per non modificare"></label>
  <label style="display: flex; align-items: center; margin-top: 14px; cursor: pointer; user-select: none;">
    <input id="disable-backup" type="checkbox" style="width: auto; margin-top: 0; margin-right: 8px; transform: scale(1.2);">
    Disabilita il backup locale delle lezioni
  </label>
  <button id="save">💾 Salva</button>
  <button id="test">🔌 Verifica Connessione</button>
  <div id="result"></div>
<script>
async function loadConfig() {
  const r = await fetch("/api/config"); const d = await r.json();
  document.getElementById("url").value = d.remote_base_url;
  document.getElementById("key").placeholder = d.api_key_masked || "Nessuna chiave impostata";
  document.getElementById("disable-backup").checked = d.disable_local_backup || false;
}
document.getElementById("save").onclick = async () => {
  const body = {
    remote_base_url: document.getElementById("url").value,
    disable_local_backup: document.getElementById("disable-backup").checked
  };
  const key = document.getElementById("key").value;
  if (key) body.api_key = key;
  await fetch("/api/config", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body) });
  showResult(true, "Impostazioni salvate."); loadConfig();
};
document.getElementById("test").onclick = async () => {
  showResult(null, "Verifica in corso...");
  const r = await fetch("/api/test-connection", { method: "POST" }); const d = await r.json();
  if (d.status === "ok") showResult(true, `Connesso (${d.latency_ms} ms)`);
  else showResult(false, d.message || "Connessione non riuscita");
};
function showResult(ok, msg) {
  const el = document.getElementById("result");
  el.style.display = "block";
  el.className = ok === null ? "" : (ok ? "ok" : "err");
  el.innerText = msg;
}
loadConfig();
</script>
</body>
</html>
```

---

## 5. Literal PyInstaller Spec (`daemon/daemon.spec`)

```python
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Collect submodules for dynamic/heavy imports to guarantee PyInstaller bundles everything.
# FastAPI, Uvicorn, httpx, SymPy, and Pydantic use a lot of dynamic lookups.
hidden_imports = (
    collect_submodules('fastapi') +
    collect_submodules('uvicorn') +
    collect_submodules('pydantic') +
    collect_submodules('pydantic_core') +
    collect_submodules('httpx') +
    collect_submodules('sympy') +
    collect_submodules('pyaudio') +
    [
        'settings_api',
        'local_bridge',
        'yaml',
        'pytesseract',
        'mss',
        'PIL',
    ]
)

# setup.html must be bundled alongside the executable to be served by the web engine.
# We also bundle the vendored tesseract folder under the tesseract/ subfolder.
datas = [
    ('setup.html', '.'),
    ('tesseract', 'tesseract'),
]

a = Analysis(
    ['local_bridge.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='lim_ai_daemon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='lim_ai_daemon',
)
```

---

## 6. Frozen State Path Selection and Testing Code

### Verbatim `sys.frozen` Detection Block (`daemon/local_bridge.py`)
```python
# Configure Pytesseract command path dynamically when running inside a PyInstaller package (frozen)
if getattr(sys, "frozen", False):
    mei_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    bundled_tesseract_path = os.path.join(mei_dir, "tesseract", "tesseract.exe")
    pytesseract.pytesseract.tesseract_cmd = bundled_tesseract_path
```

### Verbatim Mock Tests (`daemon/tests/test_local_bridge.py`)
```python
def test_tesseract_cmd_path_selection_packaged() -> None:
    """Tests that sys.frozen packaged mode correctly overrides pytesseract's tesseract_cmd path."""
    import importlib
    import sys
    import pytesseract

    # Mock frozen state and _MEIPASS path
    with patch("sys.frozen", True, create=True), \
         patch("sys._MEIPASS", "/mock/mei/dir", create=True):

        # Reload local_bridge to trigger the import-time configuration block
        import local_bridge
        importlib.reload(local_bridge)

        expected_path = os.path.join("/mock/mei/dir", "tesseract", "tesseract.exe")
        assert pytesseract.pytesseract.tesseract_cmd == expected_path


def test_tesseract_cmd_path_selection_development() -> None:
    """Tests that development mode leaves pytesseract's tesseract_cmd untouched."""
    import importlib
    import sys
    import pytesseract

    # Save current value
    original_cmd = pytesseract.pytesseract.tesseract_cmd

    # Mock non-frozen/dev state
    with patch("sys.frozen", False, create=True):
        import local_bridge
        importlib.reload(local_bridge)

        # Should remain the original/system configured cmd (or whatever was there before)
        assert pytesseract.pytesseract.tesseract_cmd == original_cmd
```
