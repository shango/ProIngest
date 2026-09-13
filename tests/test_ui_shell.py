"""The main window shell. `ui/app.py` and `ui/main_window.py`, M5.1.

Every test here runs on the offscreen platform, which is what lets the UI be checked on
both CI runners and on a machine with no display. What is asserted is what the window
is made of and what it remembers, not how it looks: a screenshot test would pin the
theme, and the theme is the one part of this a person has to judge (docs/MAC_SESSION.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from proingest.core import batchfile, naming
from proingest.core import settings as core_settings
from proingest.core.models import Batch, Deliverable, Turnover
from proingest.core.planner import DeliverableJob
from proingest.core.render import Progress
from proingest.ui import app as ui_app
from proingest.ui import paths
from proingest.ui.main_window import (
    BOTTOM_TABS,
    CHECKING_BATCH,
    EMPTY_STATE_TEXT,
    NO_ROWS_TEXT,
    NO_TURNOVERS_TEXT,
    NOTHING_TO_RENDER,
    WRITING_REPORTS,
    MainWindow,
)
from proingest.ui.metadata import MIXED, NO_SELECTION, as_text
from proingest.ui.run_strip import LINK_COLOR, RunStrip
from proingest.ui.runner import RENDERING
from proingest.ui.shot_model import IN, NOTES, DisplayMode, RowState
from tests.fixtures.batches import batch, fail, media, row, warn


class DrivenWindow(MainWindow):
    """A window whose dialogs are answered rather than opened.

    **Every modal the window can open is overridden here rather than per test**, and
    each defaults to the answer that changes nothing. An offscreen modal is a hung suite
    rather than a failed assertion, so a test that forgets to stub one would not fail,
    it would stop - which is exactly what happened to this file the first time a batch
    was opened whose delivery root did not exist.
    """

    def __init__(self, settings_path: Path) -> None:
        super().__init__(settings_path)
        self.problems: list[tuple[str, str]] = []
        self.folder_answer: Path | None = None
        self.open_answer: Path | None = None
        self.save_answer: Path | None = None
        self.save_asked: list[str] = []
        self.unsaved_answer = QMessageBox.StandardButton.Discard
        self.opened_folders: list[Path] = []

    def report_problem(self, title: str, text: str) -> None:
        self.problems.append((title, text))

    def ask_folder(self, title: str, start: Path | None) -> Path | None:
        return self.folder_answer

    def ask_open_path(self) -> Path | None:
        return self.open_answer

    def ask_save_path(self, suggested_name: str) -> Path | None:
        self.save_asked.append(suggested_name)
        return self.save_answer

    def ask_unsaved(self) -> QMessageBox.StandardButton:
        return self.unsaved_answer

    def open_folder(self, folder: Path) -> None:
        self.opened_folders.append(folder)


@pytest.fixture
def window(qt_app: QApplication, tmp_path: Path) -> DrivenWindow:
    """A window whose settings file is a temporary one, never the user's own."""
    return DrivenWindow(tmp_path / "settings.json")


REMEMBERED_SIZE = (640, 480)
"""Smaller than any screen this runs on. `restoreGeometry` clamps to the screen, and the
offscreen platform's is 800 by 800, so a larger size here would test the clamp instead."""


def actions(window: DrivenWindow) -> dict[str, QAction]:
    return {action.text(): action for action in window.findChildren(QAction)}


class TestTheApplication:
    def test_its_name_is_set_because_the_data_folder_is_built_from_it(
        self, qt_app: QApplication
    ) -> None:
        assert qt_app.applicationName() == paths.APPLICATION_NAME

    def test_the_organisation_name_is_left_unset(self, qt_app: QApplication) -> None:
        """Qt appends organisation and application both, and PACKAGING.md wants one level.

        Setting both gives `Application Support/ProIngest/ProIngest`, which is not where
        the packaging document says the settings file is, and nothing would notice until
        somebody went looking for it on a real Mac.
        """
        assert qt_app.organizationName() == ""

    def test_the_app_data_folder_is_named_once(self, qt_app: QApplication) -> None:
        assert paths.app_data_dir().name == paths.APPLICATION_NAME
        assert paths.app_data_dir().parent.name != paths.APPLICATION_NAME

    def test_the_settings_path_lands_under_the_app_data_folder(self, qt_app: QApplication) -> None:
        """Qt is asked where that is; nothing here builds the path (UI_SPEC section 11)."""
        assert paths.settings_path().parent == paths.app_data_dir()
        assert paths.settings_path().name == core_settings.SETTINGS_FILENAME

    def test_the_theme_is_loaded_and_is_not_empty(self) -> None:
        assert "QMainWindow" in ui_app.theme()

    def test_a_missing_theme_does_not_stop_the_app(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A cosmetic file left out of a bundle must not be the reason the tool will not start."""
        monkeypatch.setattr(ui_app, "THEME_FILE", Path("/nowhere/theme.qss"))
        assert ui_app.theme() == ""


class TestTheToolbarAndMenus:
    def test_every_action_in_the_spec_exists(self, window: DrivenWindow) -> None:
        """UI_SPEC section 1's three toolbar groups, in one place so none goes missing."""
        expected = {
            "New", "Open...", "Save",
            "Add Turnover", "Scan", "Run", "Stop",
            "Export", "Settings",
        }  # fmt: skip
        assert expected <= set(actions(window))

    def test_the_toolbar_carries_them_in_the_spec_s_order(self, window: DrivenWindow) -> None:
        named = [action.text() for action in window.toolbar.actions() if action.text()]
        assert named == [
            "New", "Open...", "Save",
            "Add Turnover", "Scan", "Run", "Stop",
            "Export", "Settings",
        ]  # fmt: skip

    def test_the_groups_are_separated_as_section_1_draws_them(self, window: DrivenWindow) -> None:
        separators = [action for action in window.toolbar.actions() if action.isSeparator()]
        assert len(separators) == 2

    def test_nothing_with_no_feature_behind_it_is_enabled(self, window: DrivenWindow) -> None:
        """Disabled rather than absent, and never a live-looking button that does nothing.

        Shorter with every chunk. New and Open came alive in M5.4, and the four left are
        the run (M5.5), the exports and the Settings page (M5.7).
        """
        for name in ("Run", "Stop", "Export", "Settings"):
            assert not actions(window)[name].isEnabled(), name

    def test_what_needs_a_batch_waits_for_one(self, window: DrivenWindow) -> None:
        for name in ("Save", "Add Turnover", "Scan"):
            assert not actions(window)[name].isEnabled(), name

    def test_quit_works_from_the_first_launch(self, window: DrivenWindow) -> None:
        assert actions(window)["Quit"].isEnabled()


class TestTheKeyboardModel:
    """UI_SPEC section 4. `Ctrl` is portable and Qt maps it onto Cmd for macOS itself."""

    @pytest.mark.parametrize(
        ("name", "keys"),
        [("Run", "Ctrl+R"), ("Stop", "Ctrl+.")],
    )
    def test_the_shortcuts_the_spec_names_outright(
        self, window: DrivenWindow, name: str, keys: str
    ) -> None:
        assert actions(window)[name].shortcut() == QKeySequence(keys)

    @pytest.mark.parametrize(
        ("name", "standard"),
        [
            ("New", QKeySequence.StandardKey.New),
            ("Open...", QKeySequence.StandardKey.Open),
            ("Save", QKeySequence.StandardKey.Save),
            ("Settings", QKeySequence.StandardKey.Preferences),
            ("Quit", QKeySequence.StandardKey.Quit),
        ],
    )
    def test_the_standard_ones_come_from_qt(
        self, window: DrivenWindow, name: str, standard: QKeySequence.StandardKey
    ) -> None:
        """Standard keys also pick up the platform's second binding, which a literal cannot."""
        assert actions(window)[name].shortcut() == QKeySequence(standard)

    @pytest.mark.parametrize(
        ("name", "role"),
        [
            ("About ProIngest", QAction.MenuRole.AboutRole),
            ("Settings", QAction.MenuRole.PreferencesRole),
            ("Quit", QAction.MenuRole.QuitRole),
        ],
    )
    def test_the_three_macos_roles_are_set(
        self, window: DrivenWindow, name: str, role: QAction.MenuRole
    ) -> None:
        """Without these macOS leaves them in the window's menus, where nobody looks."""
        assert actions(window)[name].menuRole() == role


class TestTheLayout:
    def test_the_empty_state_says_what_section_10_says(self, window: DrivenWindow) -> None:
        label = window.findChild(QLabel, "empty_state_text")
        assert label is not None
        assert label.text() == EMPTY_STATE_TEXT

    def test_its_two_buttons_trigger_the_toolbar_s_own_actions(self, window: DrivenWindow) -> None:
        """One action per thing the tool can do, whichever surface the user reaches it from."""
        empty_state = window.findChild(QWidget, "empty_state")
        assert empty_state is not None
        buttons = [button.text() for button in empty_state.findChildren(QPushButton)]
        assert buttons == ["New batch", "Open batch..."]

    def test_they_follow_their_action_both_ways(self, window: DrivenWindow) -> None:
        """The action is the authority on whether the thing can be done at all."""
        button = next(b for b in window.findChildren(QPushButton) if b.text() == "New batch")
        assert button.isEnabled()
        window.action_new.setEnabled(False)
        assert not button.isEnabled()
        window.action_new.setEnabled(True)
        assert button.isEnabled()

    def test_the_bottom_dock_has_its_three_tabs(self, window: DrivenWindow) -> None:
        names = [window.bottom_tabs.tabText(i) for i in range(window.bottom_tabs.count())]
        assert names == list(BOTTOM_TABS)

    def test_the_status_bar_progress_is_hidden_until_a_run(self, window: DrivenWindow) -> None:
        assert not window.progress.isVisible()


class TestOpeningABatch:
    """M5.2: the list replaces the empty state, and the two list controls come alive."""

    def test_the_empty_state_gives_way_to_the_list(self, window: DrivenWindow) -> None:
        assert window.pages.currentIndex() == 0
        window.set_batch(batch(row()))
        assert window.pages.currentIndex() == 1

    def test_the_batch_bar_names_the_batch(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row(), name="melt turnover 12"))
        assert window.batch_bar.name_label.text() == "melt turnover 12"

    def test_the_rows_reach_the_list(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row(), row("MELT0002_pl01")))
        assert window.shot_list.proxy.rowCount(window.shot_list.proxy.index(0, 0)) == 2

    def test_the_list_controls_are_dead_until_there_is_a_list(self, window: DrivenWindow) -> None:
        assert not window.action_cycle_display.isEnabled()
        assert not window.action_find.isEnabled()
        window.set_batch(batch(row()))
        assert window.action_cycle_display.isEnabled()
        assert window.action_find.isEnabled()

    def test_ctrl_t_cycles_the_display_and_the_buttons_follow(self, window: DrivenWindow) -> None:
        """One place changes the mode, whichever surface asked (UI_SPEC section 4)."""
        window.set_batch(batch(row()))
        window.action_cycle_display.trigger()
        assert window.shot_model.display_mode is DisplayMode.SOURCE_TC
        checked = [b.text() for b in window.batch_bar.mode_buttons.buttons() if b.isChecked()]
        assert checked == [DisplayMode.SOURCE_TC.value]

    def test_picking_a_mode_on_the_bar_reaches_the_model(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()))
        window.batch_bar.display_mode_picked.emit(DisplayMode.RECORD_TC)
        assert window.shot_model.display_mode is DisplayMode.RECORD_TC

    def test_typing_in_the_search_box_filters_the_list(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row(), row("MELT0002_pl01")))
        window.batch_bar.search.setText("MELT0002")
        assert window.shot_list.proxy.rowCount(window.shot_list.proxy.index(0, 0)) == 1

    def test_ctrl_f_puts_the_cursor_in_the_search_box(self, window: DrivenWindow) -> None:
        """`focusWidget` rather than `hasFocus`: the offscreen platform activates no window,
        so the second asks whether the desktop gave this process focus, which it cannot."""
        window.set_batch(batch(row()))
        window.action_find.trigger()
        assert window.focusWidget() is window.batch_bar.search


class TestWhatTheWindowRemembers:
    def test_the_size_and_dock_state_come_back_on_the_next_launch(
        self, qt_app: QApplication, tmp_path: Path
    ) -> None:
        path = tmp_path / "settings.json"
        first = MainWindow(path)
        first.resize(*REMEMBERED_SIZE)
        first.save_window_state()

        second = MainWindow(path)
        assert second.size().toTuple() == REMEMBERED_SIZE

    def test_closing_is_what_saves_it(self, qt_app: QApplication, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        window = MainWindow(path)
        window.resize(900, 600)
        window.close()
        assert core_settings.load(path).window_geometry != ""

    def test_a_first_launch_opens_at_the_default_size(
        self, qt_app: QApplication, tmp_path: Path
    ) -> None:
        from proingest.ui.main_window import DEFAULT_SIZE

        assert MainWindow(tmp_path / "none.json").size().toTuple() == DEFAULT_SIZE

    def test_window_state_a_different_qt_wrote_is_ignored_rather_than_fatal(
        self, qt_app: QApplication, tmp_path: Path
    ) -> None:
        """Qt refuses a blob it does not recognise; the launch still has to happen."""
        path = tmp_path / "settings.json"
        core_settings.save(
            core_settings.AppSettings(window_geometry="bm90IHF0", window_state="bm90IHF0"), path
        )
        assert MainWindow(path).size().toTuple() != (0, 0)


class TestEditingFromTheWindow:
    """M5.3: the two pieces of editing the window owns, the skip action and autosave."""

    def test_skip_is_dead_until_there_is_a_row_to_skip(self, window: DrivenWindow) -> None:
        assert not window.action_toggle_skip.isEnabled()
        window.set_batch(batch(row()))
        assert window.action_toggle_skip.isEnabled()

    def test_ctrl_k_is_what_it_answers_to(self, window: DrivenWindow) -> None:
        assert window.action_toggle_skip.shortcut() == QKeySequence("Ctrl+K")

    def test_it_skips_the_current_row(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()))
        window.shot_list.ask_skip_reason = lambda row: "reshoot"  # type: ignore[method-assign]
        proxy = window.shot_list.proxy
        window.shot_list.setCurrentIndex(proxy.index(0, 1, proxy.index(0, 0)))
        window.action_toggle_skip.trigger()
        assert window.shot_model.batch.rows[0].skipped

    def test_an_edit_schedules_a_save(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()), tmp_batch_path(window))
        edit(window, "checked against the EDL")
        assert window.autosave.pending

    def test_and_closing_the_window_writes_it(self, window: DrivenWindow) -> None:
        path = tmp_batch_path(window)
        window.set_batch(batch(row()), path)
        edit(window, "checked against the EDL")
        window.close()
        assert batchfile.load(path, reconcile=False).rows[0].notes == "checked against the EDL"

    def test_a_batch_with_no_file_is_asked_about_rather_than_dropped(
        self, window: DrivenWindow
    ) -> None:
        """A batch made by New has no file until it is saved, so closing has to ask."""
        window.set_batch(batch(row()))
        edit(window, "checked")
        window.close()
        assert window.autosave.pending

    def test_a_save_says_so_in_the_status_bar(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()), tmp_batch_path(window))
        edit(window, "checked")
        window.autosave.flush()
        assert "melt.pibatch" in window.statusBar().currentMessage()


class TestTheBatchLifecycle:
    """M5.4: New, Open, Save, the two roots, and the empty states between them."""

    def test_new_and_open_are_live_from_the_first_launch(self, window: DrivenWindow) -> None:
        """They are the only way out of the empty state, so they cannot wait on a batch."""
        assert window.action_new.isEnabled()
        assert window.action_open.isEnabled()

    def test_new_opens_an_empty_batch_asking_for_a_turnover(self, window: DrivenWindow) -> None:
        window.action_new.trigger()
        assert window.pages.currentIndex() == 1
        assert window.list_pages.currentIndex() == 1
        assert window.list_empty_text.text() == NO_TURNOVERS_TEXT

    def test_a_new_batch_has_no_file_until_it_is_saved(self, window: DrivenWindow) -> None:
        window.action_new.trigger()
        assert window.batch_path is None

    def test_open_reads_a_batch_and_its_rows_reach_the_list(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        path = batchfile.save(batch(row()), tmp_path / "melt.pibatch")
        window.open_answer = path
        window.action_open.trigger()

        assert window.batch.rows[0].clip_name == "MELT0001_pl01"
        assert window.batch_path == path
        assert window.list_pages.currentIndex() == 0

    def test_open_takes_a_backup_first(self, window: DrivenWindow, tmp_path: Path) -> None:
        """The file backed up is the last one the editor saw whole."""
        path = batchfile.save(batch(row()), tmp_path / "melt.pibatch")
        window.open_answer = path
        window.action_open.trigger()
        assert path.with_suffix(batchfile.BACKUP_SUFFIX).is_file()

    def test_a_batch_that_will_not_read_is_reported_rather_than_raised(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.pibatch"
        bad.write_text("{ not json")
        window.open_answer = bad
        window.action_open.trigger()

        assert window.problems and "bad.pibatch" in window.problems[0][1]
        assert window.pages.currentIndex() == 0

    def test_cancelling_the_open_dialog_changes_nothing(self, window: DrivenWindow) -> None:
        window.action_open.trigger()
        assert window.pages.currentIndex() == 0

    def test_save_asks_where_once_and_then_stops_asking(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row()))
        window.save_answer = tmp_path / "melt.pibatch"
        window.action_save.trigger()
        window.action_save.trigger()
        assert window.save_asked == ["melt"]
        assert (tmp_path / "melt.pibatch").is_file()

    def test_saving_is_what_gives_autosave_somewhere_to_write(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row()))
        edit(window, "held while there was no file")
        window.save_answer = tmp_path / "melt.pibatch"
        window.action_save.trigger()
        assert not window.autosave.pending

        edit(window, "and written from here on")
        window.autosave.flush()
        loaded = batchfile.load(tmp_path / "melt.pibatch", reconcile=False)
        assert loaded.rows[0].notes == "and written from here on"

    def test_a_save_that_fails_is_reported_rather_than_logged(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """Save is the one write the editor is waiting on, unlike an autosave."""
        blocked = tmp_path / "file.txt"
        blocked.write_text("not a folder")
        window.set_batch(batch(row()))
        window.save_answer = blocked / "melt.pibatch"
        window.action_save.trigger()
        assert window.problems

    def test_the_file_it_is_saved_as_is_what_names_it(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """The QC log and the tracker are named from the batch name, so an unnamed
        batch that reaches the exports exports as `untitled`."""
        window.set_batch(Batch())
        window.save_answer = tmp_path / "melt_day1.pibatch"
        window.action_save.trigger()

        assert window.batch.name == "melt_day1"
        assert window.batch_bar.name_label.text() == "melt_day1"

    def test_a_batch_that_already_has_a_name_keeps_it(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), name="melt"))
        window.save_answer = tmp_path / "something_else.pibatch"
        window.action_save.trigger()
        assert window.batch.name == "melt"

    def test_save_is_dead_until_there_is_a_batch(self, window: DrivenWindow) -> None:
        assert not window.action_save.isEnabled()
        window.set_batch(batch(row()))
        assert window.action_save.isEnabled()


class TestTheTwoRoots:
    """UI_SPEC section 13. Both are remembered on the batch, not in the app settings."""

    def test_the_bar_shows_the_delivery_root(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()))
        assert window.batch_bar.delivery_root.text() == "/delivery"

    def test_clicking_it_changes_it(self, window: DrivenWindow, tmp_path: Path) -> None:
        window.set_batch(batch(row()))
        window.folder_answer = tmp_path
        window.batch_bar.delivery_root.click()

        assert window.batch.delivery_root == tmp_path
        assert window.batch_bar.delivery_root.text() == str(tmp_path)
        assert window.autosave.pending

    def test_a_root_that_has_gone_missing_is_reported_and_the_chooser_reopens(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """Never silently recreated: a delivery tree written into a stale path is lost."""
        stale = batch(row())
        stale.source_root = tmp_path / "unmounted"
        path = batchfile.save(stale, tmp_path / "melt.pibatch")
        window.open_answer = path
        window.folder_answer = tmp_path / "here"
        window.action_open.trigger()

        assert any("Source root" in title for title, _text in window.problems)
        assert window.batch.source_root == tmp_path / "here"

    def test_a_root_that_is_still_there_is_left_alone(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        present = batch(row())
        present.source_root = tmp_path
        present.delivery_root = tmp_path
        path = batchfile.save(present, tmp_path / "melt.pibatch")
        window.open_answer = path
        window.action_open.trigger()
        assert window.problems == []


class TestAddingAndScanningTurnovers:
    """M5.4's other half: what reaches the scanner, and what comes back from it."""

    def test_adding_a_turnover_scans_it_straight_away(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(Batch())
        started = stub_scanner(window)
        window.folder_answer = tmp_path / "source" / "turnover001"
        window.action_add_turnover.trigger()

        assert started == [[(tmp_path / "source" / "turnover001", "t1")]]

    def test_adding_from_outside_the_source_root_moves_the_root(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """The root is a starting point and not a fence (UI_SPEC section 13)."""
        opened = Batch(source_root=tmp_path / "old")
        window.set_batch(opened)
        stub_scanner(window)
        window.folder_answer = tmp_path / "elsewhere" / "turnover002"
        window.action_add_turnover.trigger()
        assert opened.source_root == tmp_path / "elsewhere"

    def test_the_same_folder_twice_is_refused_rather_than_doubled(
        self, window: DrivenWindow
    ) -> None:
        window.set_batch(batch(row()))
        started = stub_scanner(window)
        window.folder_answer = window.batch.turnovers[0].folder
        window.action_add_turnover.trigger()

        assert window.problems and started == []

    def test_what_comes_back_reaches_the_list(self, window: DrivenWindow) -> None:
        window.set_batch(Batch())
        window._take_scanned(Turnover("t1", Path("/source/t1")), [row(turnover_id="t1")], {})

        assert len(window.batch.rows) == 1
        assert window.list_pages.currentIndex() == 0
        assert window.shot_list.proxy.rowCount(window.shot_list.proxy.index(0, 0)) == 1

    def test_the_probe_cache_is_merged_rather_than_replaced(self, window: DrivenWindow) -> None:
        """The worker started from a copy, so what the UI thread learned meanwhile stays."""
        opened = Batch(probe_cache={"ours|1|2": media()})
        window.set_batch(opened)
        window._take_scanned(Turnover("t1", Path("/s")), [], {"theirs|3|4": media()})
        assert set(opened.probe_cache) == {"ours|1|2", "theirs|3|4"}

    def test_a_turnover_arriving_re_runs_the_rules_across_the_whole_batch(
        self, window: DrivenWindow
    ) -> None:
        """QC-011 is a fact about every row, and a new turnover can create one."""
        window.set_batch(batch(row(turnover_id="t1"), turnovers=[Turnover("t1", Path("/s/t1"))]))
        window._take_scanned(Turnover("t2", Path("/s/t2")), [row(turnover_id="t2")], {})

        assert all("QC-011" in {result.rule_id for result in r.qc} for r in window.batch.rows)

    def test_an_arriving_turnover_schedules_a_save(self, window: DrivenWindow) -> None:
        window.set_batch(Batch())
        window._take_scanned(Turnover("t1", Path("/s")), [row(turnover_id="t1")], {})
        assert window.autosave.pending

    def test_scan_re_tries_only_the_turnovers_with_no_rows(self, window: DrivenWindow) -> None:
        """A turnover with rows is never re-scanned: the rows carry the editor's edits."""
        window.set_batch(
            batch(
                row(turnover_id="t1"),
                turnovers=[Turnover("t1", Path("/s/t1")), Turnover("t2", Path("/s/t2"))],
            )
        )
        started = stub_scanner(window)
        window.action_scan.trigger()
        assert started == [[(Path("/s/t2"), "t2")]]

    def test_scan_is_dead_when_every_turnover_has_rows(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row(turnover_id="t1"), turnovers=[Turnover("t1", Path("/s/t1"))]))
        assert not window.action_scan.isEnabled()

    def test_a_turnover_that_scanned_to_nothing_says_so_with_a_way_to_find_out_why(
        self, window: DrivenWindow
    ) -> None:
        window.set_batch(Batch())
        window._take_scanned(Turnover("t1", Path("/source/t1")), [], {})

        assert window.list_pages.currentIndex() == 1
        assert NO_ROWS_TEXT in window.list_empty_text.text()
        assert "#issues" in window.list_empty_text.text()

    def test_the_next_turnover_id_steps_past_the_ones_in_use(self, window: DrivenWindow) -> None:
        window.set_batch(batch(turnovers=[Turnover("t1", Path("/a")), Turnover("t3", Path("/b"))]))
        assert window._next_turnover_id() == "t4"

    def test_nothing_can_be_added_while_a_scan_is_running(self, window: DrivenWindow) -> None:
        window.set_batch(Batch())
        stub_scanner(window, busy=True)
        window._scan([(Path("/s/t1"), "t1")])

        assert not window.action_add_turnover.isEnabled()
        assert not window.action_scan.isEnabled()


class TestTheIssuesDock:
    """M5.4's other half. UI_SPEC section 6, driven from the window."""

    def test_it_fills_when_a_batch_is_opened(self, window: DrivenWindow) -> None:
        window.set_batch(batch(warn(row())))
        assert window.issues.count == 1

    def test_it_empties_when_another_batch_replaces_it(self, window: DrivenWindow) -> None:
        window.set_batch(batch(warn(row())))
        window.set_batch(batch(row()))
        assert window.issues.count == 0

    def test_an_edit_re_checks_the_row_and_the_dock_follows(self, window: DrivenWindow) -> None:
        """M5.3 re-runs that row's rules on a commit, so the dock is what shows it.

        QC-032 rather than a rule about the value being unreadable: a range the media
        cannot satisfy is stored and then reported, which is the whole reason the dock
        has to keep up with the typing.
        """
        window.set_batch(batch(row()), tmp_batch_path(window))
        assert "QC-032" not in rules_shown(window)
        proxy = window.shot_list.proxy
        index = proxy.index(0, IN, proxy.index(0, 0))
        assert proxy.setData(index, "400", Qt.ItemDataRole.EditRole)

        assert "QC-032" in rules_shown(window)

    def test_a_turnover_arriving_reaches_the_dock(self, window: DrivenWindow) -> None:
        window.set_batch(Batch())
        window._take_scanned(Turnover("t1", Path("/s/t1")), [row(turnover_id="t1")], {})
        assert window.issues.count > 0

    def test_double_clicking_an_issue_selects_its_shot_in_the_list(
        self, window: DrivenWindow
    ) -> None:
        wanted = warn(row("MELT0002_pl01"))
        window.set_batch(batch(row(), wanted))
        window.issues.itemDoubleClicked.emit(window.issues.topLevelItem(0), 0)

        assert window.shot_list.current_shot_row() is wanted

    def test_it_reaches_a_shot_the_search_box_had_hidden(self, window: DrivenWindow) -> None:
        """Otherwise the double-click silently does nothing, because of a search the
        editor typed a minute ago and has stopped looking at."""
        wanted = warn(row("MELT0002_pl01"))
        window.set_batch(batch(row(), wanted))
        window.batch_bar.search.setText("MELT0001")
        window.issues.itemDoubleClicked.emit(window.issues.topLevelItem(0), 0)

        assert window.shot_list.current_shot_row() is wanted

    def test_the_empty_state_link_brings_the_dock_up(self, window: DrivenWindow) -> None:
        """Section 10: no clips found, plus a link to the Issues dock."""
        window.set_batch(Batch())
        window._take_scanned(Turnover("t1", Path("/s/t1")), [], {})
        window.bottom_tabs.setCurrentIndex(BOTTOM_TABS.index("Log"))
        window.list_empty_text.linkActivated.emit("#issues")

        assert window.bottom_tabs.currentWidget() is window.issues


class TestClosingWithWorkInHand:
    def test_a_never_saved_batch_can_refuse_the_close(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()))
        edit(window, "not finished yet")
        window.unsaved_answer = QMessageBox.StandardButton.Cancel
        window.close()
        assert window.autosave.pending

    def test_answering_save_writes_it(self, window: DrivenWindow, tmp_path: Path) -> None:
        window.set_batch(batch(row()))
        edit(window, "worth keeping")
        window.unsaved_answer = QMessageBox.StandardButton.Save
        window.save_answer = tmp_path / "melt.pibatch"
        window.close()

        assert batchfile.load(tmp_path / "melt.pibatch", reconcile=False).rows[0].notes == "worth keeping"

    def test_a_saved_batch_closes_without_asking(self, window: DrivenWindow) -> None:
        """Nothing is pending after the flush, so there is nothing to ask about."""
        window.set_batch(batch(row()), tmp_batch_path(window))
        edit(window, "checked")
        window.close()
        assert not window.autosave.pending

    def test_opening_another_batch_asks_about_this_one_first(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row(), name="first"))
        edit(window, "not finished yet")
        window.unsaved_answer = QMessageBox.StandardButton.Cancel
        window.open_answer = Path("/nowhere.pibatch")
        window.action_open.trigger()
        assert window.batch.name == "first"


class TestRunningABatch:
    """M5.5: what the window does before a job reaches a worker, and after one comes back.

    The pool has its own tests (`tests/test_runner.py`); `stub_runner` catches the jobs
    instead, because what these are about is the planning, the blocking and the banner.
    """

    def test_run_is_off_until_there_is_something_to_render(
        self, window: DrivenWindow
    ) -> None:
        assert not window.action_run.isEnabled()
        window.set_batch(Batch())
        assert not window.action_run.isEnabled()
        window.set_batch(batch(row()))
        assert window.action_run.isEnabled()

    def test_a_run_plans_the_batch_and_hands_the_jobs_over(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()

        assert started and [job.shot_code for job in started[0]] == ["MELT0001"] * 4
        assert [item.name for item in window.batch.rows[0].deliverables] == [
            job.name for job in started[0]
        ]

    def test_a_batch_with_no_delivery_root_is_asked_once(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """Section 7: Run opens no dialog if the root is set, and prompts once if not."""
        window.set_batch(batch(row(), delivery_root=None))
        started = stub_runner(window)
        window.folder_answer = tmp_path
        window.action_run.trigger()

        assert window.batch.delivery_root == tmp_path
        assert len(started) == 1

    def test_refusing_to_name_a_delivery_root_renders_nothing(
        self, window: DrivenWindow
    ) -> None:
        window.set_batch(batch(row(), delivery_root=None))
        started = stub_runner(window)
        window.action_run.trigger()
        assert started == []

    def test_a_batch_scope_error_stops_the_run_and_says_so(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """FR-6: an error about the batch blocks it, and one about a row does not."""
        # A delivery root that is a file: QC-062 refuses it and nothing can be written.
        blocked = tmp_path / "not-a-folder"
        blocked.write_text("")
        window.set_batch(batch(fail(row()), delivery_root=blocked))
        started = stub_runner(window)
        window.action_run.trigger()

        assert started == []
        assert window.problems and "QC-0" in window.problems[0][1]
        assert window.bottom_tabs.currentIndex() == BOTTOM_TABS.index("Issues")

    def test_a_row_scope_error_does_not(self, window: DrivenWindow, tmp_path: Path) -> None:
        window.set_batch(batch(fail(row()), row("MELT0002_pl01"), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()
        assert started and window.problems == []

    def test_a_batch_that_plans_nothing_says_so_rather_than_starting(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(skipped=True, skip_reason="not needed"), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()

        assert started == []
        assert window.statusBar().currentMessage() == NOTHING_TO_RENDER

    def test_nothing_else_can_touch_the_batch_while_it_runs(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """New and Open would swap the batch the run is writing into."""
        window.set_batch(batch(row(), delivery_root=tmp_path))
        stub_runner(window, busy=True)
        window.action_run.trigger()

        assert not window.action_run.isEnabled()
        assert not window.action_new.isEnabled()
        assert not window.action_open.isEnabled()
        assert not window.action_add_turnover.isEnabled()
        assert window.action_stop.isEnabled()

    def test_progress_reaches_the_status_bar_and_the_rows(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window, busy=True)
        window.action_run.trigger()
        window._run_progressed(Progress(started[0][0].name, "frame", 112, 224))
        window._show_run_progress()

        assert "%" in window.statusBar().currentMessage()
        assert window.progress.isVisible() or window.progress.value() > 0
        assert window.shot_model.state_for(window.batch.rows[0]) is RowState.RENDERING

    def test_all_four_surfaces_report_the_same_run(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """Section 7.1: the strip's bar for the batch, its line for the step, the
        status bar for the numbers, the Progress column for the shot. One `RunProgress`
        behind all four, so they cannot disagree about how far along the run is."""
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window, busy=True)
        window.action_run.trigger()
        window._run_progressed(Progress(started[0][0].name, "started", 0, 100))
        window._run_progressed(Progress(started[0][0].name, "frame", 50, 100))
        window._show_run_progress()

        percent = window._run_progress.percent  # type: ignore[union-attr]
        assert window.run_strip.state == "running"
        assert window.run_strip.bar.value() == percent
        assert window.run_strip.line.text() == f"{RENDERING} {started[0][0].name}"
        assert f"{percent}%" in window.statusBar().currentMessage()

    def test_the_line_names_the_steps_either_side_of_the_pool(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """Planning and writing the spreadsheets both block the UI thread, so a run
        that said nothing about them would look like a window that had stopped."""
        window.set_batch(batch(row(), delivery_root=tmp_path))
        said: list[str] = []
        window.run_strip.say = said.append  # type: ignore[assignment]
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0]), False)

        assert said[0] == CHECKING_BATCH
        assert "Planning 1 shots" in said
        assert WRITING_REPORTS in said
        assert said.index(WRITING_REPORTS) == len(said) - 1

    def test_a_run_that_never_starts_takes_the_strip_away_again(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """A bar left over a batch that was refused is a run that never happened."""
        window.set_batch(batch(row(skipped=True, skip_reason="not needed"), delivery_root=tmp_path))
        stub_runner(window)
        window.action_run.trigger()

        assert window.run_strip.state == "empty"

    def test_a_blocked_batch_takes_the_strip_away_too(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        blocked = tmp_path / "not-a-folder"
        blocked.write_text("")
        window.set_batch(batch(fail(row()), delivery_root=blocked))
        stub_runner(window)
        window.action_run.trigger()

        assert window.run_strip.state == "empty"

    def test_stop_asks_the_pool_to_stop_and_then_asks_nothing_else(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path))
        stub_runner(window, busy=True)
        window.action_run.trigger()
        cancelled: list[bool] = []
        window.runner.cancel = lambda: cancelled.append(True)  # type: ignore[method-assign]
        window.action_stop.trigger()

        assert cancelled == [True]

    def test_what_comes_back_is_written_onto_the_rows(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path), tmp_batch_path(window))
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0]), False)

        assert {item.status for item in window.batch.rows[0].deliverables} == {"done"}
        assert window.shot_model.state_for(window.batch.rows[0]) is RowState.DONE

    def test_the_banner_says_what_landed_and_where_the_exports_went(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0]), False)

        assert not window.run_strip.banner.isHidden()
        assert "Batch complete: 4 done, 0 failed, 0 skipped." in window.run_strip.banner.text()
        reports = naming.reports_dir(tmp_path, "MELT")
        assert str(reports) in window.run_strip.banner.text()
        assert sorted(path.name.split("_")[0] for path in reports.iterdir()) == ["qc", "shot"]

    def test_a_stopped_run_says_so_rather_than_calling_itself_complete(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0], status="skipped"), True)

        assert window.run_strip.banner.text().startswith("Run stopped: 0 done, 0 failed, 4 skipped.")

    def test_the_link_is_the_accent_rather_than_qt_s_own_blue(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """Written into the anchor because nothing else can reach it: a stylesheet
        cannot select an anchor inside a QLabel, and it overrides the palette that
        could. Without it the path is #0000ff on a #1b1e23 band."""
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0]), False)

        assert f'style="color:{LINK_COLOR}"' in window.run_strip.banner.text()

    def test_the_banner_link_opens_the_reports_folder(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0]), False)
        window._open_reports()

        assert window.opened_folders == [naming.reports_dir(tmp_path, "MELT")]

    def test_exports_that_cannot_be_written_are_reported_rather_than_faked(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """A batch whose rows have no shot code has no show to file the reports under."""
        window.set_batch(batch(row("not_a_shot_name"), delivery_root=tmp_path))
        window._run_finished([], False)

        assert window.problems and "show" in window.problems[0][1]
        assert "No exports were written." in window.run_strip.banner.text()

    def test_a_new_batch_clears_the_banner_of_the_last_one(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row(), delivery_root=tmp_path))
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0]), False)
        window.set_batch(Batch())

        assert not window.run_strip.banner.isVisible()
        assert window.run_strip.state == "empty"


class TestTheMetadataPane:
    """M5.6. The window's half of it: where the pane gets its updates from, which is
    the thing the plan said to decide first. `tests/test_metadata.py` has the rest."""

    def test_it_starts_empty_and_says_so(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()))
        assert not window.metadata.placeholder.isHidden()
        assert window.metadata.placeholder.text() == NO_SELECTION

    def test_selecting_a_row_fills_it(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()))
        window.shot_list.select_row(window.batch.rows[0])
        assert [box.title for box in window.metadata._boxes] == [
            "Identity",
            "Source media",
            "Frame rate",
            "Range",
            "Turnover",
            "QC",
        ]

    def test_selecting_two_rows_shows_what_they_agree_on(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row(), row("MELT0002_pl01", record_in=224)))
        window.shot_list.selectAll()
        text = pane_text(window)
        assert "2 shots selected" in window.metadata.summary.text()
        assert f"Clip name: {MIXED}" in text
        assert "Show: MELT" in text

    def test_selecting_a_turnover_header_shows_the_turnover_alone(
        self, window: DrivenWindow
    ) -> None:
        window.set_batch(batch(row()))
        header = window.shot_list.proxy.index(0, 0)
        window.shot_list.setCurrentIndex(header)
        assert [box.title for box in window.metadata._boxes] == ["Turnover"]

    def test_a_committed_cell_refreshes_the_pane(self, window: DrivenWindow) -> None:
        """The selection has not moved, so a pane on that signal alone would be showing
        the value the editor just replaced."""
        window.set_batch(batch(row()))
        window.shot_list.select_row(window.batch.rows[0])
        assert "Current in/out: 8 - 231" in pane_text(window)
        set_in(window, "20")
        assert "Current in/out: 20 - 231" in pane_text(window)

    def test_a_finished_run_refreshes_the_pane(self, window: DrivenWindow, tmp_path: Path) -> None:
        """QC-150 and QC-151 are written by `apply_results`, so the QC section is only
        right after it."""
        window.set_batch(batch(row(), delivery_root=tmp_path))
        window.shot_list.select_row(window.batch.rows[0])
        started = stub_runner(window)
        window.action_run.trigger()
        window._run_finished(done(started[0], status="failed"), False)

        assert "Results: none" not in pane_text(window)

    def test_a_new_batch_empties_the_pane(self, window: DrivenWindow) -> None:
        window.set_batch(batch(row()))
        window.shot_list.select_row(window.batch.rows[0])
        window.set_batch(Batch())
        assert window.metadata._boxes == []

    def test_a_rule_id_brings_the_issues_dock_forward(self, window: DrivenWindow) -> None:
        window.set_batch(batch(fail(row())))
        window.shot_list.select_row(window.batch.rows[0])
        window.metadata.issue_clicked.emit("QC-011")

        assert window.bottom_tabs.currentIndex() == BOTTOM_TABS.index("Issues")
        current = window.issues.currentItem()
        assert current is not None and current.text(1) == "QC-011"

    def test_ctrl_i_is_what_toggles_it(self, window: DrivenWindow) -> None:
        assert window.action_metadata.shortcut() == QKeySequence("Ctrl+I")
        assert window.action_metadata.isCheckable()

    def test_the_pane_is_not_movable_out_of_its_place(self, window: DrivenWindow) -> None:
        """Section 1 calls it a fixed width reading surface, not a second workspace."""
        features = window.metadata_dock.features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetClosable
        assert not features & QDockWidget.DockWidgetFeature.DockWidgetFloatable
        assert not features & QDockWidget.DockWidgetFeature.DockWidgetMovable

    def test_what_the_editor_collapsed_is_remembered(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row()))
        window.shot_list.select_row(window.batch.rows[0])
        next(box for box in window.metadata._boxes if box.title == "Range").set_open(False)
        window.close()

        reopened = DrivenWindow(window._settings_path)
        assert reopened.metadata.collapsed == ["Range"]

    def test_camdata_is_read_once_rather_than_per_selection(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """The pane redraws on every arrow key and this is the one field on disk."""
        camdata_file = tmp_path / "MELT0001_pl01_camData.txt"
        camdata_file.write_text("Lens: Zeiss Supreme Prime 35mm\n")
        sided = row()
        sided.side_files.camdata = camdata_file
        window.set_batch(batch(sided, row("MELT0002_pl01", record_in=224)))

        window.shot_list.select_row(window.batch.rows[0])
        assert "Lens: Zeiss Supreme Prime 35mm" in pane_text(window)
        camdata_file.write_text("Lens: something else\n")
        window.shot_list.select_row(window.batch.rows[1])
        window.shot_list.select_row(window.batch.rows[0])

        assert "Lens: Zeiss Supreme Prime 35mm" in pane_text(window), "read again off disk"

    def test_unreadable_camdata_is_not_the_pane_s_problem_to_report(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """QC-053 says so in the Issues dock; saying it twice is two places to correct."""
        sided = row()
        sided.side_files.camdata = tmp_path / "gone.txt"
        window.set_batch(batch(sided))
        window.shot_list.select_row(window.batch.rows[0])
        assert "camData:" in pane_text(window)


class TestTheRunStrip:
    """The widget itself. UI_SPEC section 7.1: three states and only ever one of them."""

    def test_a_strip_that_has_seen_no_run_is_nothing_at_all(self, qt_app: QApplication) -> None:
        """Hidden rather than an empty band: the height belongs to the list until a
        run wants it."""
        strip = RunStrip()
        assert strip.state == "empty"
        assert strip.isHidden()

    def test_a_run_shows_the_bar_and_the_line(self, qt_app: QApplication) -> None:
        strip = RunStrip()
        strip.start()
        strip.set_percent(40)
        strip.say("Rendering MELT0001_pl01_raw_4k_v01")

        assert strip.state == "running"
        assert strip.bar.value() == 40
        assert strip.line.text() == "Rendering MELT0001_pl01_raw_4k_v01"

    def test_the_banner_replaces_the_bar_rather_than_joining_it(
        self, qt_app: QApplication
    ) -> None:
        """A banner from the last run above the bar of this one is two answers to the
        same question."""
        strip = RunStrip()
        strip.start()
        strip.show_banner("Batch complete: 4 done, 0 failed, 0 skipped.")

        assert strip.state == "done"
        assert strip.running_side.isHidden()

    def test_a_second_run_puts_the_last_one_s_banner_away(self, qt_app: QApplication) -> None:
        strip = RunStrip()
        strip.show_banner("Batch complete: 4 done, 0 failed, 0 skipped.")
        strip.start()

        assert strip.state == "running"
        assert strip.banner.isHidden()

    def test_a_new_run_starts_the_bar_from_nothing(self, qt_app: QApplication) -> None:
        strip = RunStrip()
        strip.start()
        strip.set_percent(80)
        strip.say("Rendering MELT0001_pl01_raw_4k_v01")
        strip.start()

        assert strip.bar.value() == 0
        assert strip.line.text() == ""

    def test_a_percentage_outside_the_bar_is_clamped_rather_than_refused(
        self, qt_app: QApplication
    ) -> None:
        strip = RunStrip()
        strip.start()
        strip.set_percent(140)
        assert strip.bar.value() == 100

    def test_the_link_in_the_banner_is_forwarded(self, qt_app: QApplication) -> None:
        clicked: list[bool] = []
        strip = RunStrip()
        strip.link_activated.connect(lambda: clicked.append(True))
        strip.show_banner('Exports written to <a href="#reports">/tmp/x</a>')
        strip.banner.linkActivated.emit("#reports")

        assert clicked == [True]


def stub_scanner(window: DrivenWindow, busy: bool = False) -> list[list[tuple[Path, str]]]:
    """Catch what would have been handed to the worker thread, and say whether it is busy.

    The scanner has its own tests; what these are about is which folders the window
    decides to send, which is a question the thread cannot help answer.
    """
    started: list[list[tuple[Path, str]]] = []
    window.scanner.start = lambda folders, settings, probe_cache=None: started.append(folders)  # type: ignore[method-assign]
    if busy:
        # `busy` is "there is a thread", so a thread that was never started is the
        # smallest honest way to say so, and it goes out with the window.
        window.scanner._thread = QThread(window.scanner)
    return started


def stub_runner(window: DrivenWindow, busy: bool = False) -> list[list[DeliverableJob]]:
    """Catch what would have been handed to the pool, and say whether it is running.

    The runner has its own tests; what these are about is what the window planned and
    what it does with the answer, neither of which a process pool helps establish.
    """
    started: list[list[DeliverableJob]] = []

    def start(jobs: list[DeliverableJob], workers: int = 4) -> None:
        started.append(jobs)
        if busy:
            # `busy` is "there is a thread", so a thread that was never started is the
            # smallest honest way to say so, and it goes out with the window. Set from
            # inside `start` because a runner already busy would refuse the run.
            window.runner._thread = QThread(window.runner)
            window._update_state()

    window.runner.start = start  # type: ignore[method-assign]
    return started


def done(jobs: list[DeliverableJob], status: str = "done") -> list[Deliverable]:
    """What the pool hands back for jobs that all ended the same way."""
    written = []
    for job in jobs:
        deliverable = job.to_deliverable()
        deliverable.status = status  # type: ignore[assignment]
        deliverable.frame_count = job.frame_count
        written.append(deliverable)
    return written


def rules_shown(window: DrivenWindow) -> set[str]:
    """The rule IDs the Issues dock is showing right now."""
    items = [window.issues.topLevelItem(i) for i in range(window.issues.count)]
    return {item.text(1) for item in items if item is not None}


def tmp_batch_path(window: DrivenWindow) -> Path:
    """Beside the window's temporary settings file, which is already in `tmp_path`."""
    return window._settings_path.with_name("melt.pibatch")


def pane_text(window: DrivenWindow) -> str:
    """The metadata pane as `key: value`, which is what it is easiest to assert against."""
    return as_text(window.metadata.sections)


def set_in(window: DrivenWindow, text: str) -> None:
    """Commit the In cell the way the delegate does, through the proxy."""
    proxy = window.shot_list.proxy
    index = proxy.index(0, IN, proxy.index(0, 0))
    assert proxy.setData(index, text, Qt.ItemDataRole.EditRole)


def edit(window: DrivenWindow, notes: str) -> None:
    """Commit a Notes cell the way the delegate does, through the proxy."""
    proxy = window.shot_list.proxy
    index = proxy.index(0, NOTES, proxy.index(0, 0))
    assert proxy.setData(index, notes, Qt.ItemDataRole.EditRole)
