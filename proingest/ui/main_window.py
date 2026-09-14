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

**A run is `ui/run_controller.py`'s and the pool under it is `ui/runner.py`'s**, in the
same way a scan is `ui/scanner.py`'s: what is left here is the batch, the surfaces, and
which of them a collaborator is allowed to ask for. `show_results`, `show_issues`,
`update_state` and `settings` are public for that reason and for no other.
"""

from __future__ import annotations

import logging
from base64 import b64decode, b64encode
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
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
from proingest.core import batchfile, camdata, clf, qc, scan
from proingest.core import settings as core_settings
from proingest.core.models import (
    DEFAULT_BATCH_NAME,
    Batch,
    FrameRate,
    MediaInfo,
    ShotRow,
    Turnover,
)
from proingest.ui import metadata, settings_form, toolbar_help
from proingest.ui.autosave import AutoSaver
from proingest.ui.batch_bar import BatchBar
from proingest.ui.issues import IssuesDock
from proingest.ui.log_view import LogView
from proingest.ui.metadata_pane import MetadataPane
from proingest.ui.run_controller import RunController
from proingest.ui.run_strip import RunStrip
from proingest.ui.scanner import Scanner
from proingest.ui.settings_dialog import SettingsDialog
from proingest.ui.shot_list import ShotListView
from proingest.ui.shot_model import DisplayMode, ShotListModel

log = logging.getLogger(__name__)

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
EDL_FILTER = "Final EDL (*.edl)"

BOTTOM_TABS = ("Issues", "Log", "Deliverables")

SETTINGS_APPLIED = "Settings applied; the batch has been re-checked"

INGEST_TITLE = "Colour session ingested"
INGEST_READ = "Read from {name}, which holds {events} events."
INGEST_MIXED_RATES = "This turnover carries more than one rate; the EDL was read at {rate}."
NO_RATE_TITLE = "Nothing to read the EDL at"
NO_RATE = "No row in {name} has media, so there is no rate to read the EDL's timecode at. Scan it first."
CANNOT_READ_SESSION = "Could not read the colour session"
WHICH_TURNOVER = "Ingest a colour session into which turnover?"


METADATA_WIDTH = 360
"""What the pane opens at on a window that has never been arranged."""

METADATA_MIN_WIDTH = 260
"""How narrow the pane can be dragged. Section 1 calls it a fixed width reading surface.

Narrow enough to give the list most of a 1500 pixel window and wide enough that a
`label  value` line does not wrap on every field. Paths elide rather than wrap, so this
is about the values that are words.
"""


def turnover_labels(turnovers: Sequence[Turnover]) -> list[str]:
    """Folder names, with the parent folder added where two turnovers share one."""
    names = [turnover.folder.name for turnover in turnovers]
    return [
        f"{turnover.folder.parent.name}/{name}" if names.count(name) > 1 else name
        for turnover, name in zip(turnovers, names, strict=True)
    ]


def unsaved_question(path: Path | None) -> str:
    """What to ask about pending edits: no file yet, or a file the last write missed."""
    if path is None:
        return "This batch has never been saved. Save it before closing?"
    return f"The last save to {path.name} failed and the edits are still unsaved. Save it before closing?"


def ingest_text(report: clf.IngestReport, turnover_name: str, rates: Sequence[FrameRate]) -> str:
    """What one ingest did, in the words `proingest run --color-session` prints.

    The counts and the three labelled lists come off the report itself
    (`IngestReport.counts` and `notices`), so the two surfaces cannot drift apart. What
    is said here and not there is the turnover's folder name, because the window ingests
    one turnover rather than all of them.
    """
    lines = [
        f"{turnover_name}: {report.counts}",
        "",
        INGEST_READ.format(name=report.edl_path.name, events=report.events),
    ]
    if len({str(rate) for rate in rates}) > 1:
        lines.append(INGEST_MIXED_RATES.format(rate=rates[0]))
    for label, names in report.notices():
        lines += ["", f"{label}: {', '.join(names)}"]
    return "\n".join(lines)


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
        # Before anything is built, because the window logs while it is being built and
        # the log level is one of the two settings that decide what is kept (FR-13).
        settings_form.apply_to_process(self._settings)

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*DEFAULT_SIZE)

        self._build_actions()
        self._build_central()
        self._build_metadata_dock()
        self._build_menus()
        self._build_toolbar()
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
        self.action_ingest = self._action("Ingest Colour Session")
        self.action_ingest.triggered.connect(self.ingest_color_session)
        self.action_run = self._action("Run", QKeySequence("Ctrl+R"))
        self.action_run.triggered.connect(lambda: self.run.start())
        self.action_stop = self._action("Stop", QKeySequence("Ctrl+."))
        self.action_stop.triggered.connect(lambda: self.run.stop())
        self.action_toggle_skip = self._action("Skip Shot", QKeySequence("Ctrl+K"))
        self.action_toggle_skip.triggered.connect(lambda: self.shot_list.toggle_skip())
        self.action_export = self._action("Export")
        self.action_cycle_display = self._action("Cycle In/Out display", QKeySequence("Ctrl+T"))
        self.action_cycle_display.triggered.connect(self._cycle_display_mode)
        self.action_find = self._action("Find", QKeySequence.StandardKey.Find)
        self.action_find.triggered.connect(lambda: self.batch_bar.focus_search())
        self.action_settings = self._action("Settings", QKeySequence.StandardKey.Preferences)
        self.action_settings.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.action_settings.triggered.connect(self.open_settings)
        self.action_settings.setEnabled(True)

        # Section 1's tooltips, keyed to `ui/toolbar_help.py` rather than written here.
        # A tuple rather than a dict because the order is the toolbar's own and reading
        # it beside `_build_toolbar` is how a button added without a tooltip is noticed.
        self._toolbar_help = (
            (toolbar_help.NEW, self.action_new),
            (toolbar_help.OPEN, self.action_open),
            (toolbar_help.SAVE, self.action_save),
            (toolbar_help.ADD_TURNOVER, self.action_add_turnover),
            (toolbar_help.SCAN, self.action_scan),
            (toolbar_help.INGEST, self.action_ingest),
            (toolbar_help.RUN, self.action_run),
            (toolbar_help.STOP, self.action_stop),
            (toolbar_help.EXPORT, self.action_export),
            (toolbar_help.SETTINGS, self.action_settings),
        )

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
        batch_menu.addAction(self.action_ingest)
        batch_menu.addAction(self.action_toggle_skip)
        batch_menu.addSeparator()
        batch_menu.addAction(self.action_run)
        batch_menu.addAction(self.action_stop)

        view_menu = menus.addMenu("View")
        view_menu.addAction(self.action_cycle_display)
        view_menu.addAction(self.action_find)
        view_menu.addAction(self.action_metadata)

    def _build_toolbar(self) -> None:
        """Section 1's toolbar, in its three groups, separated as it is drawn there."""
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        for group in (
            (self.action_new, self.action_open, self.action_save),
            (
                self.action_add_turnover,
                self.action_scan,
                self.action_ingest,
                self.action_run,
                self.action_stop,
            ),
            (self.action_export, self.action_settings),
        ):
            if toolbar.actions():
                toolbar.addSeparator()
            for action in group:
                toolbar.addAction(action)
        self.addToolBar(toolbar)
        self.toolbar = toolbar
        # `_update_state` writes these from then on, but it only runs once a batch has
        # been opened, and the first launch is the one where a greyed toolbar most needs
        # to say what it is waiting for (UI_SPEC section 10).
        self._refresh_tooltips(open_batch=False, scanning=False, running=False)

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
        self.shot_model.row_edited.connect(lambda _row: self.show_results())
        self._camdata_cache: dict[Path, dict[str, str]] = {}
        self.autosave.saved.connect(lambda path: self.statusBar().showMessage(f"Saved {path.name}"))
        self.batch_bar = BatchBar(self)
        self.batch_bar.display_mode_picked.connect(self.set_display_mode)
        self.batch_bar.search_changed.connect(self.shot_list.filter_by)
        self.shot_list.filter_cleared.connect(self.batch_bar.search.clear)
        self.batch_bar.delivery_root_clicked.connect(self.choose_delivery_root)

        self.scanner = Scanner(self)
        self.scanner.scanned.connect(self._take_scanned)
        self.scanner.started_folder.connect(self._say_scanning)
        self.scanner.finished.connect(self._scan_finished)

        self.run_strip = RunStrip(self)
        # After the strip, because the run reports through it and wires itself to it.
        self.run = RunController(self)

        self.list_pages = QStackedWidget(self)
        self.list_pages.addWidget(self.shot_list)
        self.list_pages.addWidget(self._list_empty_state())

        batch_page = QWidget(self)
        batch_layout = QVBoxLayout(batch_page)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setSpacing(0)
        batch_layout.addWidget(self.batch_bar)
        batch_layout.addWidget(self.run_strip)
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
        self.shot_model.set_run(None)
        self.run_strip.clear()
        self.autosave.watch(batch, path)
        self._batch_path = path
        self._batch_open = True
        self.batch_bar.set_batch_name(batch.name)
        self.batch_bar.show_delivery_root(batch.delivery_root)
        self._camdata_cache.clear()
        self.show_results()
        self.pages.setCurrentIndex(1)
        self.update_state()

    @property
    def batch(self) -> Batch:
        """The open batch. The model is the one that holds it; this is where to ask."""
        return self.shot_model.batch

    @property
    def batch_path(self) -> Path | None:
        """Where the open batch is saved, or None when it has never been saved."""
        return self._batch_path

    @property
    def settings(self) -> core_settings.AppSettings:
        """The per user settings now in force. Replaced wholesale by an Apply.

        Read only from here, because a run reads three of them (`ui/run_controller.py`)
        and the Settings page is the one thing that writes them.
        """
        return self._settings

    def new_batch(self) -> None:
        """An empty batch with no file, waiting for a turnover (section 10).

        It takes a **copy** of the rule thresholds in Settings rather than reading them
        as it goes, for the reason UI_SPEC section 13 gives for the two roots: what a
        delivery was checked against is a record of that work, so changing the defaults
        next month must not silently re-judge a batch that shipped last week.
        """
        if not self._may_abandon_current():
            return
        batch = Batch()
        if self._settings.rules:
            batch.settings_overrides[qc.RULES_OVERRIDE_KEY] = self._app_rules().to_dict()
        self.set_batch(batch)

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
        # Without it the next autosave overwrites the only copy, so the open waits.
        try:
            batchfile.backup(path)
        except OSError as exc:
            self.report_problem("Could not back up batch", f"{path.name} was not opened: {exc}")
            return
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

    def open_settings(self) -> None:
        """The Settings page, and what an Apply reaches. UI_SPEC section 9, PRD FR-12.

        The dialog edits values and nothing else; writing them is here, because this is
        what owns the batch. Apply does three things and each is a different lifetime:
        the per user settings go to disk, the thresholds are written onto the open batch
        as its own copy, and the checks re-run so the list and the Issues dock describe
        the batch under the numbers that are now in force.
        """
        dialog = self.settings_dialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings, rules = dialog.result_settings()
        settings_form.apply_to_process(self._settings)
        core_settings.save(self._settings, self._settings_path)
        if not self._batch_open:
            return
        batch = self.batch
        batch.settings_overrides[qc.RULES_OVERRIDE_KEY] = rules.to_dict()
        qc.apply_batch_rules(batch, rules)
        self.shot_model.refresh_rows()
        self.show_results()
        self.autosave.schedule()
        self.statusBar().showMessage(SETTINGS_APPLIED)

    def settings_dialog(self) -> SettingsDialog:
        """Built here so a test can hand back one it has already answered."""
        rules = qc.settings_for(self.batch) if self._batch_open else self._app_rules()
        return SettingsDialog(self._settings, rules, self)

    def _app_rules(self) -> qc.RuleSettings:
        """The thresholds a new batch would start from, or the defaults.

        A settings file written by hand can hold a key the rules do not know, which
        `RuleSettings.from_dict` refuses rather than shrugging at. Refusing to open the
        page over it would leave no way to fix it, so it falls back and says so.
        """
        try:
            return qc.RuleSettings.from_dict(self._settings.rules)
        except (TypeError, ValueError) as exc:
            log.warning("rule defaults in the settings file are unusable (%s)", exc)
            return qc.RuleSettings()

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
        self._scan([(folder, scan.next_turnover_id(self.batch))])

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

    def _scan(self, folders: list[tuple[Path, str]]) -> None:
        """Hand the folders to the worker thread and show that something is happening."""
        if not folders:
            return
        settings = scan.ScanSettings(
            show_pattern=settings_form.show_pattern_of(self._settings),
            path_map=dict(self._settings.path_map),
            project_rate=self.batch.project_rate,
            rules=qc.settings_for(self.batch),
        )
        self.progress.setRange(0, 0)
        self.progress.setVisible(True)
        self.update_state()
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
        self.show_results()
        self.autosave.schedule()
        self.update_state()

    def _scan_finished(self) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.statusBar().showMessage(f"{len(self.batch.rows)} shots")
        self.update_state()

    # --- the colour session -----------------------------------------------------------

    def ingest_color_session(self) -> None:
        """Point at the session's final EDL and write what it says onto one turnover.

        PRD section 6 step 4, and the window's half of what `run --color-session` does.
        **One turnover**, because that is the scope the session is recorded at
        (`Turnover.color_session_edl`, OQ-50) and the scope QC-008 holds a run back at: a
        turnover still waiting on colour is a different turnover from this one.

        **The rate the EDL is read at is the first row with media's**, which is the CLI's
        answer and for the CLI's reason: an EDL's timecode is read at one rate and a batch
        can carry more than one (OQ-19). A turnover whose rows have no media has no rate to
        read it at, and that is said before the chooser opens rather than after it.

        The rules re-run afterwards because the ingest moves In and Out on the rows it
        matched, so the durations the thresholds are judged against have changed. QC-008
        and QC-009 are pre-flight and clear at the next Run.
        """
        if not self._batch_open or self.scanner.busy or self.run.busy:
            return
        turnover = self._turnover_to_ingest()
        if turnover is None:
            return
        rows = self.batch.rows_for(turnover.turnover_id)
        rates = [row.media.rate for row in rows if row.media is not None]
        if not rates:
            self.report_problem(NO_RATE_TITLE, NO_RATE.format(name=turnover.folder.name))
            return
        edl = self.ask_edl_path()
        if edl is None:
            return
        try:
            session = clf.load_session(edl, rates[0], settings_form.show_pattern_of(self._settings))
        except clf.ColorSessionError as exc:
            self.report_problem(CANNOT_READ_SESSION, str(exc))
            return

        report = clf.ingest(turnover, rows, session)
        # Where the chooser opens next time, which is a per user starting point and not
        # a record of what this batch was graded from: that is on the turnover (FR-12).
        self._settings.color_session_folder = str(edl.parent)
        qc.apply_batch_rules(self.batch, qc.settings_for(self.batch))
        self.shot_model.refresh_rows()
        self.show_results()
        self.autosave.schedule()
        self.report_ingest(ingest_text(report, turnover.folder.name, rates))

    def _turnover_to_ingest(self) -> Turnover | None:
        """Which turnover the ingest is for: the selection when it says, else asked for.

        A batch of one turnover never asks, because there is nothing to choose between.
        A selected group header says which, and so does a selection of rows that are all
        in the same one; a selection spanning two turnovers says nothing, so it asks.
        """
        turnovers = [t for t in self.batch.turnovers if self.batch.rows_for(t.turnover_id)]
        if len(turnovers) == 1:
            return turnovers[0]
        chosen = self.shot_list.selected_turnover()
        if chosen is None:
            selected = {row.turnover_id for row in self.shot_list.selected_rows()}
            if len(selected) == 1:
                one = next(iter(selected))
                chosen = next((t for t in turnovers if t.turnover_id == one), None)
        return chosen if chosen is not None else self.ask_turnover(turnovers)

    # --- what is enabled, and what the centre shows -----------------------------------

    def update_state(self) -> None:
        """One place that decides both, because both answer the same three questions.

        Called after anything that can change what the batch holds, rather than from
        each of those places: an action left enabled over an empty batch is the kind of
        thing that only shows up when somebody presses it.
        """
        open_batch = self._batch_open
        scanning = self.scanner.busy
        running = self.run.busy
        busy = scanning or running
        for action in (self.action_cycle_display, self.action_find, self.action_toggle_skip):
            action.setEnabled(open_batch)
        self.action_save.setEnabled(open_batch)
        self.action_add_turnover.setEnabled(open_batch and not busy)
        self.action_scan.setEnabled(open_batch and not busy and bool(self._unscanned()))
        self.action_ingest.setEnabled(open_batch and not busy and bool(self.batch.rows))
        # New and Open swap the batch the run is writing into, so they go with it.
        self.action_new.setEnabled(not running)
        self.action_open.setEnabled(not running)
        self.action_run.setEnabled(open_batch and not busy and bool(self.batch.rows))
        self.action_stop.setEnabled(running and not self.run.cancelled)
        self._refresh_tooltips(open_batch=open_batch, scanning=scanning, running=running)

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

    def _refresh_tooltips(self, *, open_batch: bool, scanning: bool, running: bool) -> None:
        """Section 1's hover text, rewritten whenever what a button can do changes.

        Here rather than in `_build_actions` because half of what a tooltip says is why
        the button is unavailable, and that is only true of a moment. It reads the
        enabled state off each action rather than working it out again: `_update_state`
        has just set it and is the one authority on it.
        """
        state = toolbar_help.ToolbarState(
            batch_open=open_batch,
            has_rows=open_batch and bool(self.batch.rows),
            has_unscanned=open_batch and bool(self._unscanned()),
            has_session=open_batch and any(t.color_session_edl is not None for t in self.batch.turnovers),
            scanning=scanning,
            rendering=running,
            stopping=running and self.run.cancelled,
        )
        for key, action in self._toolbar_help:
            shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            action.setToolTip(toolbar_help.tooltip(key, state, action.isEnabled(), shortcut))

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
        self.list_empty_text.linkActivated.connect(self.show_issues)
        layout.addWidget(self.list_empty_text)
        return central

    def show_issues(self) -> None:
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
        chosen, _filter = QFileDialog.getSaveFileName(self, "Save Batch", str(start), BATCH_FILTER)
        return self._remember(Path(chosen)) if chosen else None

    def ask_folder(self, title: str, start: Path | None) -> Path | None:
        """One folder: a turnover, or either of the two roots."""
        chosen = QFileDialog.getExistingDirectory(self, title, self._start_folder(start))
        return self._remember(Path(chosen)) if chosen else None

    def ask_edl_path(self) -> Path | None:
        """Which final EDL to ingest. The editor points at the EDL, not the folder.

        It opens at the colour session folder Settings remembers rather than at the
        batch's source root: a session and a turnover live nowhere near each other on
        the mount, which is why that setting exists (FR-12).
        """
        start = self._settings.color_session_folder or self._settings.last_folder
        chosen, _filter = QFileDialog.getOpenFileName(self, "Ingest Colour Session", start, EDL_FILTER)
        return Path(chosen) if chosen else None

    def ask_turnover(self, turnovers: Sequence[Turnover]) -> Turnover | None:
        """Which turnover, when the selection does not say. Folder names, not ids.

        The folder is what the editor picked in Add Turnover and what the session was
        exported for; `turnover001` is the tool's own handle for it.
        """
        names = turnover_labels(turnovers)
        chosen, accepted = QInputDialog.getItem(
            self, "Ingest Colour Session", WHICH_TURNOVER, names, 0, False
        )
        if not accepted:
            return None
        return turnovers[names.index(chosen)]

    def report_ingest(self, text: str) -> None:
        """What the ingest did. A modal, because it is the answer to one just opened.

        Not the review UI_SPEC section 1 keeps modals out of: every list in it is
        something to act on now - a row with no event will not render - and the
        alternative is a status bar line that is gone before it has been read.
        """
        QMessageBox.information(self, INGEST_TITLE, text)

    def ask_unsaved(self) -> QMessageBox.StandardButton:
        """Save, Discard or Cancel, for edits that could not be written."""
        return QMessageBox.warning(
            self,
            "Unsaved batch",
            unsaved_question(self.autosave.path),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

    def open_folder(self, folder: Path) -> None:
        """Show a folder in the Finder. Its own method so a test can answer it."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

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

    def _build_metadata_dock(self) -> None:
        """Section 1's reading surface beside the list, in a dock for what a dock gives.

        A `QDockWidget` rather than a splitter pane, because three things section 12
        asks for come with one and would otherwise be built: it collapses to nothing,
        its width and whether it is showing are remembered by `saveState` alongside the
        bottom dock, and `toggleViewAction` is the Ctrl+I the spec names. It is closable
        but **not movable or floatable**: it is a fixed width reading surface, not a
        second workspace, and a pane the editor can drag onto the left is a layout
        nobody asked to maintain.
        """
        dock = QDockWidget("Metadata", self)
        dock.setObjectName("metadata_dock")
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)

        self.metadata = MetadataPane(dock)
        self.metadata.issue_clicked.connect(self._show_issue)
        self.metadata.set_collapsed(self._settings.metadata_collapsed)
        dock.setWidget(self.metadata)
        dock.setMinimumWidth(METADATA_MIN_WIDTH)

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.metadata_dock = dock
        # A starting width, for a window that has never been arranged. `restoreState`
        # runs after this and wins whenever there is something saved, so this is only
        # ever the first launch: without it the dock opens at its minimum, which is the
        # narrowest the pane is allowed to be rather than the width it wants.
        self.resizeDocks([dock], [METADATA_WIDTH], Qt.Orientation.Horizontal)

        self.action_metadata = dock.toggleViewAction()
        self.action_metadata.setText("Metadata")
        self.action_metadata.setShortcut(QKeySequence("Ctrl+I"))

        # Three signals, not one. The selection is the obvious one; a commit changes a
        # value the pane is showing (M5.3), and `_show_results` covers everything that
        # rewrites QC wholesale. A pane on the selection alone shows a value that is
        # stale rather than wrong, which is the harder kind to notice.
        selection = self.shot_list.selectionModel()
        selection.selectionChanged.connect(lambda *_: self.refresh_metadata())

    def refresh_metadata(self) -> None:
        """Redraw the pane from the current selection. Cheap when nothing moved.

        `MetadataPane.show_sections` compares the answer against what is drawn and
        returns without touching a widget when they are equal, so this can be called
        from anything that might have changed a value without counting how often.
        """
        rows = self.shot_list.selected_rows()
        if rows:
            sections = metadata.describe(rows, self.batch, self._camdata)
            summary = metadata.selection_summary(len(rows)) if len(rows) > 1 else ""
            self.metadata.show_sections(sections, summary)
            return
        turnover = self.shot_list.selected_turnover()
        if turnover is not None:
            self.metadata.show_sections(metadata.describe_turnover(turnover, self.batch.project_rate))
            return
        self.metadata.clear()

    def _camdata(self, path: Path) -> dict[str, str]:
        """camData's key/values, read once per file per batch (CLAUDE.md: scan once).

        The only field in the pane that lives on disk rather than in the model, and the
        pane is redrawn on every selection change, so an uncached read would be a round
        trip to a Drive mount per arrow key. Unreadable reads as empty: QC-053 already
        says so in the Issues dock and the pane is not the place to say it twice.
        """
        cached = self._camdata_cache.get(path)
        if cached is None:
            try:
                cached = camdata.parse(path)
            except OSError:
                cached = {}
            self._camdata_cache[path] = cached
        return cached

    def _show_issue(self, rule_id: str) -> None:
        """A rule ID clicked in the pane: bring the Issues dock forward (section 12.2)."""
        self.show_issues()
        self.issues.select_result(rule_id, self.shot_list.selected_rows())

    def show_results(self) -> None:
        """The Issues dock and the metadata pane, which read the same QC results.

        One method because they are always right or wrong together: every place that
        re-runs a rule has to tell both, and a place that told only one is the bug this
        exists to make impossible to write.
        """
        self.issues.show_batch(self.batch)
        self.refresh_metadata()

    def _build_bottom_dock(self) -> None:
        """Issues (M5.4) and Log (M5.8.2), then Deliverables, still to come."""
        dock = QDockWidget("Details", self)
        dock.setObjectName("bottom_dock")
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        tabs = QTabWidget(dock)
        tabs.setObjectName("bottom_tabs")
        self.issues = IssuesDock(tabs)
        self.issues.row_activated.connect(self.shot_list.select_row)
        self.log_view = LogView(tabs)
        built = {"Issues": self.issues, "Log": self.log_view}
        for name in BOTTOM_TABS:
            widget = built.get(name)
            if widget is not None:
                tabs.addTab(widget, name)
                continue
            placeholder = QLabel(f"No {name.lower()} yet", tabs)
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tabs.addTab(placeholder, name)
        dock.setWidget(tabs)

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.bottom_dock = dock
        self.bottom_tabs = tabs

        # The same two signals the metadata pane follows, minus the one about QC: what
        # the Log tab needs from the list is a shot code, and only a selection and an
        # edit can change it.
        self.shot_list.selectionModel().selectionChanged.connect(lambda *_: self._refresh_log_filter())
        self.shot_model.row_edited.connect(lambda _row: self._refresh_log_filter())

    def _refresh_log_filter(self) -> None:
        """Tell the Log tab which shot "selected row only" means (FR-13).

        One shot or none. A selection spanning two shots has no single row to filter by,
        and so does a row with no shot code yet; both read as no selection rather than as
        a filter that matches nothing.
        """
        codes = {row.shot_code or "" for row in self.shot_list.selected_rows()}
        self.log_view.set_selected_shot(codes.pop() if len(codes) == 1 else "")

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
        the default size rather than failing a launch. The decode is the one step that
        can raise, on a hand edited file, and it is skipped for the same reason.
        """
        for text, restore in (
            (self._settings.window_geometry, self.restoreGeometry),
            (self._settings.window_state, self.restoreState),
        ):
            if not text:
                continue
            try:
                blob = b64decode(text, validate=True)
            except ValueError:
                log.warning("window state in the settings file is not base64; ignoring it")
                continue
            restore(QByteArray(blob))

    def save_window_state(self) -> None:
        """Write what the window looks like now. Called on close."""
        self._settings.window_geometry = b64encode(self.saveGeometry().data()).decode()
        self._settings.window_state = b64encode(self.saveState().data()).decode()
        self._settings.metadata_collapsed = self.metadata.collapsed
        core_settings.save(self._settings, self._settings_path)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop waiting, ask about what could not be written, and stop the scan.

        The flush is first because an edit made a second before the window closed is not
        one the editor expects to lose, and what is still pending after it is a batch
        that has never been saved: the one case the editor has to answer for.

        The scan is stopped last and waited on, because a `QThread` still running when
        its owner is collected is a crash on the way out.

        **A run is stopped and the close retried when its results are in.** They come
        back by a queued signal and are applied on this thread (`_run_finished`), so a
        close that blocked here waiting for the thread would drop every deliverable the
        run had finished. The wait is bounded the way `Runner.shutdown`'s is: a wedged
        worker must not be a window that cannot be closed, and after that long the close
        goes ahead without the results, as it always did.
        """
        if self.run.busy and not self.run.wait_expired:
            self.run.close_when_finished()
            event.ignore()
            return
        if not self._may_abandon_current():
            event.ignore()
            return
        self.scanner.shutdown()
        self.run.shutdown()
        self.log_view.detach()
        self.save_window_state()
        super().closeEvent(event)
