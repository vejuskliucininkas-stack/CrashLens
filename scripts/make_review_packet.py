"""Build a review packet for ChatGPT (or any reviewer) from a range of git commits.

Usage:
    python scripts/make_review_packet.py                 # changes since the last reviewed commit
    python scripts/make_review_packet.py --since abc123  # changes since a given commit
    python scripts/make_review_packet.py --all           # the whole project

The packet is written to review/packets/ as one or more Markdown files small enough
to paste into a chat. It contains instructions, project context, the commit list
and the diff. It is scanned for secrets first and is not created if any are found.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from secret_scan import scan_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "review"
LAST_REVIEWED = REVIEW / "LAST_REVIEWED"
MAX_CHARS = 90_000  # per part; fits comfortably in a chat message or file upload

INSTRUCTIONS = """\
You are reviewing changes to CrashLens, a Windows 11 troubleshooting app written in
Python (PySide6 GUI + CLI). Read review/REVIEW_GUIDE.md rules below, then review the diff.

Focus on, in order:
1. Safety: anything that could delete user files, run a repair without explicit
   approval, weaken Windows security, or leak personal data in reports.
2. Correctness bugs (wrong parsing of Windows data, wrong severity, crashes).
3. Reliability on real Windows 11 (encodings, permissions, timeouts, non-English
   Windows, missing features, slow machines).
4. Design problems and missing tests.
5. Smaller improvements.

Answer ONLY in the format of the template at the end. Use one block per finding.
Be specific: file, function, what is wrong, why, and a concrete fix. If you are
not sure, say so in the finding. Do not invent problems to fill the list.
"""


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--since", help="base commit (exclusive)")
    g.add_argument("--all", action="store_true", help="review the whole project")
    args = p.parse_args(argv)

    head = git("rev-parse", "--short", "HEAD").strip()
    if args.all:
        base = None
    elif args.since:
        base = args.since
    elif LAST_REVIEWED.exists():
        base = LAST_REVIEWED.read_text().strip() or None
    else:
        base = None

    if base:
        log = git("log", "--oneline", f"{base}..HEAD")
        diff = git("diff", f"{base}..HEAD", "--", ".", ":(exclude)review/reviews")
        scope = f"{base}..{head}"
    else:
        log = git("log", "--oneline")
        files = [f for f in git("ls-files").splitlines() if not f.startswith("review/")]
        chunks = []
        for f in files:
            path = ROOT / f
            if path.suffix in {".png", ".ico"}:
                continue
            chunks.append(f"=== {f} ===\n{path.read_text(encoding='utf-8', errors='replace')}")
        diff = "\n\n".join(chunks)
        scope = f"full project at {head}"

    if not diff.strip():
        print("Nothing to review.")
        return 0

    hits = scan_text(diff, "diff")
    if hits:
        print("Refusing to build a packet - possible secrets:")
        print("\n".join(hits))
        return 1

    template = (REVIEW / "REVIEW_TEMPLATE.md").read_text(encoding="utf-8")
    guide = (REVIEW / "REVIEW_GUIDE.md").read_text(encoding="utf-8")
    context = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    header = (
        f"# CrashLens review packet\n\nScope: {scope}\n"
        f"Created: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"## Instructions\n\n{INSTRUCTIONS}\n## Review rules\n\n{guide}\n"
        f"## Architecture\n\n{context}\n## Commits\n\n```\n{log}```\n"
    )
    body = f"## Changes\n\n```diff\n{diff}\n```\n" if base else f"## Source\n\n```\n{diff}\n```\n"
    footer = f"\n## Answer template\n\n{template}"

    out_dir = REVIEW / "packets"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"packet-{head}"
    budget = MAX_CHARS - len(header) - len(footer)
    if len(body) <= budget:
        parts = [header + body + footer]
    else:
        pieces = [body[i : i + MAX_CHARS - 500] for i in range(0, len(body), MAX_CHARS - 500)]
        n = len(pieces)
        parts = [header + f"\n(This packet has {n} parts. Wait for all parts before answering.)\n"]
        for i, piece in enumerate(pieces, 1):
            parts.append(f"# Part {i}/{n}\n\n{piece}\n")
        parts[-1] += footer
    written = []
    for i, text in enumerate(parts, 1):
        name = f"{stem}.md" if len(parts) == 1 else f"{stem}-part{i}.md"
        (out_dir / name).write_text(text, encoding="utf-8")
        written.append(out_dir / name)
    for w in written:
        print(f"Wrote {w.relative_to(ROOT)} ({w.stat().st_size // 1024} KB)")
    print("\nNext: give the packet to ChatGPT, then save its answer as")
    print(f"  review/reviews/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{head}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
