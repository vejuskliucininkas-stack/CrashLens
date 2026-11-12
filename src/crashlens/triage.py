"""Sort findings into: needs attention now / not happened recently / marked as fixed,
and compute a 0-100 health score from what needs attention now.

Two kinds of findings:
* Event findings (crashes, freezes, failed updates...) come from history. They
  can be old, and they can be marked as fixed - they come back automatically if
  the problem happens again after that.
* State findings (drive nearly full, updates old, device broken...) describe the
  PC right now. Every scan re-checks them, so they are never hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from crashlens.core.models import Finding, Severity

RECENT = timedelta(days=7)

EVENT_PREFIXES = (
    "bsod-",
    "unexpected-restart",
    "gpu-tdr",
    "whea-",
    "app-crash-",
    "app-hang-",
    "storage-errors",
    "updates-failing",
    "changes-before-crashes",
)

# Each problem takes away a share of what is left, so many small issues lower the
# score gently while a few serious ones lower it a lot.
WEIGHTS = {
    Severity.CRITICAL: 0.35,
    Severity.HIGH: 0.18,
    Severity.MEDIUM: 0.07,
    Severity.LOW: 0.02,
    Severity.INFO: 0.0,
}


def is_event(f: Finding) -> bool:
    return f.id.startswith(EVENT_PREFIXES)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


@dataclass
class Triage:
    active: list[Finding] = field(default_factory=list)
    old: list[Finding] = field(default_factory=list)
    fixed: list[Finding] = field(default_factory=list)

    @property
    def problems(self) -> list[Finding]:
        """Active findings worth showing to a normal user (not information-only)."""
        return [f for f in self.active if f.severity >= Severity.LOW]

    @property
    def important(self) -> list[Finding]:
        return [f for f in self.active if f.severity >= Severity.MEDIUM]

    @property
    def minor(self) -> list[Finding]:
        return [f for f in self.active if f.severity == Severity.LOW]

    @property
    def score(self) -> int:
        value = 1.0
        for f in self.active:
            value *= 1 - WEIGHTS[f.severity]
        return round(100 * value)


def triage(
    findings: list[Finding], resolved: dict[str, str] | None = None, now: datetime | None = None
) -> Triage:
    now = now or datetime.now(timezone.utc)
    resolved = resolved or {}
    out = Triage()
    for f in findings:
        if not is_event(f) or f.last_seen is None:
            out.active.append(f)
            continue
        marked = parse_iso(resolved.get(f.id))
        if marked is not None and f.last_seen <= marked:
            out.fixed.append(f)
        elif now - f.last_seen > RECENT:
            out.old.append(f)
        else:
            out.active.append(f)
    return out


def score_label(score: int) -> str:
    if score >= 85:
        return "Good"
    if score >= 60:
        return "Fair"
    return "Poor"


def ago(t: datetime | None, now: datetime | None = None) -> str:
    if t is None:
        return ""
    now = now or datetime.now(timezone.utc)
    secs = (now - t).total_seconds()
    if secs < 3600:
        return "less than an hour ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = int(secs // 86400)
    if d == 1:
        return "yesterday"
    return f"{d} days ago"
