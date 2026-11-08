"""The main CrashLens window."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from crashlens import APP_NAME, __version__
from crashlens.core.models import Finding, ScanReport, Severity
from crashlens.core.platform import relaunch_as_admin
from crashlens.environment import Environment
from crashlens.gui.dialogs import ApprovalDialog
from crashlens.gui.style import SEVERITY_COLORS, STATUS_TEXT, finding_html_styles
from crashlens.gui.workers import RepairWorker, ScanWorker
from crashlens.repairs.catalog import REPAIRS
from crashlens.report import render, write_report
from crashlens.scanner import is_crash_check

PAGES = ("Overview", "Problems", "Checks", "Repairs", "Report")


def _label(text: str = "", name: str | None = None, wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def _wrapping_list() -> QListWidget:
    lst = QListWidget()
    lst.setWordWrap(True)
    lst.setTextElideMode(Qt.TextElideMode.ElideNone)
    lst.setResizeMode(QListWidget.ResizeMode.Adjust)
    lst.setSpacing(4)
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    lst.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    return lst


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    return frame, lay


def _page(title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 22, 28, 22)
    lay.setSpacing(12)
    lay.addWidget(_label(title, "PageTitle"))
    if subtitle:
        lay.addWidget(_label(subtitle, "Subtle"))
    return w, lay


def finding_to_html(f: Finding) -> str:
    color = SEVERITY_COLORS[f.severity]
    e = html.escape
    parts = [
        finding_html_styles(),
        f"<div class='sev' style='color:{color}'>{e(f.severity.label.upper())} &middot; "
        f"{e(f.category.value)}</div>",
        f"<h2>{e(f.title)}</h2>",
        f"<p>{e(f.summary)}</p>",
    ]
    if f.details:
        parts.append(f"<p>{e(f.details)}</p>")
    if f.last_seen:
        parts.append(
            f"<p class='muted'>Last seen: {e(f.last_seen.strftime('%Y-%m-%d %H:%M UTC'))}</p>"
        )
    if f.recommendations:
        parts.append("<p><b>What to do</b></p><ol>")
        parts += [f"<li>{e(r)}</li>" for r in f.recommendations]
        parts.append("</ol>")
    if f.evidence:
        parts.append("<p class='muted'><b>Evidence</b></p><ul class='muted'>")
        parts += [f"<li>{e(x)}</li>" for x in f.evidence]
        parts.append("</ul>")
    return "".join(parts)


class MainWindow(QMainWindow):
    scan_completed = Signal(object)
    repair_completed = Signal(object)

    def __init__(self, env: Environment) -> None:
        super().__init__()
        self.env = env
        self.report: ScanReport | None = None
        self._threads: list[tuple[QThread, object]] = []
        self._scan_worker: ScanWorker | None = None
        self._repair_running = False
        self.setWindowTitle(f"{APP_NAME}" + (" - demo" if env.demo else ""))
        self.resize(1100, 720)
        self.setMinimumSize(860, 560)

        root = QWidget()
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(0, 0, 0, 12)
        side_lay.addWidget(_label(APP_NAME, "AppTitle"))
        self.nav = QListWidget()
        for name in PAGES:
            self.nav.addItem(QListWidgetItem(name))
        side_lay.addWidget(self.nav, 1)
        side_lay.addWidget(_label(f"  v{__version__}", "Subtle"))

        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        self.stack.addWidget(self._build_overview())
        self.stack.addWidget(self._build_problems())
        self.stack.addWidget(self._build_checks())
        self.stack.addWidget(self._build_repairs())
        self.stack.addWidget(self._build_report())
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        root_lay.addWidget(sidebar)
        root_lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._refresh_repairs_list()
        self._refresh_history()
        self._set_report_enabled(False)

    # ------------------------------------------------------------------ pages

    def _build_overview(self) -> QWidget:
        s = self.env.system
        sub = f"{s.os_name} {s.os_version}".strip()
        page, lay = _page("Overview", sub)
        if self.env.demo:
            b = _label(
                "Demo mode: CrashLens is showing a fictional PC with sample problems. "
                "Repairs are simulated and nothing on this computer is changed.",
                "DemoBanner",
            )
            b.setContentsMargins(12, 8, 12, 8)
            lay.addWidget(b)
        elif s.is_windows and not s.is_admin:
            banner = QFrame()
            banner.setObjectName("Banner")
            bl = QHBoxLayout(banner)
            bl.setContentsMargins(12, 8, 12, 8)
            bl.addWidget(
                _label(
                    "Some details (crash dump files, disk wear) need administrator rights. "
                    "Everything else works without them."
                ),
                1,
            )
            admin_btn = QPushButton("Restart as administrator")
            admin_btn.clicked.connect(self._restart_as_admin)
            bl.addWidget(admin_btn)
            lay.addWidget(banner)
        elif not s.is_windows:
            lay.addWidget(
                _label(
                    "This computer is not running Windows, so the checks cannot run here. "
                    "Start CrashLens with --demo to explore it with sample data.",
                    "Banner",
                )
            )

        card, cl = _card()
        cl.addWidget(_label("<b style='font-size:12pt'>Scan this PC</b>"))
        cl.addWidget(
            _label(
                "Reads the Windows event log, crash dumps and system status. "
                "Scanning only reads - it never changes anything.",
                "Subtle",
            )
        )
        row = QHBoxLayout()
        row.addWidget(QLabel("Look back"))
        self.days = QSpinBox()
        self.days.setRange(1, 365)
        self.days.setValue(30)
        self.days.setSuffix(" days")
        row.addWidget(self.days)
        row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_scan)
        row.addWidget(self.cancel_btn)
        self.scan_btn = QPushButton("Scan now")
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.clicked.connect(self.start_scan)
        row.addWidget(self.scan_btn)
        cl.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        cl.addWidget(self.progress)
        self.scan_status = _label("Not scanned yet.", "Subtle")
        cl.addWidget(self.scan_status)
        lay.addWidget(card)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        chip_row = QWidget()
        chip_row.setLayout(self.chips)
        lay.addWidget(chip_row)

        lay.addWidget(_label("<b>Most important</b>"))
        self.top_list = _wrapping_list()
        self.top_list.itemActivated.connect(self._open_top_item)
        self.top_list.itemClicked.connect(self._open_top_item)
        lay.addWidget(self.top_list, 1)
        return page

    def _build_problems(self) -> QWidget:
        page, lay = _page("Problems", "Everything CrashLens found, most serious first.")
        row = QHBoxLayout()
        row.addWidget(QLabel("Show"))
        self.filter = QComboBox()
        self.filter.addItems(["All problems", "Crashes & stability", "System health"])
        self.filter.currentIndexChanged.connect(self._fill_problems)
        row.addWidget(self.filter)
        self.hide_info = QCheckBox("Hide information-only items")
        self.hide_info.setChecked(False)
        self.hide_info.toggled.connect(self._fill_problems)
        row.addWidget(self.hide_info)
        row.addStretch(1)
        lay.addLayout(row)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.problem_list = _wrapping_list()
        self.problem_list.currentItemChanged.connect(self._show_problem)
        split.addWidget(self.problem_list)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.problem_view = QTextBrowser()
        self.problem_view.setOpenLinks(False)
        self.problem_view.setHtml("<p style='color:#5f5f5f'>Run a scan to see problems.</p>")
        rl.addWidget(self.problem_view, 1)
        self.fix_row = QHBoxLayout()
        fix_box = QWidget()
        fix_box.setLayout(self.fix_row)
        rl.addWidget(fix_box)
        split.addWidget(right)
        split.setSizes([330, 520])
        lay.addWidget(split, 1)
        return page

    def _build_checks(self) -> QWidget:
        page, lay = _page("Checks", "What each check found, and whether it could run.")
        self.check_table = QTableWidget(0, 4)
        self.check_table.setHorizontalHeaderLabels(["Check", "Status", "Result", "Time"])
        self.check_table.verticalHeader().setVisible(False)
        self.check_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.check_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.check_table.setWordWrap(True)
        hh = self.check_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.check_table, 1)
        return page

    def _build_repairs(self) -> QWidget:
        page, lay = _page(
            "Repairs",
            "Every repair shows exactly what it does and runs only after you approve it.",
        )
        split = QSplitter(Qt.Orientation.Horizontal)
        self.repair_list = _wrapping_list()
        self.repair_list.currentItemChanged.connect(self._show_repair)
        split.addWidget(self.repair_list)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.repair_info = QTextBrowser()
        rl.addWidget(self.repair_info, 2)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.repair_btn = QPushButton("Review and run...")
        self.repair_btn.setObjectName("Primary")
        self.repair_btn.setEnabled(False)
        self.repair_btn.clicked.connect(self._run_selected_repair)
        btn_row.addWidget(self.repair_btn)
        rl.addLayout(btn_row)
        self.repair_output = QPlainTextEdit()
        self.repair_output.setReadOnly(True)
        self.repair_output.setPlaceholderText("Repair results appear here.")
        rl.addWidget(self.repair_output, 2)
        split.addWidget(right)
        split.setSizes([330, 520])
        lay.addWidget(split, 3)
        lay.addWidget(_label("<b>History</b>"))
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["Time (UTC)", "Event", "Repair", "Result"])
        self.history.verticalHeader().setVisible(False)
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.history, 1)
        return page

    def _build_report(self) -> QWidget:
        page, lay = _page(
            "Report",
            "Save the scan results to send to a technician, a friend or a support forum.",
        )
        card, cl = _card()
        cl.addWidget(_label("<b>Format</b>"))
        self.fmt_group = QButtonGroup(self)
        for i, (fmt, text) in enumerate(
            [
                ("html", "Web page (.html) - easiest to read"),
                ("md", "Markdown (.md) - for forums and chat"),
                ("json", "Data (.json) - for tools"),
            ]
        ):
            rb = QRadioButton(text)
            rb.setProperty("fmt", fmt)
            rb.setChecked(i == 0)
            self.fmt_group.addButton(rb, i)
            cl.addWidget(rb)
        self.redact = QCheckBox(
            "Remove personal details (your user name, computer name, e-mail addresses, "
            "serial numbers)"
        )
        self.redact.setChecked(True)
        cl.addWidget(self.redact)
        row = QHBoxLayout()
        self.copy_btn = QPushButton("Copy summary")
        self.copy_btn.clicked.connect(self.copy_summary)
        row.addWidget(self.copy_btn)
        row.addStretch(1)
        self.save_btn = QPushButton("Save report...")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self.save_report)
        row.addWidget(self.save_btn)
        cl.addLayout(row)
        self.report_status = _label("Run a scan first.", "Subtle")
        cl.addWidget(self.report_status)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------------ scanning

    def start_scan(self) -> None:
        if self._scan_worker is not None:
            return
        worker = ScanWorker(self.env, self.days.value())
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        self._scan_worker = worker
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.scan_status.setText("Starting scan...")
        self._start(worker)

    def cancel_scan(self) -> None:
        if self._scan_worker:
            self._scan_worker.cancel()
            self.scan_status.setText("Cancelling...")

    def _on_progress(self, i: int, total: int, name: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(i)
        if name != "Done":
            self.scan_status.setText(f"Checking: {name} ({i + 1} of {total})")

    def _scan_done(self) -> None:
        self._scan_worker = None
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan again")
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

    def _on_scan_failed(self, message: str) -> None:
        self._scan_done()
        self.scan_status.setText(f"The scan failed: {message}")

    def _on_scan_finished(self, report: ScanReport) -> None:
        self._scan_done()
        self.report = report
        counts = report.counts()
        problems = sum(n for s, n in counts.items() if s >= Severity.LOW)
        when = report.started_at.astimezone().strftime("%H:%M")
        if problems:
            self.scan_status.setText(
                f"Scan finished at {when}: {problems} thing(s) need attention."
            )
        else:
            self.scan_status.setText(f"Scan finished at {when}: no problems found.")
        self._fill_chips(counts)
        self._fill_top()
        self._fill_problems()
        self._fill_checks()
        self._refresh_repairs_list()
        self._set_report_enabled(True)
        self.scan_completed.emit(report)

    def _fill_chips(self, counts: dict[Severity, int]) -> None:
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for sev in sorted(Severity, reverse=True):
            n = counts.get(sev, 0)
            if not n:
                continue
            chip = QLabel(f"{n} {sev.label.lower()}")
            chip.setStyleSheet(
                f"background:{SEVERITY_COLORS[sev]};color:white;border-radius:11px;"
                "padding:3px 12px;font-weight:600"
            )
            self.chips.addWidget(chip)
        self.chips.addStretch(1)

    def _list_item(self, f: Finding) -> QListWidgetItem:
        item = QListWidgetItem(f"{f.severity.label.upper()}  -  {f.title}")
        item.setData(Qt.ItemDataRole.UserRole, f.id)
        item.setForeground(QColor(SEVERITY_COLORS[f.severity]))
        item.setToolTip(f.summary)
        return item

    def _fill_top(self) -> None:
        self.top_list.clear()
        if self.report is None:
            return
        top = [f for f in self.report.findings if f.severity >= Severity.LOW][:6]
        if not top:
            self.top_list.addItem("Nothing needs attention right now.")
        for f in top:
            self.top_list.addItem(self._list_item(f))

    def _visible_findings(self) -> list[Finding]:
        if not self.report:
            return []
        mode = self.filter.currentIndex()
        out = []
        for r in self.report.results:
            crash = is_crash_check(r.check_id)
            if (mode == 1 and not crash) or (mode == 2 and crash):
                continue
            out += r.findings
        if self.hide_info.isChecked():
            out = [f for f in out if f.severity > Severity.INFO]
        return sorted(out, key=lambda f: (-int(f.severity), f.title))

    def _fill_problems(self) -> None:
        self.problem_list.clear()
        items = self._visible_findings()
        for f in items:
            self.problem_list.addItem(self._list_item(f))
        if items:
            self.problem_list.setCurrentRow(0)
        else:
            self.problem_view.setHtml(
                "<p style='color:#5f5f5f'>"
                + ("No problems in this view." if self.report else "Run a scan to see problems.")
                + "</p>"
            )
            self._set_fix_buttons(())

    def _finding(self, fid: str | None) -> Finding | None:
        if not self.report or not fid:
            return None
        return next((f for f in self.report.findings if f.id == fid), None)

    def _show_problem(self, current: QListWidgetItem | None, _prev=None) -> None:
        f = self._finding(current.data(Qt.ItemDataRole.UserRole) if current else None)
        if not f:
            return
        self.problem_view.setHtml(finding_to_html(f))
        self._set_fix_buttons(f.repair_ids)

    def _set_fix_buttons(self, repair_ids) -> None:
        while self.fix_row.count():
            item = self.fix_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for rid in repair_ids:
            if rid not in REPAIRS:
                continue
            btn = QPushButton(REPAIRS[rid].title + "...")
            btn.clicked.connect(lambda _=False, r=rid: self.request_repair(r))
            btn.setEnabled(not self._repair_running)
            self.fix_row.addWidget(btn)
        self.fix_row.addStretch(1)

    def _open_top_item(self, item: QListWidgetItem) -> None:
        fid = item.data(Qt.ItemDataRole.UserRole)
        if not fid:
            return
        self.show_finding(fid)

    def show_finding(self, fid: str) -> None:
        self.filter.setCurrentIndex(0)
        self.hide_info.setChecked(False)
        self.nav.setCurrentRow(PAGES.index("Problems"))
        for i in range(self.problem_list.count()):
            if self.problem_list.item(i).data(Qt.ItemDataRole.UserRole) == fid:
                self.problem_list.setCurrentRow(i)
                break

    def _fill_checks(self) -> None:
        if self.report is None:
            return
        t = self.check_table
        t.setRowCount(0)
        for r in self.report.results:
            row = t.rowCount()
            t.insertRow(row)
            text, color = STATUS_TEXT[r.status]
            t.setItem(row, 0, QTableWidgetItem(r.name))
            st = QTableWidgetItem(text)
            st.setForeground(QColor(color))
            t.setItem(row, 1, st)
            t.setItem(row, 2, QTableWidgetItem(r.message))
            t.setItem(row, 3, QTableWidgetItem(f"{r.duration_s:.1f}s"))
        t.resizeRowsToContents()

    # ------------------------------------------------------------------ repairs

    def _refresh_repairs_list(self) -> None:
        current = self.repair_list.currentItem()
        keep = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.repair_list.clear()
        suggested = self.report.recommended_repairs() if self.report else []
        order = suggested + [rid for rid in REPAIRS if rid not in suggested]
        for rid in order:
            r = REPAIRS[rid]
            text = ("Suggested - " if rid in suggested else "") + r.title
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, rid)
            if rid in suggested:
                item.setForeground(QColor("#0f6cbd"))
            self.repair_list.addItem(item)
            if rid == keep:
                self.repair_list.setCurrentItem(item)
        if self.repair_list.currentRow() < 0 and self.repair_list.count():
            self.repair_list.setCurrentRow(0)

    def _show_repair(self, current: QListWidgetItem | None, _prev=None) -> None:
        if not current:
            self.repair_btn.setEnabled(False)
            return
        r = REPAIRS[current.data(Qt.ItemDataRole.UserRole)]
        _, elevate = self.env.executor.plan(r)
        e = html.escape
        facts = [f"Takes {r.duration}."]
        if elevate:
            facts.append("Windows will ask for administrator permission.")
        if r.needs_restart:
            facts.append("Needs a restart.")
        self.repair_info.setHtml(
            finding_html_styles()
            + f"<h2>{e(r.title)}</h2><p>{e(r.description)}</p>"
            + f"<p><b>What happens:</b> {e(r.what_happens)}</p>"
            + f"<p class='muted'>{e(' '.join(facts))}</p>"
            + (f"<p><b>Caution:</b> {e(r.caution)}</p>" if r.caution else "")
            + f"<p class='muted'>Command: <code>{e(' '.join(r.argv))}</code></p>"
        )
        self.repair_btn.setEnabled(not self._repair_running)

    def _run_selected_repair(self) -> None:
        item = self.repair_list.currentItem()
        if item:
            self.request_repair(item.data(Qt.ItemDataRole.UserRole))

    def approval_dialog(self, rid: str) -> ApprovalDialog:
        repair = REPAIRS[rid]
        _, elevate = self.env.executor.plan(repair)
        return ApprovalDialog(repair, elevate, self.env.executor.dry_run, self)

    def request_repair(self, rid: str) -> None:
        if self._repair_running:
            return
        if not self.env.system.is_windows and not self.env.executor.dry_run:
            QMessageBox.information(self, APP_NAME, "Repairs can only run on Windows.")
            return
        dialog = self.approval_dialog(rid)
        if dialog.exec() != ApprovalDialog.DialogCode.Accepted:
            return
        self.run_approved_repair(rid)

    def run_approved_repair(self, rid: str) -> None:
        """Called only after the user approved ``rid`` in the dialog."""
        approval = self.env.executor.approvals.grant(rid, approved_by="gui")
        worker = RepairWorker(self.env, rid, approval)
        worker.finished.connect(self._on_repair_finished)
        worker.failed.connect(self._on_repair_failed)
        self._set_repair_running(True)
        self.nav.setCurrentRow(PAGES.index("Repairs"))
        self.repair_output.setPlainText(f"Running: {REPAIRS[rid].title}...\n")
        self._start(worker)

    def _set_repair_running(self, running: bool) -> None:
        self._repair_running = running
        self.repair_btn.setEnabled(not running and self.repair_list.currentItem() is not None)
        for i in range(self.fix_row.count()):
            w = self.fix_row.itemAt(i).widget()
            if w:
                w.setEnabled(not running)

    def _on_repair_finished(self, outcome) -> None:
        self._set_repair_running(False)
        lines = [f"{outcome.status.upper()}: {outcome.message}"]
        lines += [f"Next: {s}" for s in outcome.follow_up]
        if outcome.output and not outcome.elevated_window:
            lines += ["", "--- tool output ---", outcome.output.strip()]
        self.repair_output.setPlainText("\n".join(lines))
        self._refresh_history()
        self.repair_completed.emit(outcome)

    def _on_repair_failed(self, message: str) -> None:
        self._set_repair_running(False)
        self.repair_output.setPlainText(f"Not run: {message}")
        self._refresh_history()

    def _refresh_history(self) -> None:
        rows = list(reversed(self.env.audit.read(100)))
        t = self.history
        t.setRowCount(0)
        for row in rows:
            i = t.rowCount()
            t.insertRow(i)
            t.setItem(i, 0, QTableWidgetItem(str(row.get("time", ""))[:19].replace("T", " ")))
            t.setItem(i, 1, QTableWidgetItem(str(row.get("event", "")).replace("repair.", "")))
            rid = str(row.get("repair_id", ""))
            t.setItem(i, 2, QTableWidgetItem(REPAIRS[rid].title if rid in REPAIRS else rid))
            t.setItem(i, 3, QTableWidgetItem(str(row.get("status") or row.get("reason") or "")))

    # ------------------------------------------------------------------ report

    def _set_report_enabled(self, enabled: bool) -> None:
        self.save_btn.setEnabled(enabled)
        self.copy_btn.setEnabled(enabled)
        if enabled:
            self.report_status.setText("Ready.")

    def selected_format(self) -> str:
        btn = self.fmt_group.checkedButton()
        return btn.property("fmt") if btn else "html"

    def save_report(self, path: str | None = None) -> Path | None:
        if not self.report:
            return None
        fmt = self.selected_format()
        if not path:
            stamp = self.report.started_at.astimezone().strftime("%Y%m%d-%H%M")
            default = str(Path.home() / f"CrashLens-report-{stamp}.{fmt}")
            filters = {
                "html": "Web page (*.html)",
                "md": "Markdown (*.md)",
                "json": "JSON (*.json)",
            }
            path, _ = QFileDialog.getSaveFileName(self, "Save report", default, filters[fmt])
            if not path:
                return None
        target = Path(path)
        if target.suffix.lower().lstrip(".") != fmt:
            target = target.with_suffix(f".{fmt}")
        try:
            # The save dialog already asked before replacing an existing file.
            out = write_report(
                self.report, target, fmt, redact=self.redact.isChecked(), overwrite=True
            )
        except OSError as exc:
            self.report_status.setText(f"Could not save: {exc}")
            return None
        self.report_status.setText(f"Saved: {out}")
        return out

    def copy_summary(self) -> None:
        if not self.report:
            return
        QGuiApplication.clipboard().setText(render(self.report, "md", self.redact.isChecked()))
        self.report_status.setText("Summary copied to the clipboard (Markdown).")

    # ------------------------------------------------------------------ helpers

    def _start(self, worker) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        pair = (thread, worker)
        self._threads.append(pair)
        thread.finished.connect(
            lambda: self._threads.remove(pair) if pair in self._threads else None
        )
        thread.start()

    def _restart_as_admin(self) -> None:
        if relaunch_as_admin():
            self.close()
        else:
            QMessageBox.information(self, APP_NAME, "CrashLens could not restart as administrator.")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._scan_worker:
            self._scan_worker.cancel()
        for thread, _ in list(self._threads):
            thread.quit()
            thread.wait(3000)
        super().closeEvent(event)
