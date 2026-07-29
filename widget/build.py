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
