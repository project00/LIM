#!/usr/bin/env python3
"""
Test script for verifying that widget/build.py executes successfully
and generates a valid, correct .wgt package with the expected files.
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path


def test_build():
    print("=== Running Widget Build Tests ===")

    # Resolve paths
    tests_dir = Path(__file__).parent.resolve()
    widget_dir = tests_dir.parent.resolve()
    repo_root = widget_dir.parent.resolve()

    build_script = widget_dir / "build.py"
    output_wgt = repo_root / "dist" / "AI_LIM.wgt"

    # Clean previous build if any to avoid test pollution
    if output_wgt.exists():
        output_wgt.unlink()

    # 1. Run the build script
    print(f"Executing build script: {build_script}")
    result = subprocess.run([sys.executable, str(build_script)], capture_output=True, text=True)

    # Check exit code
    assert result.returncode == 0, f"Build script failed with exit code {result.returncode}.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    print("✓ Build script executed with exit code 0")

    # 2. Verify output file exists
    assert output_wgt.exists(), f"Output package does not exist at expected path: {output_wgt}"
    print("✓ Output file AI_LIM.wgt exists")

    # 3. Verify it is a valid zip archive and assert its exact contents
    assert zipfile.is_zipfile(output_wgt), "The output file is not a valid zip archive."
    print("✓ Output file is a valid zip archive")

    expected_files = {
        "config.xml",
        "index.html",
        "css/style.css",
        "js/dsa.js",
        "js/export.js",
        "js/renderer.js",
        "js/ws-client.js",
    }

    with zipfile.ZipFile(output_wgt, "r") as zipf:
        archive_files = set(zipf.namelist())

    print(f"Files found in archive: {archive_files}")

    # Assert that actual archive files exactly match the expected files list
    assert archive_files == expected_files, (
        f"Archive file list mismatch!\n"
        f"Expected: {sorted(expected_files)}\n"
        f"Found: {sorted(archive_files)}\n"
        f"Extra: {archive_files - expected_files}\n"
        f"Missing: {expected_files - archive_files}"
    )

    print("✓ Archive contains exactly the expected file list (no missing or extraneous files)")
    print("=== ALL BUILD TESTS PASSED ===")


if __name__ == "__main__":
    try:
        test_build()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
