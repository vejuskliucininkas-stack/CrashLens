"""Runs all checks and collects a ScanReport."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from crashlens.checks.base import Check, CheckContext
from crashlens.checks.crashes import (
    AppCrashCheck,
    BlueScreenCheck,
    GraphicsDriverCheck,
    HardwareErrorCheck,
    ReliabilityCheck,
)
from crashlens.checks.health import ALL_HEALTH_CHECKS
from crashlens.core.models import CheckResult, CheckStatus, ScanReport, SystemInfo
from crashlens.core.platform import windows_dir
from crashlens.core.runner import CommandRunner

CRASH_CHECKS: tuple[type[Check], ...] = (
    BlueScreenCheck,
    GraphicsDriverCheck,
    HardwareErrorCheck,
    AppCrashCheck,
    ReliabilityCheck,
)
HEALTH_CHECKS: tuple[type[Check], ...] = ALL_HEALTH_CHECKS

ProgressFn = Callable[[int, int, str], None]


def default_checks() -> list[Check]:
    return [cls() for cls in (*CRASH_CHECKS, *HEALTH_CHECKS)]


def is_crash_check(check_id: str) -> bool:
    return check_id.startswith("crash.")


class Scanner:
    def __init__(
        self,
        runner: CommandRunner,
        system: SystemInfo,
        *,
        demo: bool = False,
        lookback_days: int = 30,
        minidump_dir: Path | None = None,
        checks: Sequence[Check] | None = None,
    ) -> None:
        if not 1 <= lookback_days <= 365:
            raise ValueError("lookback_days must be between 1 and 365")
        self.runner = runner
        self.system = system
        self.demo = demo
        self.lookback_days = lookback_days
        if minidump_dir is None and system.is_windows and not demo:
            minidump_dir = windows_dir() / "Minidump"
        self.minidump_dir = minidump_dir
        self.checks = list(checks) if checks is not None else default_checks()

    def run(
        self,
        progress: ProgressFn | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> ScanReport:
        report = ScanReport(system=self.system, demo=self.demo)
        ctx = CheckContext(
            runner=self.runner,
            is_windows=self.system.is_windows or self.demo,
            lookback_days=self.lookback_days,
            minidump_dir=self.minidump_dir,
            demo=self.demo,
        )
        total = len(self.checks)
        for i, check in enumerate(self.checks):
            if cancelled and cancelled():
                report.results.append(
                    CheckResult(check.id, check.name, CheckStatus.UNAVAILABLE, message="Cancelled.")
                )
                continue
            if progress:
                progress(i, total, check.name)
            report.results.append(check.run(ctx))
        if progress:
            progress(total, total, "Done")
        report.finished_at = datetime.now(timezone.utc)
        return report
