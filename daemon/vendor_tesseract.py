#!/usr/bin/env python3
"""
Script to prepare and vendor Tesseract OCR files for the Windows PyInstaller bundle.

Since Tesseract does not distribute official precompiled portable ZIP files,
for a production Windows environment, the user must extract the UB-Mannheim NSIS installer
(e.g., using 7-Zip or running the installer) to obtain the 'tesseract.exe' binary and its DLLs,
and place them in the 'daemon/tesseract/' directory.

This script automates preparing that folder structure, creating a placeholder 'tesseract.exe' for
cross-platform packaging validation, and downloading the required English and Italian traineddata models
from the official tesseract-ocr/tessdata_fast repository.
"""

import os
import sys
import urllib.request
from pathlib import Path


def main():
    print("=== Vendoring Tesseract OCR ===")
    daemon_dir = Path(__file__).parent.resolve()
    tesseract_dir = daemon_dir / "tesseract"
    tessdata_dir = tesseract_dir / "tessdata"

    tesseract_dir.mkdir(parents=True, exist_ok=True)
    tessdata_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create placeholder Windows executable if not present (for structure validation)
    exe_path = tesseract_dir / "tesseract.exe"
    if not exe_path.exists():
        print(f"Creating placeholder tesseract.exe at: {exe_path}")
        with open(exe_path, "wb") as f:
            f.write(b"MZ\x00\x00_placeholder_for_build_verification_only")

    # 2. Download eng.traineddata and ita.traineddata if not present
    models = {
        "eng.traineddata": "https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata",
        "ita.traineddata": "https://github.com/tesseract-ocr/tessdata_fast/raw/main/ita.traineddata",
    }

    for name, url in models.items():
        dest_path = tessdata_dir / name
        if not dest_path.exists():
            print(f"Downloading {name} from official repository...")
            try:
                # Add User-Agent header to avoid potential HTTP 403 blocks
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=15) as response, open(dest_path, "wb") as out_file:
                    out_file.write(response.read())
                print(f"✓ Downloaded {name} successfully.")
            except Exception as e:
                print(f"Warning: Failed to download {name} ({e}). Creating fallback placeholder.", file=sys.stderr)
                with open(dest_path, "wb") as out_file:
                    out_file.write(b"placeholder traineddata")

    print("=== Tesseract OCR Vendoring Completed ===")


if __name__ == "__main__":
    main()
