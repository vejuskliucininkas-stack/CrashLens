"""Build CrashLens.exe (single file, double-click to run) and crashlens-cli.exe.

Run from the repository root on Windows:
    pip install -e ".[gui,build]"
    python packaging/build.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMON = ["--noconfirm", "--clean", "--onefile", "--collect-submodules", "crashlens"]
BUILDS = [
    [
        "--windowed",
        "--name",
        "CrashLens",
        "--icon",
        "packaging/crashlens.ico",
        "packaging/gui_entry.py",
    ],
    [
        "--console",
        "--name",
        "crashlens-cli",
        "--icon",
        "packaging/crashlens.ico",
        "--exclude-module",
        "PySide6",
        "packaging/cli_entry.py",
    ],
]


def main() -> int:
    for extra in BUILDS:
        cmd = [sys.executable, "-m", "PyInstaller", *COMMON, *extra]
        print(">", " ".join(cmd), flush=True)
        if subprocess.run(cmd, cwd=ROOT, check=False).returncode != 0:
            return 1
    print("\nBuilt:\n  dist/CrashLens.exe\n  dist/crashlens-cli.exe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
