"""Background workers so scans and repairs never freeze the window."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from crashlens.core.models import ScanReport
from crashlens.environment import Environment
from crashlens.repairs.executor import Approval, RepairOutcome


class ScanWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)  # ScanReport
    failed = Signal(str)

    def __init__(self, env: Environment, days: int) -> None:
        super().__init__()
        self.env = env
        self.days = days
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        try:
            report: ScanReport = self.env.scanner(self.days).run(
                progress=lambda i, t, n: self.progress.emit(i, t, n),
                cancelled=self._cancel.is_set,
            )
        except Exception as exc:  # pragma: no cover - scanner already isolates checks
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(report)


class RepairWorker(QObject):
    finished = Signal(object)  # RepairOutcome
    failed = Signal(str)

    def __init__(self, env: Environment, repair_id: str, approval: Approval) -> None:
        super().__init__()
        self.env = env
        self.repair_id = repair_id
        self.approval = approval

    @Slot()
    def run(self) -> None:
        try:
            outcome: RepairOutcome = self.env.executor.execute(self.repair_id, self.approval)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(outcome)
