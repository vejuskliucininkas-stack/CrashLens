import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import review_status  # noqa: E402
from secret_scan import scan_text  # noqa: E402

SAMPLE = """# Review of abc..def
Reviewer: ChatGPT
## Findings

### [R-2026-11-09-1] Approval token logged in full
**Severity:** High
**Type:** Safety
**Where:** src/crashlens/repairs/executor.py - execute

### [R-2026-11-09-2] Missing test for UTF-16
**Severity:** Low
"""


def test_review_status_parses_findings_and_responses(tmp_path, monkeypatch, capsys):
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    (reviews / "2026-11-09-def.md").write_text(SAMPLE, encoding="utf-8")
    responses = tmp_path / "RESPONSES.md"
    responses.write_text("- [R-2026-11-09-1] addressed in 1234567 - prefix only\n")
    monkeypatch.setattr(review_status, "REVIEWS", reviews)
    monkeypatch.setattr(review_status, "RESPONSES", responses)
    findings, resp = review_status.collect()
    assert [(f[0], f[2]) for f in findings] == [
        ("R-2026-11-09-1", "High"),
        ("R-2026-11-09-2", "Low"),
    ]
    assert resp == {"R-2026-11-09-1": "addressed"}
    review_status.main()
    out = capsys.readouterr().out
    assert "1 open" in out and "ADDRESSED" in out and "OPEN" in out


def test_review_status_with_no_reviews(tmp_path, monkeypatch, capsys):
    (tmp_path / "reviews").mkdir()
    monkeypatch.setattr(review_status, "REVIEWS", tmp_path / "reviews")
    review_status.main()
    assert "No reviews received yet" in capsys.readouterr().out


def test_secret_scan_patterns():
    assert scan_text("token: 'ghp_" + "a" * 36 + "'")
    assert scan_text("-----BEGIN " + "PRIVATE KEY-----")
    assert scan_text("AKIA" + "A" * 16)
    assert not scan_text("api_key = os.environ['OPENAI_API_KEY']")
    assert not scan_text("password = '<your password>'")


def test_repository_has_no_secrets():
    files = [p for p in (ROOT / "src").rglob("*.py")] + [p for p in (ROOT / "docs").glob("*.md")]
    hits = []
    for f in files:
        hits += scan_text(f.read_text(encoding="utf-8"), str(f))
    assert hits == []


def test_no_fake_reviews_committed():
    """Only real ChatGPT reviews may live in review/reviews/."""
    reviews = [p for p in (ROOT / "review" / "reviews").glob("*") if p.name != ".gitkeep"]
    responses = (ROOT / "review" / "RESPONSES.md").read_text(encoding="utf-8")
    if not reviews:
        assert "No reviews have been received yet" in responses
