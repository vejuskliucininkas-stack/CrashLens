"""Base class and context shared by all checks."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crashlens.core.models import CheckResult, CheckStatus, Finding
from crashlens.core.runner import CommandRunner, QueryError


class Unavailable(Exception):
    """Raised by a check that cannot run on this system (not an error)."""


@dataclass
class CheckContext:
    runner: CommandRunner
    is_windows: bool
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    lookback_days: int = 30
    minidump_dir: Path | None = None
    demo: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)  # facts for the dashboard
    _cache: dict[str, Any] = field(default_factory=dict, repr=False)

    def cached(self, key: str, producer: Callable[[], Any]) -> Any:
        """Run ``producer`` once per scan; later checks reuse the result (or error)."""
        if key not in self._cache:
            try:
                self._cache[key] = ("ok", producer())
            except Exception as exc:
                self._cache[key] = ("err", exc)
        state, value = self._cache[key]
        if state == "err":
            raise value
        return value


class Check(ABC):
    id: str = "check"
    name: str = "Check"
    windows_only: bool = True

    def run(self, ctx: CheckContext) -> CheckResult:
        start = time.monotonic()
        try:
            if self.windows_only and not ctx.is_windows:
                raise Unavailable("Only available on Windows.")
            findings, message = self.collect(ctx)
            status = CheckStatus.ISSUES if _needs_attention(findings) else CheckStatus.OK
        except Unavailable as exc:
            findings, message, status = [], str(exc), CheckStatus.UNAVAILABLE
        except QueryError as exc:
            findings, message, status = [], str(exc), CheckStatus.ERROR
        except Exception as exc:  # a broken check must never break the whole scan
            findings, message = [], f"Unexpected error: {type(exc).__name__}: {exc}"
            status = CheckStatus.ERROR
        return CheckResult(
            check_id=self.id,
            name=self.name,
            status=status,
            findings=findings,
            message=message,
            duration_s=time.monotonic() - start,
        )

    @abstractmethod
    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        """Return (findings, short status message)."""


def _needs_attention(findings: list[Finding]) -> bool:
    from crashlens.core.models import Severity

    return any(f.severity >= Severity.LOW for f in findings)
