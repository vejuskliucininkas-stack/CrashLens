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
    # parse_known_args: a windowed app has no console to print usage errors to.
    args, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
