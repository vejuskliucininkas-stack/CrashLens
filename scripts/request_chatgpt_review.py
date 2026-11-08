"""Optional: send a review packet to ChatGPT through the OpenAI API and save the answer.

This lets reviews run without copy-pasting. It is entirely optional - pasting the
packet into ChatGPT by hand works the same way.

Requirements (on YOUR computer, never committed):
    set OPENAI_API_KEY=...        (Windows: setx OPENAI_API_KEY "..." then reopen terminal)
    set OPENAI_MODEL=...          the model name you want to use (no default is assumed)

Usage:
    python scripts/request_chatgpt_review.py review/packets/packet-abc1234.md

The answer is saved to review/reviews/ with a header recording the model and the
API response id, so it is always clear that a real review was received.
The API key is read from the environment only; it is never printed or written.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://api.openai.com/v1/chat/completions"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", "").strip()
    if not key:
        print("OPENAI_API_KEY is not set. Paste the packet into ChatGPT by hand instead.")
        return 2
    if not model:
        print("OPENAI_MODEL is not set. Choose the model you want to use.")
        return 2
    packets = [Path(a) for a in argv]
    text = "\n\n".join(p.read_text(encoding="utf-8") for p in packets)
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": text}]}).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310 - fixed https URL
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"The API returned an error: HTTP {exc.code}. Nothing was saved.")
        return 1
    except urllib.error.URLError as exc:
        print(f"Could not reach the API: {exc.reason}. Nothing was saved.")
        return 1
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("Unexpected API response. Nothing was saved.")
        return 1
    stamp = datetime.now(timezone.utc)
    head = packets[0].stem.replace("packet-", "").split("-part")[0]
    out = ROOT / "review" / "reviews" / f"{stamp:%Y-%m-%d}-{head}-api.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = (
        "<!-- Source: OpenAI API | model: {m} | response id: {rid} | received: {t} -->\n\n"
    ).format(m=data.get("model", model), rid=data.get("id", "?"), t=stamp.isoformat())
    out.write_text(meta + answer, encoding="utf-8")
    print(f"Saved review: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
