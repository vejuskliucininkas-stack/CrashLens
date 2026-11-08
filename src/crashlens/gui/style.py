"""Colours and the Qt style sheet (a calm, Windows 11-like look)."""

from __future__ import annotations

from crashlens.core.models import CheckStatus, Severity

ACCENT = "#0067c0"

SEVERITY_COLORS = {
    Severity.CRITICAL: "#8b1a1a",
    Severity.HIGH: "#c42b1c",
    Severity.MEDIUM: "#b4690e",
    Severity.LOW: "#0f6cbd",
    Severity.INFO: "#616161",
}

STATUS_TEXT = {
    CheckStatus.OK: ("OK", "#0f7b0f"),
    CheckStatus.ISSUES: ("Needs attention", "#b4690e"),
    CheckStatus.UNAVAILABLE: ("Not available", "#616161"),
    CheckStatus.ERROR: ("Error", "#c42b1c"),
}

QSS = f"""
QWidget {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; }}
QMainWindow, #Content {{ background: #f3f3f3; }}
#Sidebar {{ background: #ebebeb; border: none; }}
#Sidebar QListWidget {{ background: transparent; border: none; outline: none; }}
#Sidebar QListWidget::item {{ padding: 10px 14px; margin: 2px 8px; border-radius: 6px;
    color: #1a1a1a; }}
#Sidebar QListWidget::item:selected {{ background: #ffffff; color: {ACCENT};
    font-weight: 600; }}
#Sidebar QListWidget::item:hover:!selected {{ background: #e0e0e0; }}
#AppTitle {{ font-size: 15pt; font-weight: 700; padding: 18px 16px 8px 18px; }}
#PageTitle {{ font-size: 18pt; font-weight: 600; }}
#Subtle {{ color: #5f5f5f; }}
#Card {{ background: #ffffff; border: 1px solid #e5e5e5; border-radius: 8px; }}
#Banner {{ background: #fff4ce; border: 1px solid #f2d888; border-radius: 6px; }}
#DemoBanner {{ background: #e8f1fb; border: 1px solid #b6d3f2; border-radius: 6px; }}
QPushButton {{ background: #ffffff; border: 1px solid #d1d1d1; border-radius: 5px;
    padding: 6px 14px; }}
QPushButton:hover {{ background: #f6f6f6; }}
QPushButton:disabled {{ color: #a0a0a0; background: #f5f5f5; }}
QPushButton#Primary {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT};
    font-weight: 600; }}
QPushButton#Primary:hover {{ background: #1975c5; }}
QPushButton#Primary:disabled {{ background: #9cc0e4; border-color: #9cc0e4; }}
QListWidget, QTableWidget, QTextBrowser, QPlainTextEdit {{ background: #ffffff;
    border: 1px solid #e5e5e5; border-radius: 6px; }}
QListWidget::item {{ padding: 0px 4px; }}
QListWidget::item:selected {{ background: #e5f0fb; color: #1a1a1a; }}
QHeaderView::section {{ background: #fafafa; border: none; border-bottom: 1px solid #e5e5e5;
    padding: 6px; font-weight: 600; }}
QProgressBar {{ border: none; background: #e5e5e5; border-radius: 3px; height: 6px;
    text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
"""


def finding_html_styles() -> str:
    return (
        "<style>body{font-family:'Segoe UI',sans-serif;font-size:10pt;color:#1a1a1a}"
        "h2{font-size:14pt;margin:0 0 4px}.sev{font-weight:700;font-size:9pt}"
        ".muted{color:#5f5f5f}li{margin-bottom:3px}</style>"
    )
