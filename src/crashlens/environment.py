"""Builds the objects the CLI and GUI share (real system or demo)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from crashlens.core.models import SystemInfo
from crashlens.core.platform import app_data_dir, system_info
from crashlens.core.runner import CommandRunner, SubprocessRunner
from crashlens.demo import demo_runner, demo_system
from crashlens.repairs.executor import ApprovalRegistry, AuditLog, RepairExecutor
from crashlens.scanner import Scanner


@dataclass
class Environment:
    runner: CommandRunner
    system: SystemInfo
    demo: bool
    executor: RepairExecutor
    audit: AuditLog

    def scanner(self, lookback_days: int = 30) -> Scanner:
        return Scanner(self.runner, self.system, demo=self.demo, lookback_days=lookback_days)


def build_environment(
    demo: bool = False, dry_run: bool = False, audit_path: Path | None = None
) -> Environment:
    if demo:
        runner: CommandRunner = demo_runner()
        system = demo_system()
        dry_run = True  # demo mode never runs anything for real
    else:
        runner = SubprocessRunner()
        system = system_info()
    audit = AuditLog(audit_path if audit_path is not None else app_data_dir() / "audit.log")
    executor = RepairExecutor(
        runner,
        ApprovalRegistry(),
        audit,
        is_windows=system.is_windows,
        is_admin=system.is_admin,
        dry_run=dry_run,
    )
    return Environment(runner, system, demo, executor, audit)
