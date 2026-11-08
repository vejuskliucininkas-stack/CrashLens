"""Desktop app entry point."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from crashlens import APP_NAME
from crashlens.environment import build_environment
from crashlens.gui.main_window import MainWindow
from crashlens.gui.style import QSS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crashlens-gui")
    parser.add_argument("--demo", action="store_true", help="use sample data")
    parser.add_argument("--dry-run", action="store_true", help="never run repairs for real")
    # parse_known_args: a windowed app has no console to print usage errors to.
    args, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    try:
        window = MainWindow(build_environment(demo=args.demo, dry_run=args.dry_run))
    except Exception as exc:  # show the problem instead of closing silently
        QMessageBox.critical(
            None,
            APP_NAME,
            f"CrashLens could not start.\n\n{type(exc).__name__}: {exc}\n\n"
            "Please send a screenshot of this message.",
        )
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
