"""Light and dark themes, text sizes, and the Qt style sheet."""

from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from crashlens.core.models import CheckStatus, Severity
from crashlens.core.settings import Settings

LIGHT = {
    "bg": "#f4f5f7",
    "side": "#ffffff",
    "card": "#ffffff",
    "text": "#16181d",
    "muted": "#5b6270",
    "border": "#e1e4ea",
    "hover": "#eef1f5",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_soft": "#e8effe",
    "accent_text": "#ffffff",
    "banner": "#fff7e0",
    "banner_border": "#f3dc9a",
    "ok": "#15803d",
    "warn": "#b45309",
    "bad": "#c2261c",
}

DARK = {
    "bg": "#121418",
    "side": "#181b20",
    "card": "#1e2228",
    "text": "#eef0f3",
    "muted": "#a2a9b5",
    "border": "#2e333b",
    "hover": "#272c33",
    "accent": "#5b8cff",
    "accent_hover": "#7aa2ff",
    "accent_soft": "#1f2a44",
    "accent_text": "#0b0d10",
    "banner": "#2f2814",
    "banner_border": "#5a4a1c",
    "ok": "#4ade80",
    "warn": "#fbbf24",
    "bad": "#f87171",
}

SEVERITY = {
    "light": {
        Severity.CRITICAL: "#b91c1c",
        Severity.HIGH: "#dc2626",
        Severity.MEDIUM: "#d97706",
        Severity.LOW: "#2563eb",
        Severity.INFO: "#6b7280",
    },
    "dark": {
        Severity.CRITICAL: "#f87171",
        Severity.HIGH: "#fb7185",
        Severity.MEDIUM: "#fbbf24",
        Severity.LOW: "#7aa2ff",
        Severity.INFO: "#9ca3af",
    },
}

SIZES = {"normal": 11, "large": 13, "xlarge": 15}

STATUS_TEXT = {
    CheckStatus.OK: ("OK", "ok"),
    CheckStatus.ISSUES: ("Needs attention", "warn"),
    CheckStatus.UNAVAILABLE: ("Not available", "muted"),
    CheckStatus.ERROR: ("Error", "bad"),
}

_QSS = Template("""
* { font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif; }
QWidget { font-size: ${pt}pt; color: $text; }
QMainWindow, #Content, #Page, QScrollArea, QScrollArea > QWidget > QWidget { background: $bg; }
QScrollArea { border: none; }
QDialog { background: $bg; }
#Sidebar { background: $side; border-right: 1px solid $border; }
#Brand { font-size: ${h2}pt; font-weight: 700; }
#Tagline { color: $muted; font-size: ${small}pt; }
#Nav { background: transparent; border: none; outline: none; }
#Nav::item { padding: 13px 16px; margin: 3px 12px; border-radius: 10px; color: $text; }
#Nav::item:selected { background: $accent_soft; color: $accent; font-weight: 600; }
#Nav::item:hover:!selected { background: $hover; }
#H1 { font-size: ${h1}pt; font-weight: 700; }
#H2 { font-size: ${h2}pt; font-weight: 600; }
#H3 { font-size: ${h3}pt; font-weight: 600; }
#Muted { color: $muted; }
#Small { color: $muted; font-size: ${small}pt; }
#Badge { font-size: ${small}pt; font-weight: 700; }
#Card { background: $card; border: 1px solid $border; border-radius: 14px; }
#Hero { background: $card; border: 1px solid $border; border-radius: 18px; }
#Banner { background: $banner; border: 1px solid $banner_border; border-radius: 12px; }
QPushButton { background: $card; color: $text; border: 1px solid $border; border-radius: 10px;
    padding: 10px 18px; font-weight: 500; }
QPushButton:hover { background: $hover; }
QPushButton:disabled { color: $muted; background: $bg; }
QPushButton#Primary { background: $accent; color: $accent_text; border: 1px solid $accent;
    font-weight: 600; }
QPushButton#Primary:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#Primary:disabled { background: $border; border-color: $border; color: $muted; }
QPushButton#Big { background: $accent; color: $accent_text; border: none; border-radius: 14px;
    font-size: ${h2}pt; font-weight: 700; padding: 18px 44px; }
QPushButton#Big:hover { background: $accent_hover; }
QPushButton#Big:disabled { background: $border; color: $muted; }
QPushButton#Link { background: transparent; border: none; color: $accent; padding: 6px 4px;
    font-weight: 600; text-align: left; }
QPushButton#Link:hover { text-decoration: underline; }
QPushButton#Choice { padding: 14px 20px; border-radius: 12px; }
QPushButton#Choice:checked { border: 2px solid $accent; background: $accent_soft; color: $accent;
    font-weight: 700; }
QCheckBox { spacing: 10px; }
QComboBox { background: $card; border: 1px solid $border; border-radius: 10px; padding: 8px 12px; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { width: 0; height: 0; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid $muted; margin-right: 10px; }
QComboBox QAbstractItemView { background: $card; color: $text; border: 1px solid $border;
    selection-background-color: $accent_soft; selection-color: $text; }
QListWidget, QTableWidget, QTextBrowser, QPlainTextEdit { background: $card; color: $text;
    border: 1px solid $border; border-radius: 10px; }
QListWidget::item { padding: 2px 4px; }
QListWidget::item:selected { background: $accent_soft; color: $text; }
QTableWidget { gridline-color: $border; }
QHeaderView::section { background: $side; color: $text; border: none;
    border-bottom: 1px solid $border; padding: 8px; font-weight: 600; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: $muted; padding: 10px 16px;
    border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: $text; border-bottom: 2px solid $accent; font-weight: 600; }
QProgressBar { border: none; background: $border; border-radius: 5px; max-height: 10px; }
QProgressBar::chunk { background: $accent; border-radius: 5px; }
QToolTip { background: $card; color: $text; border: 1px solid $border; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
""")

_state = {"mode": "light", "pt": SIZES["normal"]}


def system_is_dark() -> bool:
    try:
        hints = QGuiApplication.styleHints()
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def resolve_mode(theme: str) -> str:
    if theme == "dark":
        return "dark"
    if theme == "light":
        return "light"
    return "dark" if system_is_dark() else "light"


def mode() -> str:
    return _state["mode"]


def colors() -> dict[str, str]:
    return DARK if _state["mode"] == "dark" else LIGHT


def color(name: str) -> str:
    return colors()[name]


def severity_color(sev: Severity) -> str:
    return SEVERITY[_state["mode"]][sev]


def base_pt() -> int:
    return _state["pt"]


def build_qss(mode_name: str, pt: int) -> str:
    c = DARK if mode_name == "dark" else LIGHT
    return _QSS.substitute(
        c,
        pt=pt,
        small=max(pt - 1, 9),
        h3=round(pt * 1.2),
        h2=round(pt * 1.45),
        h1=round(pt * 2.0),
    )


def _palette(c: dict[str, str]) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: c["bg"],
        QPalette.ColorRole.WindowText: c["text"],
        QPalette.ColorRole.Base: c["card"],
        QPalette.ColorRole.AlternateBase: c["hover"],
        QPalette.ColorRole.Text: c["text"],
        QPalette.ColorRole.Button: c["card"],
        QPalette.ColorRole.ButtonText: c["text"],
        QPalette.ColorRole.Highlight: c["accent"],
        QPalette.ColorRole.HighlightedText: c["accent_text"],
        QPalette.ColorRole.ToolTipBase: c["card"],
        QPalette.ColorRole.ToolTipText: c["text"],
        QPalette.ColorRole.PlaceholderText: c["muted"],
        QPalette.ColorRole.Link: c["accent"],
    }
    for role, value in roles.items():
        p.setColor(role, QColor(value))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    return p


def apply(app: QApplication, settings: Settings) -> str:
    """Apply theme and text size to the whole app. Returns 'light' or 'dark'."""
    mode_name = resolve_mode(settings.theme)
    pt = SIZES.get(settings.text_size, SIZES["normal"])
    _state.update(mode=mode_name, pt=pt)
    app.setStyle("Fusion")
    app.setPalette(_palette(colors()))
    font = QFont(app.font())
    font.setPointSize(pt)
    app.setFont(font)
    app.setStyleSheet(build_qss(mode_name, pt))
    return mode_name


def html_styles() -> str:
    c = colors()
    return (
        f"<style>body{{font-size:{base_pt()}pt;color:{c['text']}}}"
        f"h2{{font-size:{round(base_pt() * 1.3)}pt;margin:0 0 6px}}"
        f".muted{{color:{c['muted']}}}li{{margin-bottom:4px}}"
        f"a{{color:{c['accent']}}}</style>"
    )
