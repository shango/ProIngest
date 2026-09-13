"""The main window: the frame every later chunk hangs its own surface on.

UI_SPEC section 1 is the layout and this builds the whole of it that does not need a
batch: the menu bar with its macOS roles, the toolbar, the bottom dock's three tabs,
the status bar, and the empty state that section 10 specifies. **Every action exists
from the start and the ones with nothing behind them yet are disabled**, each saying in
one line which chunk enables it. A toolbar that grows buttons chunk by chunk hides the
shape of the tool from the person reviewing it; a disabled button says what is coming
and cannot be mistaken for a feature that does nothing.

The window owns no model yet. What it owns is window state, which is restored before it
is shown and saved when it closes.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from proingest import __version__
from proingest.core import settings as core_settings
from proingest.core.models import Batch
from proingest.ui.batch_bar import BatchBar
from proingest.ui.shot_list import ShotListView
from proingest.ui.shot_model import DisplayMode, ShotListModel

WINDOW_TITLE = "ProIngest"

DEFAULT_SIZE = (1500, 900)
"""What the window opens at before it has ever been resized. Wide because the shot list
is the hero and section 2 gives it twelve columns beside the metadata pane."""

EMPTY_STATE_TEXT = "New batch or open one"
"""UI_SPEC section 10, verbatim. The other two empty states arrive with the batch."""

BOTTOM_TABS = ("Issues", "Log", "Deliverables")


class MainWindow(QMainWindow):
    """The application window.

    `settings_path` is passed in rather than looked up, so a test can point the window
    at a temporary file and assert what it remembers without touching the user's own
    settings. `ui/paths.py` is what supplies the real one.
    """

    def __init__(self, settings_path: Path) -> None:
        super().__init__()
        self._settings_path = settings_path
        self._settings = core_settings.load(settings_path)

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*DEFAULT_SIZE)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_bottom_dock()
        self._build_status_bar()
        self._restore_window_state()

    # --- construction ---------------------------------------------------------------

    def _build_actions(self) -> None:
        """Every action in UI_SPEC sections 1 and 4, with the shortcuts it specifies.

        `Ctrl` is written portably and reaches macOS as Cmd on its own (section 4), so
        nothing here is special cased per platform. Where a standard key exists it is
        used, because that also picks up the platform's second binding for free.
        """
        self.action_new = self._action("New", QKeySequence.StandardKey.New)
        self.action_open = self._action("Open...", QKeySequence.StandardKey.Open)
        self.action_save = self._action("Save", QKeySequence.StandardKey.Save)
        self.action_add_turnover = self._action("Add Turnover")
        self.action_scan = self._action("Scan")
        self.action_run = self._action("Run", QKeySequence("Ctrl+R"))
        self.action_stop = self._action("Stop", QKeySequence("Ctrl+."))
        self.action_export = self._action("Export")
        self.action_cycle_display = self._action("Cycle In/Out display", QKeySequence("Ctrl+T"))
        self.action_cycle_display.triggered.connect(self._cycle_display_mode)
        self.action_find = self._action("Find", QKeySequence.StandardKey.Find)
        self.action_find.triggered.connect(lambda: self.batch_bar.focus_search())
        self.action_settings = self._action("Settings", QKeySequence.StandardKey.Preferences)
        self.action_settings.setMenuRole(QAction.MenuRole.PreferencesRole)

        self.action_about = QAction(f"About {WINDOW_TITLE}", self)
        self.action_about.setMenuRole(QAction.MenuRole.AboutRole)
        self.action_about.setEnabled(False)

        self.action_quit = QAction("Quit", self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.setMenuRole(QAction.MenuRole.QuitRole)
        self.action_quit.triggered.connect(self.close)

    def _action(self, text: str, shortcut: QKeySequence | QKeySequence.StandardKey | None = None) -> QAction:
        """One toolbar or menu action, disabled until the chunk that wires it lands.

        Disabled rather than absent: the shape of the tool is in the spec and reviewing
        it is easier against the real toolbar. Nothing here is a no-op that looks live.
        """
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.setEnabled(False)
        return action

    def _build_menus(self) -> None:
        """The system menu bar. macOS moves About, Settings and Quit out of it by role.

        Qt puts the menu bar at the top of the screen on macOS by itself; what it does
        not do by itself is move those three into the application menu, which is why
        each carries a role (UI_SPEC section 11).
        """
        menus = self.menuBar()

        app_menu = menus.addMenu(WINDOW_TITLE)
        app_menu.addAction(self.action_about)
        app_menu.addAction(self.action_settings)
        app_menu.addAction(self.action_quit)

        file_menu = menus.addMenu("File")
        file_menu.addAction(self.action_new)
        file_menu.addAction(self.action_open)
        file_menu.addAction(self.action_save)
        file_menu.addSeparator()
        file_menu.addAction(self.action_export)

        batch_menu = menus.addMenu("Batch")
        batch_menu.addAction(self.action_add_turnover)
        batch_menu.addAction(self.action_scan)
        batch_menu.addSeparator()
        batch_menu.addAction(self.action_run)
        batch_menu.addAction(self.action_stop)

        view_menu = menus.addMenu("View")
        view_menu.addAction(self.action_cycle_display)
        view_menu.addAction(self.action_find)

    def _build_toolbar(self) -> None:
        """Section 1's toolbar, in its three groups, separated as it is drawn there."""
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        for group in (
            (self.action_new, self.action_open, self.action_save),
            (self.action_add_turnover, self.action_scan, self.action_run, self.action_stop),
            (self.action_export, self.action_settings),
        ):
            if toolbar.actions():
                toolbar.addSeparator()
            for action in group:
                toolbar.addAction(action)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

    def _build_central(self) -> None:
        """Two pages: the empty state, and the batch. `set_batch` swaps between them.

        A stack rather than a rebuilt central widget, because the list and its model
        outlive one batch: `ShotListModel.set_batch` is a reset, and the selection
        model, the column widths and the filter all survive it.
        """
        self.shot_model = ShotListModel(self)
        self.shot_list = ShotListView(self.shot_model, self)
        self.batch_bar = BatchBar(self)
        self.batch_bar.display_mode_picked.connect(self.set_display_mode)
        self.batch_bar.search_changed.connect(self.shot_list.filter_by)

        batch_page = QWidget(self)
        batch_layout = QVBoxLayout(batch_page)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setSpacing(0)
        batch_layout.addWidget(self.batch_bar)
        batch_layout.addWidget(self.shot_list)

        self.pages = QStackedWidget(self)
        self.pages.addWidget(self._empty_state())
        self.pages.addWidget(batch_page)
        self.setCentralWidget(self.pages)

    def set_batch(self, batch: Batch) -> None:
        """Show a batch. Until something can open one, this is how a batch gets here."""
        self.shot_model.set_batch(batch)
        self.batch_bar.set_batch_name(batch.name)
        self.pages.setCurrentIndex(1)
        for action in (self.action_cycle_display, self.action_find):
            action.setEnabled(True)

    def set_display_mode(self, mode: DisplayMode) -> None:
        """The one place the display mode changes, whichever surface asked for it."""
        self.shot_model.set_display_mode(mode)
        self.batch_bar.show_display_mode(mode)

    def _cycle_display_mode(self) -> None:
        """Ctrl+T: Frames to Source TC to Record TC and round again (section 4)."""
        self.set_display_mode(self.shot_model.display_mode.next())

    def _empty_state(self) -> QWidget:
        """UI_SPEC section 10, and all the centre holds until a batch is open."""
        central = QWidget(self)
        central.setObjectName("empty_state")
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        label = QLabel(EMPTY_STATE_TEXT, central)
        label.setObjectName("empty_state_text")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        buttons = QWidget(central)
        button_row = QVBoxLayout(buttons)
        button_row.setSpacing(8)
        for text, action in (("New batch", self.action_new), ("Open batch...", self.action_open)):
            button = QPushButton(text, buttons)
            button.clicked.connect(action.trigger)
            # The action is the authority on whether the thing can be done at all, and it
            # follows it both ways: the chunk that enables New has one line to change, not two.
            button.setEnabled(action.isEnabled())
            action.changed.connect(lambda a=action, b=button: b.setEnabled(a.isEnabled()))
            button_row.addWidget(button)
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignCenter)
        return central

    def _build_bottom_dock(self) -> None:
        """Issues, Log and Deliverables, empty until each has something to report."""
        dock = QDockWidget("Details", self)
        dock.setObjectName("bottom_dock")
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        tabs = QTabWidget(dock)
        tabs.setObjectName("bottom_tabs")
        for name in BOTTOM_TABS:
            placeholder = QLabel(f"No {name.lower()} yet", tabs)
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tabs.addTab(placeholder, name)
        dock.setWidget(tabs)

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.bottom_dock = dock
        self.bottom_tabs = tabs

    def _build_status_bar(self) -> None:
        """Section 7's progress, hidden until a run has something to report."""
        self.progress = QProgressBar(self)
        self.progress.setObjectName("status_progress")
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage(f"{WINDOW_TITLE} {__version__}")

    # --- what the window remembers ---------------------------------------------------

    def _restore_window_state(self) -> None:
        """Geometry and dock arrangement from the last run, if there was one.

        Qt's own blobs, base64 encoded to survive JSON. A blob written by a different
        Qt version is refused by Qt itself rather than raising, so a stale one leaves
        the default size rather than failing a launch.
        """
        if self._settings.window_geometry:
            self.restoreGeometry(QByteArray(b64decode(self._settings.window_geometry)))
        if self._settings.window_state:
            self.restoreState(QByteArray(b64decode(self._settings.window_state)))

    def save_window_state(self) -> None:
        """Write what the window looks like now. Called on close."""
        self._settings.window_geometry = b64encode(self.saveGeometry().data()).decode()
        self._settings.window_state = b64encode(self.saveState().data()).decode()
        core_settings.save(self._settings, self._settings_path)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Save the window state on the way out.

        Nothing here can refuse the close yet. Once a batch can be dirty this is where
        the unsaved changes prompt goes, which is why the override exists now.
        """
        self.save_window_state()
        super().closeEvent(event)
