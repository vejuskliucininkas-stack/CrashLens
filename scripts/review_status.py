"""Show which review findings are still open.

Reads every review in review/reviews/*.md and matches finding IDs against
review/RESPONSES.md, where each finding gets a line:

    - [R-2026-11-09-1] addressed in abc1234 - <short note>
    - [R-2026-11-09-2] declined - <reason>

Usage:  python scripts/review_status.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "review" / "reviews"
RESPONSES = ROOT / "review" / "RESPONSES.md"

FINDING = re.compile(r"^###\s*\[(R-[\w-]+)\]\s*(.*)$", re.M)
SEVERITY = re.compile(r"(?im)^\*\*Severity:\*\*\s*(\w+)")
RESPONSE = re.compile(r"^-\s*\[(R-[\w-]+)\]\s*(addressed|declined|deferred)\b", re.M | re.I)


def collect() -> tuple[list[tuple[str, str, str, str]], dict[str, str]]:
    findings = []
    for f in sorted(REVIEWS.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        matches = list(FINDING.finditer(text))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sev = SEVERITY.search(text, m.end(), end)
            findings.append((m.group(1), m.group(2).strip(), sev.group(1) if sev else "?", f.name))
    responses = {}
    if RESPONSES.exists():
        for m in RESPONSE.finditer(RESPONSES.read_text(encoding="utf-8")):
            responses[m.group(1)] = m.group(2).lower()
    return findings, responses


def main() -> int:
    findings, responses = collect()
    if not findings:
        print("No reviews received yet (review/reviews/ is empty).")
        return 0
    open_items = [f for f in findings if f[0] not in responses]
    print(
        f"{len(findings)} finding(s) in {len({f[3] for f in findings})} review(s); "
        f"{len(open_items)} open.\n"
    )
    for fid, title, sev, src in findings:
        state = responses.get(fid, "OPEN")
        print(f"{state.upper():10} {sev:9} {fid:22} {title}  ({src})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
