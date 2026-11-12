"""Desktop app entry point."""

from __future__ import annotations

import argparse
import contextlib
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from crashlens import APP_NAME
from crashlens.core.settings import Settings
from crashlens.environment import build_environment
from crashlens.gui import logo
from crashlens.gui import style as theme
from crashlens.gui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crashlens-gui")
    parser.add_argument("--demo", action="store_true", help="use sample data")
    parser.add_argument("--dry-run", action="store_true", help="never run repairs for real")
    parser.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    # parse_known_args: a windowed app has no console to print usage errors to.
    args, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    if args.selftest:
        return _selftest()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(logo.icon())
    try:
        env = build_environment(demo=args.demo, dry_run=args.dry_run)
        settings = Settings.load(env.settings_path)
        theme.apply(app, settings)
        window = MainWindow(env, settings)
    except Exception as exc:  # show the problem instead of closing silently
        QMessageBox.critical(
            None,
            APP_NAME,
            f"CrashLens could not start.\n\n{type(exc).__name__}: {exc}\n\n"
            "Please send a screenshot of this message.",
        )
        return 1
    # Follow Windows when it switches between light and dark (Qt 6.5+).
    with contextlib.suppress(AttributeError):
        app.styleHints().colorSchemeChanged.connect(
            lambda *_: window.apply_look() if window.settings.theme == "system" else None
        )
    window.show()
    return app.exec()


def _selftest() -> int:
    """Open the window offscreen, run a demo check, close. Used by the .exe build."""
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QTimer

    app = QApplication.instance() or QApplication([sys.argv[0]])
    tmp = Path(tempfile.mkdtemp(prefix="crashlens-selftest-"))
    env = build_environment(
        demo=True, audit_path=tmp / "audit.log", settings_path=tmp / "settings.json"
    )
    settings = Settings(welcomed=True)
    theme.apply(app, settings)
    window = MainWindow(env, settings)
    window.show()
    result = {"code": 1}

    def done(report) -> None:
        result["code"] = 0 if report.findings and window.cards else 3
        app.quit()

    window.scan_completed.connect(done)
    QTimer.singleShot(0, window.start_scan)
    QTimer.singleShot(60000, app.quit)
    app.exec()
    return result["code"]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
