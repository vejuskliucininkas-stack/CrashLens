"""Data models shared by every part of CrashLens.

Everything here is plain data (dataclasses) so it can be rendered by the GUI,
the CLI and the report exporters, and serialised to JSON without surprises.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any


class Severity(IntEnum):
    """How urgent a finding is. Ordered so findings can be sorted."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.capitalize()


class CheckStatus(str, Enum):
    """Outcome of running one check."""

    OK = "ok"  # ran, nothing wrong
    ISSUES = "issues"  # ran, produced findings worth attention
    UNAVAILABLE = "unavailable"  # not applicable here (e.g. not Windows, feature missing)
    ERROR = "error"  # the check itself failed


class Category(str, Enum):
    CRASH = "crash"
    APP = "application"
    HARDWARE = "hardware"
    STORAGE = "storage"
    DRIVERS = "drivers"
    SYSTEM = "system"
    SECURITY = "security"
    PERFORMANCE = "performance"
    UPDATES = "updates"


@dataclass(frozen=True)
class Finding:
    """A single thing CrashLens wants to tell the user about."""

    id: str
    title: str
    severity: Severity
    category: Category
    summary: str
    details: str = ""
    evidence: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    repair_ids: tuple[str, ...] = ()
    occurrences: int = 1
    last_seen: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.name
        data["category"] = self.category.value
        data["last_seen"] = self.last_seen.isoformat() if self.last_seen else None
        data["evidence"] = list(self.evidence)
        data["recommendations"] = list(self.recommendations)
        data["repair_ids"] = list(self.repair_ids)
        return data


@dataclass
class CheckResult:
    """Result of one check (a crash analyser or a health check)."""

    check_id: str
    name: str
    status: CheckStatus
    findings: list[Finding] = field(default_factory=list)
    message: str = ""
    duration_s: float = 0.0

    @property
    def worst_severity(self) -> Severity | None:
        return max((f.severity for f in self.findings), default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration_s": round(self.duration_s, 3),
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class SystemInfo:
    os_name: str = "Unknown"
    os_version: str = ""
    os_build: str = ""
    computer_name: str = ""
    user_name: str = ""
    is_admin: bool = False
    is_windows: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanReport:
    """Everything one scan produced."""

    system: SystemInfo
    results: list[CheckResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    demo: bool = False

    @property
    def findings(self) -> list[Finding]:
        items = [f for r in self.results for f in r.findings]
        return sorted(items, key=lambda f: (-int(f.severity), f.title))

    def counts(self) -> dict[Severity, int]:
        out = {s: 0 for s in Severity}
        for f in self.findings:
            out[f.severity] += 1
        return out

    def recommended_repairs(self) -> list[str]:
        seen: list[str] = []
        for f in self.findings:
            for rid in f.repair_ids:
                if rid not in seen:
                    seen.append(rid)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": "CrashLens",
            "demo": self.demo,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "system": self.system.to_dict(),
            "summary": {s.name: n for s, n in self.counts().items()},
            "results": [r.to_dict() for r in self.results],
        }
