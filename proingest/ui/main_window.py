"""The main window: the frame every later chunk hangs its own surface on.

UI_SPEC section 1 is the layout and this builds the whole of it that does not need a
batch: the menu bar with its macOS roles, the toolbar, the bottom dock's three tabs,
the status bar, and the empty state that section 10 specifies. **Every action exists
from the start and the ones with nothing behind them yet are disabled**, each saying in
one line which chunk enables it. A toolbar that grows buttons chunk by chunk hides the
shape of the tool from the person reviewing it; a disabled button says what is coming
and cannot be mistaken for a feature that does nothing.

What the window owns is the batch and the file it came from (M5.4), and window state,
which is restored before it is shown and saved when it closes. **Every dialog it opens
is its own method**, so a test can answer one: an offscreen modal is a hung suite rather
than a failed assertion.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from proingest import __version__
from proingest.core import batchfile, qc, scan
from proingest.core import settings as core_settings
from proingest.core.models import DEFAULT_BATCH_NAME, Batch, MediaInfo, ShotRow, Turnover
from proingest.ui.autosave import AutoSaver
from proingest.ui.batch_bar import BatchBar
from proingest.ui.issues import IssuesDock
from proingest.ui.scanner import Scanner
from proingest.ui.shot_list import ShotListView
from proingest.ui.shot_model import DisplayMode, ShotListModel

WINDOW_TITLE = "ProIngest"

DEFAULT_SIZE = (1500, 900)
"""What the window opens at before it has ever been resized. Wide because the shot list
is the hero and section 2 gives it twelve columns beside the metadata pane."""

EMPTY_STATE_TEXT = "New batch or open one"
NO_TURNOVERS_TEXT = "Add a turnover folder to begin"
NO_ROWS_TEXT = "No clips found in timeline"
"""UI_SPEC section 10's three states, verbatim. The third is shown with a link to the
Issues dock beside it, because a timeline that produced no rows always said why there."""

ISSUES_LINK = "See the Issues dock"

BATCH_FILTER = "ProIngest batch (*.pibatch)"

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
        self.action_new.triggered.connect(self.new_batch)
        self.action_new.setEnabled(True)
        self.action_open = self._action("Open...", QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.open_batch)
        self.action_open.setEnabled(True)
        self.action_save = self._action("Save", QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self.save_batch)
        self.action_add_turnover = self._action("Add Turnover")
        self.action_add_turnover.triggered.connect(self.add_turnover)
        self.action_scan = self._action("Scan")
        self.action_scan.triggered.connect(self.scan_unscanned)
        self.action_run = self._action("Run", QKeySequence("Ctrl+R"))
        self.action_stop = self._action("Stop", QKeySequence("Ctrl+."))
        self.action_toggle_skip = self._action("Skip Shot", QKeySequence("Ctrl+K"))
        self.action_toggle_skip.triggered.connect(lambda: self.shot_list.toggle_skip())
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
        batch_menu.addAction(self.action_toggle_skip)
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

        The batch page has a stack of its own, because two of section 10's three empty
        states are states of an *open* batch: the batch bar stays, and what a batch with
        no turnovers has nothing to show in is the list.
        """
        self.shot_model = ShotListModel(self)
        self.shot_list = ShotListView(self.shot_model, self)
        self.autosave = AutoSaver(self)
        self.shot_model.row_edited.connect(lambda _row: self.autosave.schedule())
        # A commit re-runs that row's rules (M5.3), so what the dock is showing about
        # that row is what just changed. Rebuilt whole: the results are a list short
        # enough that finding the ones that moved costs more than redrawing them.
        self.shot_model.row_edited.connect(lambda _row: self.issues.show_batch(self.batch))
        self.autosave.saved.connect(lambda path: self.statusBar().showMessage(f"Saved {path.name}"))
        self.batch_bar = BatchBar(self)
        self.batch_bar.display_mode_picked.connect(self.set_display_mode)
        self.batch_bar.search_changed.connect(self.shot_list.filter_by)
        self.batch_bar.delivery_root_clicked.connect(self.choose_delivery_root)

        self.scanner = Scanner(self)
        self.scanner.scanned.connect(self._take_scanned)
        self.scanner.started_folder.connect(self._say_scanning)
        self.scanner.finished.connect(self._scan_finished)

        self.list_pages = QStackedWidget(self)
        self.list_pages.addWidget(self.shot_list)
        self.list_pages.addWidget(self._list_empty_state())

        batch_page = QWidget(self)
        batch_layout = QVBoxLayout(batch_page)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setSpacing(0)
        batch_layout.addWidget(self.batch_bar)
        batch_layout.addWidget(self.list_pages)

        self.pages = QStackedWidget(self)
        self.pages.addWidget(self._empty_state())
        self.pages.addWidget(batch_page)
        self.setCentralWidget(self.pages)

        self._batch_path: Path | None = None
        self._batch_open = False

    # --- the batch lifecycle ----------------------------------------------------------

    def set_batch(self, batch: Batch, path: Path | None = None) -> None:
        """Show a batch, and autosave it to `path` when it is edited.

        `path` is where the batch file lives, and a batch made by New has none until it
        is saved. Until then an edited batch has its edits held by the autosaver rather
        than written, and the window is what asks about them before it closes.
        """
        self.shot_model.set_batch(batch)
        self.autosave.watch(batch, path)
        self._batch_path = path
        self._batch_open = True
        self.batch_bar.set_batch_name(batch.name)
        self.batch_bar.show_delivery_root(batch.delivery_root)
        self.issues.show_batch(batch)
        self.pages.setCurrentIndex(1)
        self._update_state()

    @property
    def batch(self) -> Batch:
        """The open batch. The model is the one that holds it; this is where to ask."""
        return self.shot_model.batch

    @property
    def batch_path(self) -> Path | None:
        """Where the open batch is saved, or None when it has never been saved."""
        return self._batch_path

    def new_batch(self) -> None:
        """An empty batch with no file, waiting for a turnover (section 10)."""
        if not self._may_abandon_current():
            return
        self.set_batch(Batch())

    def open_batch(self) -> None:
        """Read a `.pibatch`, back it up, and check that its two roots are still there."""
        if not self._may_abandon_current():
            return
        path = self.ask_open_path()
        if path is None:
            return
        try:
            loaded = batchfile.load(path)
        except batchfile.BatchFileError as exc:
            self.report_problem("Could not open batch", str(exc))
            return
        # The copy is taken on open rather than on save, so the file being backed up is
        # the last one the editor saw whole rather than the one a bad save just wrote.
        batchfile.backup(path)
        self.set_batch(loaded, path)
        self._check_roots(loaded)

    def save_batch(self) -> bool:
        """Write the batch, asking where the first time. True when something was written.

        Explicit rather than routed through the autosaver: Save is the one write the
        editor is waiting on, so a failure is reported here instead of being logged and
        left pending the way an autosave is.
        """
        if not self._batch_open:
            return False
        path = self._batch_path or self.ask_save_path(self.batch.name)
        if path is None:
            return False
        if self._batch_path is None and self.batch.name == DEFAULT_BATCH_NAME:
            # The file the editor just named is the only name this batch has been given,
            # and the name is not decoration: the QC log and the tracker are named from
            # it, so a batch saved as `melt_day1` must not export as `untitled`.
            self.batch.name = path.stem
            self.batch_bar.set_batch_name(self.batch.name)
        try:
            written = batchfile.save(self.batch, path)
        except OSError as exc:
            self.report_problem("Could not save batch", str(exc))
            return False
        self._batch_path = written
        self.autosave.adopt(written)
        self.statusBar().showMessage(f"Saved {written.name}")
        return True

    def choose_delivery_root(self) -> None:
        """The batch bar's path, click to change (UI_SPEC section 13)."""
        if not self._batch_open:
            return
        chosen = self.ask_folder("Delivery root", self.batch.delivery_root)
        if chosen is None:
            return
        self.batch.delivery_root = chosen
        self.batch_bar.show_delivery_root(chosen)
        self.autosave.schedule()

    def _may_abandon_current(self) -> bool:
        """Write or discard what the open batch still owes, and say whether to go on."""
        self.autosave.flush()
        if not self.autosave.pending:
            return True
        answer = self.ask_unsaved()
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Discard:
            return True
        return self.save_batch()

    def _check_roots(self, batch: Batch) -> None:
        """A root that has gone missing is reported and the chooser reopens (section 13).

        Never silently recreated: writing a delivery tree into a stale path is how
        deliverables get lost, and a source root that is not there is a mount that has
        not come up rather than a folder to make.
        """
        for label, root in (("Source root", batch.source_root), ("Delivery root", batch.delivery_root)):
            if root is None or root.is_dir():
                continue
            self.report_problem(f"{label} is missing", f"{root} is not there any more.")
            chosen = self.ask_folder(label, None)
            if chosen is None:
                continue
            if label.startswith("Source"):
                batch.source_root = chosen
            else:
                batch.delivery_root = chosen
                self.batch_bar.show_delivery_root(chosen)
            self.autosave.schedule()

    # --- adding and scanning turnovers ------------------------------------------------

    def add_turnover(self) -> None:
        """Pick a turnover folder under the source root and scan it straight away.

        Straight away rather than waiting for Scan: a folder that is added and shows
        nothing until a second button is pressed is a dead click. Scan is what re-tries
        a turnover that came back with no rows.

        Adding from outside the source root is allowed and moves the root, because the
        root is a starting point and not a fence (UI_SPEC section 13).
        """
        if not self._batch_open or self.scanner.busy:
            return
        folder = self.ask_folder("Add Turnover", self.batch.source_root)
        if folder is None:
            return
        if any(turnover.folder == folder for turnover in self.batch.turnovers):
            self.report_problem("Already added", f"{folder.name} is already in this batch.")
            return
        self.batch.source_root = folder.parent
        self._scan([(folder, self._next_turnover_id())])

    def scan_unscanned(self) -> None:
        """Scan the turnovers that have no rows. The retry, and nothing else.

        **A turnover that has rows is never re-scanned here**, because a scan rebuilds
        rows and the rows carry the editor's In/Out, shot code and notes. What this is
        for is the turnover whose mount was down or whose timeline had not finished
        downloading: fix it, press Scan, and it fills in. Re-scanning a scanned turnover
        without discarding the edits on it is OQ-48.
        """
        if not self._batch_open or self.scanner.busy:
            return
        self._scan([(t.folder, t.turnover_id) for t in self._unscanned()])

    def _unscanned(self) -> list[Turnover]:
        return [t for t in self.batch.turnovers if not self.batch.rows_for(t.turnover_id)]

    def _next_turnover_id(self) -> str:
        """`t1`, `t2`, and so on, which is what `scan.scan_batch` numbers them.

        Counted past the highest in use rather than off the length, so removing the
        second of three turnovers cannot hand the next one an id a row still points at.
        """
        used = {t.turnover_id for t in self.batch.turnovers}
        position = len(used) + 1
        while f"t{position}" in used:
            position += 1
        return f"t{position}"

    def _scan(self, folders: list[tuple[Path, str]]) -> None:
        """Hand the folders to the worker thread and show that something is happening."""
        if not folders:
            return
        settings = scan.ScanSettings(
            project_rate=self.batch.project_rate,
            rules=qc.settings_for(self.batch),
        )
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self._update_state()
        self.scanner.start(folders, settings, self.batch.probe_cache)

    def _say_scanning(self, folder: Path) -> None:
        self.statusBar().showMessage(f"Scanning {folder.name}...")

    def _take_scanned(
        self, turnover: Turnover, rows: list[ShotRow], probe_cache: dict[str, MediaInfo]
    ) -> None:
        """One folder's result, back on the UI thread, folded into the batch.

        The probe cache is merged rather than replaced: the worker started from a copy,
        so anything the UI thread learned meanwhile is still ours to keep.

        QC-011 is the reason the batch rules re-run rather than only the new rows': a
        duplicate clip name is a fact about every row in the batch, and a turnover
        arriving can create one in a turnover that was already there.
        """
        batch = self.batch
        existing = next(
            (i for i, t in enumerate(batch.turnovers) if t.turnover_id == turnover.turnover_id),
            None,
        )
        if existing is None:
            batch.turnovers.append(turnover)
        else:
            # Only a turnover with no rows is ever scanned twice, so there is nothing to
            # take out of `batch.rows` here: what is replaced is the turnover's own QC.
            batch.turnovers[existing] = turnover
        batch.rows.extend(rows)
        batch.probe_cache.update(probe_cache)
        qc.apply_batch_rules(batch, qc.settings_for(batch))
        self.shot_model.set_batch(batch)
        self.issues.show_batch(batch)
        self.autosave.schedule()
        self._update_state()

    def _scan_finished(self) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.statusBar().showMessage(f"{len(self.batch.rows)} shots")
        self._update_state()

    # --- what is enabled, and what the centre shows -----------------------------------

    def _update_state(self) -> None:
        """One place that decides both, because both answer the same three questions.

        Called after anything that can change what the batch holds, rather than from
        each of those places: an action left enabled over an empty batch is the kind of
        thing that only shows up when somebody presses it.
        """
        open_batch = self._batch_open
        scanning = self.scanner.busy
        for action in (self.action_cycle_display, self.action_find, self.action_toggle_skip):
            action.setEnabled(open_batch)
        self.action_save.setEnabled(open_batch)
        self.action_add_turnover.setEnabled(open_batch and not scanning)
        self.action_scan.setEnabled(open_batch and not scanning and bool(self._unscanned()))

        if not open_batch:
            return
        if self.batch.rows:
            self.list_pages.setCurrentIndex(0)
            return
        self.list_empty_text.setText(
            NO_TURNOVERS_TEXT
            if not self.batch.turnovers
            else f'{NO_ROWS_TEXT}. <a href="#issues">{ISSUES_LINK}</a>'
        )
        self.list_pages.setCurrentIndex(1)

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

    def _list_empty_state(self) -> QWidget:
        """Section 10's other two states, which are states of an open batch.

        One label rather than two pages: the two differ by a sentence, and a stack of
        near identical widgets is two places to change the wording in.
        """
        central = QWidget(self)
        central.setObjectName("list_empty_state")
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.list_empty_text = QLabel(NO_TURNOVERS_TEXT, central)
        self.list_empty_text.setObjectName("list_empty_state_text")
        self.list_empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_empty_text.linkActivated.connect(self._show_issues)
        layout.addWidget(self.list_empty_text)
        return central

    def _show_issues(self) -> None:
        """Bring the Issues tab up, which is where the link in section 10 points."""
        self.bottom_dock.setVisible(True)
        self.bottom_tabs.setCurrentIndex(BOTTOM_TABS.index("Issues"))

    # --- the dialogs, each its own method so a test can answer it ---------------------

    def ask_open_path(self) -> Path | None:
        """Which `.pibatch` to open."""
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Open Batch", self._start_folder(None), BATCH_FILTER
        )
        return self._remember(Path(chosen)) if chosen else None

    def ask_save_path(self, suggested_name: str) -> Path | None:
        """Where to save a batch that has never been saved."""
        start = Path(self._start_folder(None)) / f"{suggested_name}{batchfile.SUFFIX}"
        chosen, _filter = QFileDialog.getSaveFileName(
            self, "Save Batch", str(start), BATCH_FILTER
        )
        return self._remember(Path(chosen)) if chosen else None

    def ask_folder(self, title: str, start: Path | None) -> Path | None:
        """One folder: a turnover, or either of the two roots."""
        chosen = QFileDialog.getExistingDirectory(self, title, self._start_folder(start))
        return self._remember(Path(chosen)) if chosen else None

    def ask_unsaved(self) -> QMessageBox.StandardButton:
        """Save, Discard or Cancel, for a batch with edits and no file yet."""
        return QMessageBox.warning(
            self,
            "Unsaved batch",
            "This batch has never been saved. Save it before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

    def report_problem(self, title: str, text: str) -> None:
        """Something the editor has to know about and can do something about."""
        QMessageBox.warning(self, title, text)

    def _start_folder(self, preferred: Path | None) -> str:
        """Where a chooser opens: the batch's own root, else the last one browsed to.

        Empty when there has been neither, which opens wherever the platform would.
        **Nothing here guesses at a Drive mount** (UI_SPEC section 11): a wrong guess
        opens somewhere plausible and empty and reads as the folder being wrong.
        """
        if preferred is not None and preferred.is_dir():
            return str(preferred)
        return self._settings.last_folder

    def _remember(self, chosen: Path) -> Path:
        """Keep where that chooser ended up, so the next one opens there."""
        folder = chosen if chosen.is_dir() else chosen.parent
        self._settings.last_folder = str(folder)
        return chosen

    def _build_bottom_dock(self) -> None:
        """Issues (M5.4), then Log and Deliverables, empty until each has something."""
        dock = QDockWidget("Details", self)
        dock.setObjectName("bottom_dock")
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        tabs = QTabWidget(dock)
        tabs.setObjectName("bottom_tabs")
        self.issues = IssuesDock(tabs)
        self.issues.row_activated.connect(self.shot_list.select_row)
        for name in BOTTOM_TABS:
            if name == "Issues":
                tabs.addTab(self.issues, name)
                continue
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
        """Stop waiting, ask about what could not be written, and stop the scan.

        The flush is first because an edit made a second before the window closed is not
        one the editor expects to lose, and what is still pending after it is a batch
        that has never been saved: the one case the editor has to answer for.

        The scan thread is stopped last and it is waited on, because a `QThread` still
        running when its owner is collected is a crash on the way out.
        """
        if not self._may_abandon_current():
            event.ignore()
            return
        self.scanner.shutdown()
        self.save_window_state()
        super().closeEvent(event)
