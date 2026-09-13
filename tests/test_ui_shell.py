"""The main window shell. `ui/app.py` and `ui/main_window.py`, M5.1.

Every test here runs on the offscreen platform, which is what lets the UI be checked on
both CI runners and on a machine with no display. What is asserted is what the window
is made of and what it remembers, not how it looks: a screenshot test would pin the
theme, and the theme is the one part of this a person has to judge (docs/MAC_SESSION.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from proingest.core import settings as core_settings
from proingest.ui import app as ui_app
from proingest.ui import paths
from proingest.ui.main_window import BOTTOM_TABS, EMPTY_STATE_TEXT, MainWindow


@pytest.fixture
def window(qt_app: QApplication, tmp_path: Path) -> MainWindow:
    """A window whose settings file is a temporary one, never the user's own."""
    return MainWindow(tmp_path / "settings.json")


REMEMBERED_SIZE = (640, 480)
"""Smaller than any screen this runs on. `restoreGeometry` clamps to the screen, and the
offscreen platform's is 800 by 800, so a larger size here would test the clamp instead."""


def actions(window: MainWindow) -> dict[str, QAction]:
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
    def test_every_action_in_the_spec_exists(self, window: MainWindow) -> None:
        """UI_SPEC section 1's three toolbar groups, in one place so none goes missing."""
        expected = {
            "New", "Open...", "Save",
            "Add Turnover", "Scan", "Run", "Stop",
            "Export", "Settings",
        }  # fmt: skip
        assert expected <= set(actions(window))

    def test_the_toolbar_carries_them_in_the_spec_s_order(self, window: MainWindow) -> None:
        named = [action.text() for action in window.toolbar.actions() if action.text()]
        assert named == [
            "New", "Open...", "Save",
            "Add Turnover", "Scan", "Run", "Stop",
            "Export", "Settings",
        ]  # fmt: skip

    def test_the_groups_are_separated_as_section_1_draws_them(self, window: MainWindow) -> None:
        separators = [action for action in window.toolbar.actions() if action.isSeparator()]
        assert len(separators) == 2

    def test_nothing_with_no_feature_behind_it_is_enabled(self, window: MainWindow) -> None:
        """Disabled rather than absent, and never a live-looking button that does nothing."""
        for name in ("New", "Open...", "Save", "Add Turnover", "Scan", "Run", "Stop", "Export"):
            assert not actions(window)[name].isEnabled(), name

    def test_quit_works_from_the_first_launch(self, window: MainWindow) -> None:
        assert actions(window)["Quit"].isEnabled()


class TestTheKeyboardModel:
    """UI_SPEC section 4. `Ctrl` is portable and Qt maps it onto Cmd for macOS itself."""

    @pytest.mark.parametrize(
        ("name", "keys"),
        [("Run", "Ctrl+R"), ("Stop", "Ctrl+.")],
    )
    def test_the_shortcuts_the_spec_names_outright(
        self, window: MainWindow, name: str, keys: str
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
        self, window: MainWindow, name: str, standard: QKeySequence.StandardKey
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
        self, window: MainWindow, name: str, role: QAction.MenuRole
    ) -> None:
        """Without these macOS leaves them in the window's menus, where nobody looks."""
        assert actions(window)[name].menuRole() == role


class TestTheLayout:
    def test_the_empty_state_says_what_section_10_says(self, window: MainWindow) -> None:
        label = window.findChild(QLabel, "empty_state_text")
        assert label is not None
        assert label.text() == EMPTY_STATE_TEXT

    def test_its_two_buttons_trigger_the_toolbar_s_own_actions(self, window: MainWindow) -> None:
        """One action per thing the tool can do, whichever surface the user reaches it from."""
        buttons = [button.text() for button in window.findChildren(QPushButton)]
        assert buttons == ["New batch", "Open batch..."]

    def test_they_follow_their_action_when_it_is_enabled(self, window: MainWindow) -> None:
        """So the chunk that wires New has one line to change rather than two surfaces."""
        button = next(b for b in window.findChildren(QPushButton) if b.text() == "New batch")
        assert not button.isEnabled()
        window.action_new.setEnabled(True)
        assert button.isEnabled()

    def test_the_bottom_dock_has_its_three_tabs(self, window: MainWindow) -> None:
        names = [window.bottom_tabs.tabText(i) for i in range(window.bottom_tabs.count())]
        assert names == list(BOTTOM_TABS)

    def test_the_status_bar_progress_is_hidden_until_a_run(self, window: MainWindow) -> None:
        assert not window.progress.isVisible()


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
