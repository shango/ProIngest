"""Starting the application. `python -m proingest` with no subcommand lands here.

Kept apart from the window so that everything process-wide happens in one place and in
one order: the application and organisation names first, because `ui/paths.py` asks Qt
for a folder built from them, then the theme, then the window.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from proingest import __version__
from proingest.core import logsetup
from proingest.ui import paths
from proingest.ui.main_window import MainWindow

THEME_FILE = Path(__file__).parent / "theme.qss"


def theme() -> str:
    """The stylesheet, read from the package. Missing is not fatal.

    A tool that will not start because a cosmetic file is absent is worse than one that
    starts looking wrong, and this is the one file in the UI that a packaging mistake
    can leave out of a bundle.
    """
    try:
        return THEME_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_application(argv: list[str] | None = None) -> QApplication:
    """A QApplication with its name set, which is what the app data folder is built from.

    The organisation name is left unset on purpose; `ui/paths.py` says why.
    """
    app = QApplication(argv if argv is not None else [])
    app.setApplicationName(paths.APPLICATION_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(theme())
    return app


def run(argv: list[str] | None = None) -> int:
    """Launch the window and hand control to Qt. Returns the process exit code.

    Logging is set up after the application, because the folder it writes into is built
    from the application name, and before the window, because the window logs while it
    is being built.
    """
    app = build_application(argv)
    logsetup.configure(paths.log_dir())
    window = MainWindow(paths.settings_path())
    window.show()
    return app.exec()
