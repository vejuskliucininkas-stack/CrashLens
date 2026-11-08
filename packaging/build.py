"""Build CrashLens.exe (desktop app) and crashlens-cli.exe (command line) with PyInstaller.

Run from the repository root on Windows:
    pip install -e ".[gui,build]"
    python packaging/build.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BUILDS = [
    ["--windowed", "--name", "CrashLens", "packaging/gui_entry.py"],
    [
        "--console",
        "--name",
        "crashlens-cli",
        "--exclude-module",
        "PySide6",
        "packaging/cli_entry.py",
    ],
]


def main() -> int:
    for extra in BUILDS:
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--collect-submodules",
            "crashlens",
            *extra,
        ]
        print(">", " ".join(cmd))
        if subprocess.run(cmd, cwd=ROOT, check=False).returncode != 0:
            return 1
    print("\nBuilt:\n  dist/CrashLens/CrashLens.exe\n  dist/crashlens-cli/crashlens-cli.exe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
