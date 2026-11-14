"""Dialogs: asking before a fix runs, and explaining a problem in plain words."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from crashlens.core.models import Finding
from crashlens.gui import friendly
from crashlens.gui import style as theme
from crashlens.repairs.catalog import Repair, RepairKind


def label(text: str, name: str | None = None, wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def button(text: str, name: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    if name:
        btn.setObjectName(name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class Expander(QWidget):
    """A 'Show technical details' link that reveals extra content."""

    def __init__(self, title: str, content: QWidget, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._title = title
        self.toggle = button(f"▸  Show {title}", "Link")
        self.content = content
        content.setVisible(False)
        self.toggle.clicked.connect(self._flip)
        lay.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(content)

    def _flip(self) -> None:
        show = not self.content.isVisible()
        self.content.setVisible(show)
        arrow, verb = ("▾", "Hide") if show else ("▸", "Show")
        self.toggle.setText(f"{arrow}  {verb} {self._title}")


class ConfirmRepairDialog(QDialog):
    """Asks, in plain words, before any fix runs. 'No' is the default button."""

    def __init__(self, repair: Repair, will_elevate: bool, dry_run: bool, parent=None) -> None:
        super().__init__(parent)
        self.repair = repair
        self.setWindowTitle("Before we start")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(12)

        lay.addWidget(label(friendly.repair_name(repair.id), "H2"))
        lay.addWidget(label(friendly.repair_text(repair.id) or repair.description))

        facts = [f"<b>How long:</b> {html.escape(repair.duration)}"]
        if will_elevate:
            facts.append(
                "<b>Windows will ask for permission.</b> When you see "
                "“Do you want to allow this app to make changes?”, click "
                "<b>Yes</b>."
            )
        if repair.needs_restart:
            facts.append("<b>Restart needed.</b> Save your work first.")
        if repair.caution:
            facts.append(f"<b>Please note:</b> {html.escape(repair.caution)}")
        if dry_run:
            facts.append("<b>Demo:</b> this is practice - nothing will really happen.")
        info = label("<br>".join(facts))
        info.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(info)

        tech = label(
            f"What CrashLens will run: <code>{html.escape(' '.join(repair.argv))}</code><br>"
            f"{html.escape(repair.what_happens)}",
            "Small",
        )
        tech.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(Expander("technical details", tech))

        lay.addSpacing(6)
        lay.addWidget(label("Do you want to start?", "H3"))
        row = QHBoxLayout()
        row.addStretch(1)
        self.no_button = button("No, go back")
        start_word = "Yes, start" if repair.kind is RepairKind.TOOL else "Yes, open it"
        self.yes_button = button(start_word, "Primary")
        self.no_button.setDefault(True)
        self.no_button.setAutoDefault(True)
        self.yes_button.setAutoDefault(False)
        self.no_button.clicked.connect(self.reject)
        self.yes_button.clicked.connect(self.accept)
        row.addWidget(self.no_button)
        row.addWidget(self.yes_button)
        lay.addLayout(row)
        self.no_button.setFocus()


class FindingDialog(QDialog):
    """'Tell me more': what happened, what to do, and the fixes - in plain words."""

    fix_requested = Signal(str)

    def __init__(self, finding: Finding, show_details: bool, parent=None) -> None:
        super().__init__(parent)
        self.finding = finding
        self.setWindowTitle("What this means")
        self.resize(640, 620)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("Page")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 16)
        lay.setSpacing(12)

        badge = label(friendly.badge(finding).upper(), "Badge")
        badge.setStyleSheet(f"color:{theme.severity_color(finding.severity)}")
        lay.addWidget(badge)
        lay.addWidget(label(friendly.headline(finding), "H2"))
        lay.addWidget(label(friendly.explanation(finding)))

        lay.addWidget(label("What happened", "H3"))
        lay.addWidget(label(finding.summary, "Muted"))

        if finding.recommendations:
            lay.addWidget(label("What you can do", "H3"))
            steps = "".join(f"<li>{html.escape(r)}</li>" for r in finding.recommendations)
            s = label(f"<ol style='margin-left:-20px'>{steps}</ol>")
            s.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(s)

        self.fix_buttons: list[QPushButton] = []
        if finding.repair_ids:
            lay.addWidget(label("CrashLens can help with", "H3"))
            for i, rid in enumerate(finding.repair_ids):
                card = QFrame()
                card.setObjectName("Card")
                cl = QHBoxLayout(card)
                cl.setContentsMargins(16, 12, 12, 12)
                text = QVBoxLayout()
                text.addWidget(label(f"<b>{html.escape(friendly.repair_name(rid))}</b>"))
                text.addWidget(label(friendly.repair_text(rid), "Small"))
                cl.addLayout(text, 1)
                btn = button("Start", "Primary" if i == 0 else None)
                btn.clicked.connect(lambda _=False, r=rid: self._fix(r))
                self.fix_buttons.append(btn)
                cl.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
                lay.addWidget(card)

        if finding.details or finding.evidence:
            parts = []
            if finding.details:
                parts.append(html.escape(finding.details))
            parts.append(f"<b>{html.escape(finding.title)}</b>")
            parts += [html.escape(e) for e in finding.evidence]
            tech = label("<br>".join(parts), "Small")
            tech.setTextFormat(Qt.TextFormat.RichText)
            exp = Expander("technical details", tech)
            if show_details:
                exp._flip()
            lay.addWidget(exp)
        lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.setContentsMargins(28, 8, 28, 18)
        row.addStretch(1)
        close = button("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        outer.addLayout(row)

    def _fix(self, rid: str) -> None:
        self.done(QDialog.DialogCode.Accepted)
        self.fix_requested.emit(rid)


class FixAllDialog(QDialog):
    """Shows every fix 'Fix everything' will run, lets the person untick any, and asks once.
    'Cancel' is the default button."""

    def __init__(self, plan, will_elevate: bool, dry_run: bool, parent=None) -> None:
        from PySide6.QtWidgets import QCheckBox

        from crashlens.repairs.catalog import REPAIRS

        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Fix everything")
        self.resize(640, 640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("Page")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 12)
        lay.setSpacing(10)
        lay.addWidget(label("Fix everything", "H2"))
        lay.addWidget(
            label(
                "CrashLens will run these fixes one after another. Untick anything you don't "
                "want. None of them delete your documents, photos or programs.",
                "Muted",
            )
        )

        self.boxes: dict[str, QCheckBox] = {}
        for step in plan.steps:
            r = REPAIRS[step.repair_id]
            card = QFrame()
            card.setObjectName("Card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(4)
            box = QCheckBox(friendly.repair_name(step.repair_id))
            box.setChecked(True)
            f = box.font()
            f.setBold(True)
            box.setFont(f)
            self.boxes[step.repair_id] = box
            cl.addWidget(box)
            if step.findings:
                why = "; ".join(friendly.headline(x) for x in step.findings[:3])
                cl.addWidget(label(f"For: {why}", "Small"))
            elif step.repair_id == "restore_point":
                cl.addWidget(label("Safety first: lets you undo the changes later.", "Small"))
            cl.addWidget(label(f"{friendly.repair_text(step.repair_id)}  ({r.duration})", "Small"))
            lay.addWidget(card)

        notes = []
        if will_elevate:
            notes.append(
                "<b>Windows will ask for permission once.</b> When you see "
                "“Do you want to allow this app to make changes?”, click "
                "<b>Yes</b>."
            )
        if dry_run:
            notes.append("<b>Demo:</b> this is practice - nothing will really happen.")
        if notes:
            n = label("<br>".join(notes))
            n.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(n)

        if plan.manual:
            lay.addWidget(label("You'll need to do these yourself", "H3"))
            items = "".join(
                f"<li><b>{html.escape(friendly.headline(f))}</b>"
                + (f" - {html.escape(f.recommendations[0])}" if f.recommendations else "")
                + "</li>"
                for f in plan.manual
            )
            m = label(f"<ul style='margin-left:-20px'>{items}</ul>", "Small")
            m.setTextFormat(Qt.TextFormat.RichText)
            lay.addWidget(m)
        lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.setContentsMargins(28, 8, 28, 18)
        row.addStretch(1)
        self.cancel_button = button("Cancel")
        self.start_button = button("Start fixing", "Primary")
        self.cancel_button.setDefault(True)
        self.cancel_button.setAutoDefault(True)
        self.start_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.start_button.clicked.connect(self.accept)
        for box in self.boxes.values():
            box.toggled.connect(self._update)
        row.addWidget(self.cancel_button)
        row.addWidget(self.start_button)
        outer.addLayout(row)
        self._update()
        self.cancel_button.setFocus()

    def selected_ids(self) -> list[str]:
        return [rid for rid, box in self.boxes.items() if box.isChecked()]

    def _update(self) -> None:
        n = len(self.selected_ids())
        self.start_button.setEnabled(n > 0)
        self.start_button.setText(f"Start fixing ({n})" if n else "Start fixing")
