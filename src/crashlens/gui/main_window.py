"""The main CrashLens window - made for people who have never used a PC tool before."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from crashlens import APP_NAME, __version__
from crashlens.core.models import Finding, ScanReport, Severity
from crashlens.core.platform import relaunch_as_admin
from crashlens.core.settings import LOOKBACK_CHOICES, Settings
from crashlens.environment import Environment
from crashlens.gui import friendly, logo
from crashlens.gui import style as theme
from crashlens.gui.dialogs import ConfirmRepairDialog, FindingDialog, button, label
from crashlens.gui.workers import RepairWorker, ScanWorker
from crashlens.repairs.catalog import REPAIRS
from crashlens.report import render, write_report

P_WELCOME, P_HOME, P_FIX, P_HELP, P_SETTINGS, P_DETAILS = range(6)
NAV = [
    ("Home", P_HOME),
    ("Fix tools", P_FIX),
    ("Get help", P_HELP),
    ("Settings", P_SETTINGS),
    ("Details", P_DETAILS),
]
ALWAYS_SUGGEST = ("sfc_scan", "open_windows_update", "open_storage_settings")


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class FitScrollArea(QScrollArea):
    """A scroll area whose page always grows to fit its (word-wrapped) content.

    Qt does not enforce a minimum height on pages whose layout uses
    height-for-width (wrapped labels), so content added later would be squashed.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._pending = False

    def setWidget(self, widget: QWidget) -> None:  # noqa: N802 - Qt API
        super().setWidget(widget)
        widget.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if obj is self.widget() and event.type() == QEvent.Type.LayoutRequest:
            self._schedule()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._schedule()

    def _schedule(self) -> None:
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self._fit)

    def _fit(self) -> None:
        self._pending = False
        inner = self.widget()
        if inner is None or inner.layout() is None:
            return
        width = self.viewport().width()
        lay = inner.layout()
        needed = lay.totalHeightForWidth(width) if lay.hasHeightForWidth() else 0
        needed = max(needed, lay.totalMinimumSize().height())
        if inner.minimumHeight() != needed:
            inner.setMinimumHeight(needed)


def _scroll_page(margins=(40, 32, 40, 32)) -> tuple[QScrollArea, QVBoxLayout]:
    area = FitScrollArea()
    inner = QWidget()
    inner.setObjectName("Page")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(*margins)
    lay.setSpacing(16)
    area.setWidget(inner)
    return area, lay


def _card(name: str = "Card", margins=(22, 18, 22, 18)) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(8)
    return frame, lay


class MainWindow(QMainWindow):
    scan_completed = Signal(object)
    repair_completed = Signal(object)

    def __init__(self, env: Environment, settings: Settings | None = None) -> None:
        super().__init__()
        self.env = env
        self.settings = (settings or Settings.load(env.settings_path)).validated()
        self.report: ScanReport | None = None
        self._threads: list[tuple[QThread, object]] = []
        self._scan_worker: ScanWorker | None = None
        self._repair_running = False
        self._fix_buttons: list[QPushButton] = []
        self.cards: list[QFrame] = []

        self.setWindowTitle(APP_NAME + (" - demo" if env.demo else ""))
        self.setWindowIcon(logo.icon())
        self.resize(1120, 760)
        self.setMinimumSize(820, 580)

        root = QWidget()
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root_lay.addWidget(self.sidebar)

        right = QWidget()
        right.setObjectName("Content")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.busy = self._build_busy_banner()
        rl.addWidget(self.busy)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome())
        self.stack.addWidget(self._build_home())
        self.stack.addWidget(self._build_fix())
        self.stack.addWidget(self._build_help())
        self.stack.addWidget(self._build_settings())
        self.stack.addWidget(self._build_details())
        rl.addWidget(self.stack, 1)
        root_lay.addWidget(right, 1)
        self.setCentralWidget(root)

        self._sync_settings_widgets()
        self._apply_details_visibility()
        self._render_fix_tools()
        self._refresh_history()
        self._set_help_enabled(False)
        if self.settings.welcomed:
            self.go(P_HOME)
        else:
            self.go(P_WELCOME)

    # ================================================================== layout

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(230)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 22, 0, 16)
        lay.setSpacing(4)
        brand = QHBoxLayout()
        brand.setContentsMargins(22, 0, 16, 14)
        icon = QLabel()
        icon.setPixmap(logo.pixmap(36))
        brand.addWidget(icon)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label(APP_NAME, "Brand", wrap=False))
        names.addWidget(label("PC doctor", "Tagline", wrap=False))
        brand.addLayout(names)
        brand.addStretch(1)
        lay.addLayout(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        for text, _ in NAV:
            self.nav.addItem(QListWidgetItem(text))
        self.nav.currentRowChanged.connect(self._on_nav)
        lay.addWidget(self.nav, 1)
        lay.addWidget(label(f"    Version {__version__}", "Small", wrap=False))
        return side

    def _build_busy_banner(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Banner")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(20, 12, 20, 12)
        self.busy_text = label("")
        lay.addWidget(self.busy_text, 1)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setFixedWidth(160)
        bar.setTextVisible(False)
        lay.addWidget(bar)
        frame.setVisible(False)
        frame.setContentsMargins(16, 12, 16, 0)
        return frame

    # ------------------------------------------------------------------ welcome

    def _build_welcome(self) -> QWidget:
        area, outer = _scroll_page((40, 40, 40, 40))
        column = QWidget()
        column.setMaximumWidth(820)
        lay = QVBoxLayout(column)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(column, 10)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)

        icon = QLabel()
        icon.setPixmap(logo.pixmap(96))
        icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(icon)
        title = label("Welcome to CrashLens", "H1")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        sub = label(
            "Find out why your computer crashes, freezes or feels slow - "
            "explained in plain words, with fixes you can start in one click.",
            "Muted",
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(sub)

        steps = QHBoxLayout()
        steps.setSpacing(14)
        for num, head, text in (
            ("1", "Check", "One button looks at your whole computer. It only looks."),
            ("2", "Understand", "Every problem is explained the way a friend would."),
            ("3", "Fix", "Fixes ask you first. Nothing changes unless you say yes."),
        ):
            card, cl = _card()
            n = label(num, "H1")
            n.setStyleSheet(f"color:{theme.color('accent')}")
            cl.addWidget(n)
            cl.addWidget(label(head, "H3"))
            cl.addWidget(label(text, "Muted"))
            cl.addStretch(1)
            steps.addWidget(card, 1)
        lay.addLayout(steps)

        lay.addSpacing(6)
        look = label("How do you like it?", "H3")
        look.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(look)
        self.welcome_theme = self._choice_row(
            [("Light", "light"), ("Dark", "dark"), ("Same as Windows", "system")],
            self._set_theme,
            centered=True,
        )
        lay.addWidget(self.welcome_theme[0])
        lay.addSpacing(8)
        go = button("Let's start", "Big")
        go.clicked.connect(self._finish_welcome)
        self.welcome_button = go
        lay.addWidget(go, 0, Qt.AlignmentFlag.AlignHCenter)
        return area

    def _finish_welcome(self) -> None:
        self.settings.welcomed = True
        self.settings.save(self.env.settings_path)
        self.go(P_HOME)

    # ------------------------------------------------------------------ home

    def _build_home(self) -> QWidget:
        area, lay = _scroll_page()
        hero, hl = _card("Hero", (36, 32, 36, 30))
        hl.setSpacing(12)
        self.hello = label("Let's check your computer", "H1")
        hl.addWidget(self.hello)
        self.hello_sub = label(
            "Press the button. CrashLens looks for problems and explains them in simple "
            "words. Checking never changes anything.",
            "Muted",
        )
        hl.addWidget(self.hello_sub)
        row = QHBoxLayout()
        self.scan_btn = button("Check my computer", "Big")
        self.scan_btn.clicked.connect(self.start_scan)
        row.addWidget(self.scan_btn)
        self.cancel_btn = button("Stop")
        self.cancel_btn.clicked.connect(self.cancel_scan)
        self.cancel_btn.setVisible(False)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        hl.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        hl.addWidget(self.progress)
        self.progress_text = label("", "Muted")
        self.progress_text.setVisible(False)
        hl.addWidget(self.progress_text)
        lay.addWidget(hero)

        s = self.env.system
        if self.env.demo:
            lay.addWidget(
                self._banner(
                    "<b>Demo mode.</b> You are looking at a pretend computer with made-up "
                    "problems. Nothing on your real computer is checked or changed."
                )
            )
        elif not s.is_windows:
            lay.addWidget(
                self._banner(
                    "<b>This computer isn't running Windows</b>, so CrashLens can't check it. "
                    "Start it with --demo to try it with a pretend computer."
                )
            )
        elif not s.is_admin:
            banner = self._banner(
                "<b>Tip:</b> CrashLens can look a little deeper if you let it run as administrator."
            )
            btn = button("Allow")
            btn.clicked.connect(self._restart_as_admin)
            banner.layout().addWidget(btn)
            lay.addWidget(banner)

        self.verdict_card, vl = _card("Card", (26, 22, 26, 22))
        vrow = QHBoxLayout()
        vrow.setSpacing(18)
        self.verdict_icon = QLabel()
        self.verdict_icon.setFixedSize(64, 64)
        self.verdict_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vrow.addWidget(self.verdict_icon, 0, Qt.AlignmentFlag.AlignTop)
        vt = QVBoxLayout()
        self.verdict_title = label("", "H2")
        self.verdict_sub = label("", "Muted")
        vt.addWidget(self.verdict_title)
        vt.addWidget(self.verdict_sub)
        vrow.addLayout(vt, 1)
        vl.addLayout(vrow)
        self.verdict_card.setVisible(False)
        lay.addWidget(self.verdict_card)

        self.cards_box = QVBoxLayout()
        self.cards_box.setSpacing(12)
        lay.addLayout(self.cards_box)
        lay.addStretch(1)
        return area

    def _banner(self, text: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Banner")
        bl = QHBoxLayout(frame)
        bl.setContentsMargins(18, 12, 18, 12)
        lab = label(text)
        lab.setTextFormat(Qt.TextFormat.RichText)
        bl.addWidget(lab, 1)
        return frame

    def _problem_card(self, f: Finding, first: bool) -> QFrame:
        card, cl = _card("Card", (24, 18, 22, 18))
        card.setStyleSheet(
            f"QFrame#Card {{ border-left: 6px solid {theme.severity_color(f.severity)}; }}"
        )
        top = QHBoxLayout()
        badge = label(friendly.badge(f).upper(), "Badge", wrap=False)
        badge.setStyleSheet(f"color:{theme.severity_color(f.severity)}")
        top.addWidget(badge)
        if first and f.severity >= Severity.HIGH:
            top.addWidget(label("  •  START HERE", "Badge", wrap=False))
        top.addStretch(1)
        cl.addLayout(top)
        cl.addWidget(label(friendly.headline(f), "H3"))
        cl.addWidget(label(friendly.explanation(f), "Muted"))
        row = QHBoxLayout()
        row.setSpacing(10)
        if f.repair_ids:
            rid = f.repair_ids[0]
            fix = button(f"Fix it: {friendly.repair_name(rid)}", "Primary")
            fix.clicked.connect(lambda _=False, r=rid: self.request_repair(r))
            fix.setEnabled(not self._repair_running)
            self._fix_buttons.append(fix)
            row.addWidget(fix)
        more = button("Tell me more")
        more.clicked.connect(lambda _=False, fid=f.id: self.show_finding(fid))
        row.addWidget(more)
        row.addStretch(1)
        cl.addLayout(row)
        card.setProperty("finding_id", f.id)
        return card

    # ------------------------------------------------------------------ fix tools

    def _build_fix(self) -> QWidget:
        area, lay = _scroll_page()
        lay.addWidget(label("Fix tools", "H1"))
        lay.addWidget(
            label(
                "Each tool tells you what it does and asks before it starts. "
                "None of them delete your files.",
                "Muted",
            )
        )
        self.fix_box = QVBoxLayout()
        self.fix_box.setSpacing(10)
        lay.addLayout(self.fix_box)
        self.last_result = self._banner("")
        self.last_result.setVisible(False)
        lay.addWidget(self.last_result)
        lay.addStretch(1)
        return area

    def _render_fix_tools(self) -> None:
        _clear(self.fix_box)
        self._fix_buttons = [b for b in self._fix_buttons if not b.isHidden() and b.parent()]
        suggested = self.report.recommended_repairs() if self.report else list(ALWAYS_SUGGEST)
        others = [rid for rid in REPAIRS if rid not in suggested]
        heading = "Suggested for your computer" if self.report else "Most useful"
        for title, ids in ((heading, suggested), ("More tools", others)):
            if not ids:
                continue
            self.fix_box.addWidget(label(title, "H3"))
            grid = QGridLayout()
            grid.setSpacing(12)
            for i, rid in enumerate(ids):
                card, cl = _card("Card", (20, 16, 20, 16))
                cl.addWidget(label(friendly.repair_name(rid), "H3"))
                desc = label(friendly.repair_text(rid), "Muted")
                cl.addWidget(desc, 1)
                btn = button("Start", "Primary" if title != "More tools" else None)
                btn.clicked.connect(lambda _=False, r=rid: self.request_repair(r))
                btn.setEnabled(not self._repair_running)
                self._fix_buttons.append(btn)
                cl.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(card, i // 2, i % 2)
            box = QWidget()
            box.setLayout(grid)
            self.fix_box.addWidget(box)

    # ------------------------------------------------------------------ get help

    def _build_help(self) -> QWidget:
        area, lay = _scroll_page()
        lay.addWidget(label("Get help from someone", "H1"))
        lay.addWidget(
            label(
                "Save a report about your computer and send it to a friend, a family member, "
                "a repair shop or a help forum. It shows them exactly what CrashLens found.",
                "Muted",
            )
        )
        self.help_needs_scan = self._banner(
            "First, check your computer on the <b>Home</b> page. Then come back here."
        )
        go_home = button("Go to Home")
        go_home.clicked.connect(lambda: self.go(P_HOME))
        self.help_needs_scan.layout().addWidget(go_home)
        lay.addWidget(self.help_needs_scan)

        card, cl = _card("Card", (26, 22, 26, 22))
        cl.addWidget(label("Save a report", "H2"))
        cl.addWidget(
            label(
                "Creates a file you can attach to an e-mail or a message. Anyone can open it "
                "in a web browser.",
                "Muted",
            )
        )
        self.redact = QCheckBox("Hide my name and my computer's name (recommended)")
        self.redact.setChecked(True)
        cl.addWidget(self.redact)
        fmt_row = QHBoxLayout()
        self.fmt_label = label("File type:", wrap=False)
        fmt_row.addWidget(self.fmt_label)
        self.fmt = QComboBox()
        for text, fmt in (
            ("Web page (.html) - best for most people", "html"),
            ("Text for forums (.md)", "md"),
            ("Data for tools (.json)", "json"),
        ):
            self.fmt.addItem(text, fmt)
        fmt_row.addWidget(self.fmt)
        fmt_row.addStretch(1)
        self.fmt_row = QWidget()
        self.fmt_row.setLayout(fmt_row)
        cl.addWidget(self.fmt_row)
        row = QHBoxLayout()
        self.save_btn = button("Save the report", "Primary")
        self.save_btn.clicked.connect(lambda: self.save_report())
        row.addWidget(self.save_btn)
        self.copy_btn = button("Copy as text")
        self.copy_btn.clicked.connect(self.copy_summary)
        row.addWidget(self.copy_btn)
        row.addStretch(1)
        cl.addLayout(row)
        self.report_status = label("", "Muted")
        cl.addWidget(self.report_status)
        lay.addWidget(card)
        lay.addStretch(1)
        return area

    # ------------------------------------------------------------------ settings

    def _choice_row(self, options, on_pick, centered=False) -> tuple[QWidget, QButtonGroup, dict]:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        if centered:
            row.addStretch(1)
        group = QButtonGroup(box)
        group.setExclusive(True)
        buttons = {}
        for text, value in options:
            b = button(text, "Choice")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, v=value: on_pick(v))
            group.addButton(b)
            buttons[value] = b
            row.addWidget(b)
        row.addStretch(1)
        return box, group, buttons

    def _build_settings(self) -> QWidget:
        area, lay = _scroll_page()
        lay.addWidget(label("Settings", "H1"))
        lay.addWidget(label("Changes are saved straight away.", "Muted"))

        card, cl = _card("Card", (26, 22, 26, 22))
        cl.addWidget(label("Look", "H2"))
        cl.addWidget(label("Light, dark, or match your Windows setting.", "Muted"))
        self.theme_choice = self._choice_row(
            [("Light", "light"), ("Dark", "dark"), ("Same as Windows", "system")],
            self._set_theme,
        )
        cl.addWidget(self.theme_choice[0])
        lay.addWidget(card)

        card, cl = _card("Card", (26, 22, 26, 22))
        cl.addWidget(label("Text size", "H2"))
        cl.addWidget(label("Make everything bigger and easier to read.", "Muted"))
        self.size_choice = self._choice_row(
            [("Normal", "normal"), ("Large", "large"), ("Extra large", "xlarge")],
            self._set_text_size,
        )
        cl.addWidget(self.size_choice[0])
        lay.addWidget(card)

        card, cl = _card("Card", (26, 22, 26, 22))
        cl.addWidget(label("How far back to look", "H2"))
        cl.addWidget(label("CrashLens looks for problems that happened in this time.", "Muted"))
        self.lookback = QComboBox()
        for days in LOOKBACK_CHOICES:
            self.lookback.addItem("The last year" if days == 365 else f"The last {days} days", days)
        self.lookback.currentIndexChanged.connect(self._set_lookback)
        cl.addWidget(self.lookback, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)

        card, cl = _card("Card", (26, 22, 26, 22))
        cl.addWidget(label("For experts", "H2"))
        self.details_box = QCheckBox("Show technical details and the Details page")
        self.details_box.toggled.connect(self._set_details)
        cl.addWidget(self.details_box)
        lay.addWidget(card)
        lay.addStretch(1)
        return area

    # ------------------------------------------------------------------ details (experts)

    def _build_details(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(12)
        lay.addWidget(label("Details", "H1"))
        lay.addWidget(label("Everything CrashLens found, in technical detail.", "Muted"))
        tabs = QTabWidget()
        split = QSplitter(Qt.Orientation.Horizontal)
        self.problem_list = QListWidget()
        self.problem_list.setWordWrap(True)
        self.problem_list.currentItemChanged.connect(self._show_problem_detail)
        split.addWidget(self.problem_list)
        self.problem_view = QTextBrowser()
        split.addWidget(self.problem_view)
        split.setSizes([340, 520])
        tabs.addTab(split, "All findings")
        self.check_table = self._table(["Check", "Status", "Result", "Time"])
        tabs.addTab(self.check_table, "Checks")
        self.history = self._table(["Time (UTC)", "Event", "Fix", "Result"])
        tabs.addTab(self.history, "Fix history")
        lay.addWidget(tabs, 1)
        return page

    def _table(self, headers: list[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setWordWrap(True)
        hh = t.horizontalHeader()
        for i in range(len(headers)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        return t

    # ================================================================== navigation

    def go(self, page: int) -> None:
        self.stack.setCurrentIndex(page)
        self.sidebar.setVisible(page != P_WELCOME)
        for row, (_, p) in enumerate(NAV):
            if p == page and self.nav.currentRow() != row:
                self.nav.blockSignals(True)
                self.nav.setCurrentRow(row)
                self.nav.blockSignals(False)

    def _on_nav(self, row: int) -> None:
        if 0 <= row < len(NAV):
            self.stack.setCurrentIndex(NAV[row][1])

    # ================================================================== settings

    def _sync_settings_widgets(self) -> None:
        for box in (self.theme_choice, self.welcome_theme):
            box[2][self.settings.theme].setChecked(True)
        self.size_choice[2][self.settings.text_size].setChecked(True)
        self.lookback.blockSignals(True)
        self.lookback.setCurrentIndex(LOOKBACK_CHOICES.index(self.settings.lookback_days))
        self.lookback.blockSignals(False)
        self.details_box.blockSignals(True)
        self.details_box.setChecked(self.settings.show_details)
        self.details_box.blockSignals(False)

    def _changed(self) -> None:
        self.settings.save(self.env.settings_path)
        self.apply_look()
        self._sync_settings_widgets()

    def _set_theme(self, value: str) -> None:
        self.settings.theme = value
        self._changed()

    def _set_text_size(self, value: str) -> None:
        self.settings.text_size = value
        self._changed()

    def _set_lookback(self, index: int) -> None:
        self.settings.lookback_days = LOOKBACK_CHOICES[index]
        self.settings.save(self.env.settings_path)

    def _set_details(self, on: bool) -> None:
        self.settings.show_details = on
        self.settings.save(self.env.settings_path)
        self._apply_details_visibility()

    def _apply_details_visibility(self) -> None:
        show = self.settings.show_details
        self.nav.item(len(NAV) - 1).setHidden(not show)
        self.fmt_row.setVisible(show)
        if not show and self.stack.currentIndex() == P_DETAILS:
            self.go(P_SETTINGS)

    def apply_look(self) -> None:
        """Re-apply theme and text size, and redraw the parts that use theme colours."""
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, self.settings)
        if self.report:
            self._render_results()
        self._render_fix_tools()

    # ================================================================== scanning

    def start_scan(self) -> None:
        if self._scan_worker is not None:
            return
        worker = ScanWorker(self.env, self.settings.lookback_days)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        self._scan_worker = worker
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Checking...")
        self.cancel_btn.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_text.setVisible(True)
        self.progress_text.setText("Getting started...")
        self._start(worker)

    def cancel_scan(self) -> None:
        if self._scan_worker:
            self._scan_worker.cancel()
            self.progress_text.setText("Stopping...")

    def _on_progress(self, i: int, total: int, name: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(i)
        if name != "Done":
            self.progress_text.setText(f"Looking at: {name.lower()}  ({i + 1} of {total})")

    def _scan_done(self) -> None:
        self._scan_worker = None
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Check again")
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.progress_text.setVisible(False)

    def _on_scan_failed(self, message: str) -> None:
        self._scan_done()
        self.progress_text.setVisible(True)
        self.progress_text.setText(f"Something went wrong while checking: {message}")

    def _on_scan_finished(self, report: ScanReport) -> None:
        self._scan_done()
        self.report = report
        self.hello.setText("Here's what we found")
        self.hello_sub.setText(
            f"Checked {report.started_at.astimezone():%A %d %B at %H:%M}. "
            "Press the button again any time."
        )
        self._render_results()
        self._render_fix_tools()
        self._fill_details()
        self._set_help_enabled(True)
        self.scan_completed.emit(report)

    def _render_results(self) -> None:
        if self.report is None:
            return
        mood, title, sub = friendly.verdict(self.report.findings)
        symbol = {"ok": "✓", "warn": "!", "bad": "!"}[mood]
        col = theme.color({"ok": "ok", "warn": "warn", "bad": "bad"}[mood])
        self.verdict_icon.setText(symbol)
        self.verdict_icon.setStyleSheet(
            f"background:{col};color:{theme.color('card')};border-radius:32px;"
            f"font-size:{theme.base_pt() * 2}pt;font-weight:800;"
        )
        self.verdict_title.setText(title)
        self.verdict_sub.setText(sub)
        self.verdict_card.setVisible(True)

        _clear(self.cards_box)
        self.cards = []
        self._fix_buttons = []
        lowest = Severity.INFO if self.settings.show_details else Severity.LOW
        main = [f for f in self.report.findings if f.severity >= Severity.MEDIUM]
        small = [f for f in self.report.findings if lowest <= f.severity < Severity.MEDIUM]
        if not main:
            main, small = small, []
        for i, f in enumerate(main):
            card = self._problem_card(f, first=(i == 0))
            self.cards.append(card)
            self.cards_box.addWidget(card)
        self.small_toggle = None
        if small:
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(12)
            for f in small:
                card = self._problem_card(f, first=False)
                self.cards.append(card)
                hl.addWidget(card)
            holder.setVisible(False)
            count = len(small)
            word = "smaller thing" if count == 1 else "smaller things"
            toggle = button(f"\u25b8  Show {count} {word}", "Link")

            def flip(_=False, t=toggle, h=holder, n=count, w=word) -> None:
                h.setVisible(not h.isVisible())
                t.setText(f"\u25be  Hide {n} {w}" if h.isVisible() else f"\u25b8  Show {n} {w}")

            toggle.clicked.connect(flip)
            self.small_toggle = toggle
            self.small_holder = holder
            self.cards_box.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
            self.cards_box.addWidget(holder)

    def _finding(self, fid: str | None) -> Finding | None:
        if not self.report or not fid:
            return None
        return next((f for f in self.report.findings if f.id == fid), None)

    def finding_dialog(self, fid: str) -> FindingDialog | None:
        f = self._finding(fid)
        if f is None:
            return None
        dlg = FindingDialog(f, self.settings.show_details, self)
        dlg.fix_requested.connect(self.request_repair)
        for b in dlg.fix_buttons:
            b.setEnabled(not self._repair_running)
        return dlg

    def show_finding(self, fid: str) -> None:
        dlg = self.finding_dialog(fid)
        if dlg is not None:
            dlg.exec()

    # ================================================================== fixes

    def approval_dialog(self, rid: str) -> ConfirmRepairDialog:
        repair = REPAIRS[rid]
        _, elevate = self.env.executor.plan(repair)
        return ConfirmRepairDialog(repair, elevate, self.env.executor.dry_run, self)

    def request_repair(self, rid: str) -> None:
        if self._repair_running or rid not in REPAIRS:
            return
        if not self.env.system.is_windows and not self.env.executor.dry_run:
            QMessageBox.information(self, APP_NAME, "Fixes only work on Windows.")
            return
        dialog = self.approval_dialog(rid)
        if dialog.exec() != ConfirmRepairDialog.DialogCode.Accepted:
            return
        self.run_approved_repair(rid)

    def run_approved_repair(self, rid: str) -> None:
        """Called only after the person said yes in the dialog."""
        approval = self.env.executor.approvals.grant(rid, approved_by="gui")
        worker = RepairWorker(self.env, rid, approval)
        worker.finished.connect(self._on_repair_finished)
        worker.failed.connect(self._on_repair_failed)
        self._set_repair_running(True, rid)
        self._start(worker)

    def _set_repair_running(self, running: bool, rid: str | None = None) -> None:
        self._repair_running = running
        if running and rid:
            self.busy_text.setText(
                f"<b>Working on: {html.escape(friendly.repair_name(rid))}</b> - "
                f"this can take {html.escape(REPAIRS[rid].duration)}. "
                "You can keep using your computer."
            )
            self.busy_text.setTextFormat(Qt.TextFormat.RichText)
        self.busy.setVisible(running)
        alive = []
        for b in self._fix_buttons:
            try:
                b.setEnabled(not running)
                alive.append(b)
            except RuntimeError:  # widget already deleted
                continue
        self._fix_buttons = alive

    def _result_words(self, outcome) -> tuple[str, str]:
        name = friendly.repair_name(outcome.repair_id)
        if outcome.status == "success":
            title = f"{name}: done"
        elif outcome.status == "launched":
            title = f"{name}: started"
        elif outcome.status == "simulated":
            title = f"{name}: practice run finished"
        elif outcome.status == "cancelled":
            title = f"{name}: cancelled"
        else:
            title = f"{name}: didn't work"
        text = outcome.message
        if outcome.status == "simulated":
            text = (
                "This was the demo, so nothing really happened. On your own computer, "
                "this would have started for real."
            )
        if outcome.follow_up:
            text += "\n\nWhat to do next:\n" + "\n".join(f"• {s}" for s in outcome.follow_up)
        return title, text

    def _on_repair_finished(self, outcome) -> None:
        self._set_repair_running(False)
        title, text = self._result_words(outcome)
        self.last_result.layout().itemAt(0).widget().setText(
            f"<b>{html.escape(title)}</b><br>{html.escape(text).replace(chr(10), '<br>')}"
        )
        self.last_result.setVisible(True)
        self._refresh_history()
        self.repair_completed.emit(outcome)
        if self.isVisible() and QApplication.platformName() != "offscreen":
            QMessageBox.information(self, title, text)

    def _on_repair_failed(self, message: str) -> None:
        self._set_repair_running(False)
        self.last_result.layout().itemAt(0).widget().setText(
            f"<b>That didn't start.</b><br>{html.escape(message)}"
        )
        self.last_result.setVisible(True)
        self._refresh_history()

    # ================================================================== details data

    def _fill_details(self) -> None:
        if self.report is None:
            return
        self.problem_list.clear()
        for f in self.report.findings:
            item = QListWidgetItem(f"{f.severity.label.upper()}  -  {f.title}")
            item.setData(Qt.ItemDataRole.UserRole, f.id)
            item.setForeground(QColor(theme.severity_color(f.severity)))
            self.problem_list.addItem(item)
        if self.problem_list.count():
            self.problem_list.setCurrentRow(0)
        t = self.check_table
        t.setRowCount(0)
        for r in self.report.results:
            row = t.rowCount()
            t.insertRow(row)
            text, col = theme.STATUS_TEXT[r.status]
            t.setItem(row, 0, QTableWidgetItem(r.name))
            st = QTableWidgetItem(text)
            st.setForeground(QColor(theme.color(col)))
            t.setItem(row, 1, st)
            t.setItem(row, 2, QTableWidgetItem(r.message))
            t.setItem(row, 3, QTableWidgetItem(f"{r.duration_s:.1f}s"))
        t.resizeRowsToContents()

    def _show_problem_detail(self, current, _prev=None) -> None:
        f = self._finding(current.data(Qt.ItemDataRole.UserRole) if current else None)
        if not f:
            return
        e = html.escape
        parts = [theme.html_styles(), f"<h2>{e(f.title)}</h2><p>{e(f.summary)}</p>"]
        if f.details:
            parts.append(f"<p>{e(f.details)}</p>")
        if f.recommendations:
            parts.append("<ol>" + "".join(f"<li>{e(r)}</li>" for r in f.recommendations) + "</ol>")
        if f.evidence:
            parts.append(
                "<ul class='muted'>" + "".join(f"<li>{e(x)}</li>" for x in f.evidence) + "</ul>"
            )
        self.problem_view.setHtml("".join(parts))

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
            t.setItem(i, 2, QTableWidgetItem(friendly.repair_name(rid) if rid else ""))
            t.setItem(i, 3, QTableWidgetItem(str(row.get("status") or row.get("reason") or "")))

    # ================================================================== reports

    def _set_help_enabled(self, enabled: bool) -> None:
        self.save_btn.setEnabled(enabled)
        self.copy_btn.setEnabled(enabled)
        self.help_needs_scan.setVisible(not enabled)

    def selected_format(self) -> str:
        return self.fmt.currentData() if self.settings.show_details else "html"

    def save_report(self, path: str | None = None) -> Path | None:
        if not self.report:
            return None
        fmt = self.selected_format()
        if not path:
            stamp = self.report.started_at.astimezone().strftime("%Y-%m-%d")
            default = str(Path.home() / "Desktop" / f"CrashLens report {stamp}.{fmt}")
            if not (Path.home() / "Desktop").is_dir():
                default = str(Path.home() / f"CrashLens report {stamp}.{fmt}")
            filters = {
                "html": "Web page (*.html)",
                "md": "Markdown (*.md)",
                "json": "JSON (*.json)",
            }
            path, _ = QFileDialog.getSaveFileName(self, "Save the report", default, filters[fmt])
            if not path:
                return None
        target = Path(path)
        if target.suffix.lower().lstrip(".") != fmt:
            target = target.with_name(target.name + f".{fmt}")
        try:
            # The save dialog already asked before replacing an existing file.
            out = write_report(
                self.report, target, fmt, redact=self.redact.isChecked(), overwrite=True
            )
        except OSError as exc:
            self.report_status.setText(f"Couldn't save the report: {exc}")
            return None
        self.report_status.setText(f"Saved: {out}. You can now attach this file to a message.")
        return out

    def copy_summary(self) -> None:
        if not self.report:
            return
        QGuiApplication.clipboard().setText(render(self.report, "md", self.redact.isChecked()))
        self.report_status.setText("Copied. You can now paste it into a message (Ctrl+V).")

    # ================================================================== helpers

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
            QMessageBox.information(self, APP_NAME, "CrashLens couldn't restart as administrator.")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._scan_worker:
            self._scan_worker.cancel()
        for thread, _ in list(self._threads):
            thread.quit()
            thread.wait(3000)
        super().closeEvent(event)
