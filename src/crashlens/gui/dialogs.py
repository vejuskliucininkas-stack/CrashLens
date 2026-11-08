"""The approval dialog shown before any repair runs."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from crashlens.repairs.catalog import Repair, RepairKind


class ApprovalDialog(QDialog):
    """Shows exactly what a repair will do. Run stays disabled until the box is ticked."""

    def __init__(self, repair: Repair, will_elevate: bool, dry_run: bool, parent=None) -> None:
        super().__init__(parent)
        self.repair = repair
        self.setWindowTitle("Approve repair")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        title = QLabel(f"<b style='font-size:13pt'>{html.escape(repair.title)}</b>")
        title.setWordWrap(True)
        lay.addWidget(title)

        rows = [
            ("What happens", repair.what_happens),
            ("Command", " ".join(repair.argv)),
            ("Takes", repair.duration),
        ]
        if repair.kind is RepairKind.TOOL and repair.changes_system:
            rows.append(("Changes", "Windows system files or settings (not your personal files)."))
        if will_elevate:
            rows.append(("Permission", "Windows will ask for administrator permission next."))
        if repair.needs_restart:
            rows.append(("Restart", "A restart is needed to finish."))
        if repair.caution:
            rows.append(("Caution", repair.caution))
        if dry_run:
            rows.append(("Demo / dry run", "Nothing will actually run."))
        body = "".join(
            f"<tr><td style='padding:3px 12px 3px 0;color:#5f5f5f;white-space:nowrap'>"
            f"{html.escape(k)}</td><td style='padding:3px 0'>"
            + (f"<code>{html.escape(v)}</code>" if k == "Command" else html.escape(v))
            + "</td></tr>"
            for k, v in rows
        )
        details = QLabel(f"<table>{body}</table>")
        details.setWordWrap(True)
        details.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(details)

        self.confirm = QCheckBox("I understand what this does and want to run it now.")
        lay.addWidget(self.confirm)

        buttons = QDialogButtonBox()
        self.run_button = QPushButton("Run repair" if repair.kind is RepairKind.TOOL else "Open")
        self.run_button.setObjectName("Primary")
        self.run_button.setEnabled(False)
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(self.run_button, QDialogButtonBox.ButtonRole.AcceptRole)
        cancel.setDefault(True)
        cancel.setAutoDefault(True)
        self.run_button.setAutoDefault(False)
        self.confirm.toggled.connect(self.run_button.setEnabled)
        buttons.accepted.connect(self._accept_if_confirmed)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept_if_confirmed(self) -> None:
        if self.confirm.isChecked():
            self.accept()
