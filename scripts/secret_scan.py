"""Tiny secret scanner used before anything leaves the machine (review packets, commits).

Usage:
    python scripts/secret_scan.py [paths...]      # scan files (default: tracked files)
Exit code 1 if something that looks like a secret is found.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "OpenAI key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    "Anthropic key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"
    ),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "Password assignment": re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"
    ),
}

# Lines that are clearly examples / test fixtures.
ALLOW = re.compile(r"(?i)(example|placeholder|dummy|fake|xxxx|<your|test_)")


def scan_text(text: str, source: str = "<text>") -> list[str]:
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW.search(line):
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                hits.append(f"{source}:{lineno}: possible {name}")
    return hits


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    return [root / p for p in out.splitlines()]


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    files = [Path(a) for a in argv] if argv else tracked_files(root)
    hits: list[str] = []
    for f in files:
        if f.name == "secret_scan.py" or f.suffix in {".png", ".ico", ".exe", ".dmp"}:
            continue
        try:
            hits += scan_text(f.read_text(encoding="utf-8", errors="ignore"), str(f))
        except OSError:
            continue
    for h in hits:
        print(h)
    if hits:
        print(f"{len(hits)} possible secret(s) found.")
        return 1
    print("No secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
