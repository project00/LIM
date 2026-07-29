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
