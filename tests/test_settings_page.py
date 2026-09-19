"""The Settings page: what it offers, what it reads back, and what an Apply reaches.

M5.7.2, PRD FR-12 and UI_SPEC section 9. Split the way the code is: the form is a value
and is asserted without a window, and the dialog is driven offscreen through the same
harness the rest of the interface uses.

**The page is never opened by `exec`.** A modal on the offscreen platform is a hung
suite rather than a failed assertion, so `DrivenWindow` answers it, exactly as it
answers every other dialog the window can open.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
)

from proingest.core import color, exr, ffmpeg, logsetup, naming, qc
from proingest.core import settings as core_settings
from proingest.core.settings import AppSettings
from proingest.ui import settings_form
from proingest.ui.main_window import SETTINGS_APPLIED
from proingest.ui.settings_dialog import SettingsDialog
from tests.fixtures.batches import batch, row
from tests.test_ui_shell import DrivenWindow, set_in


class TestTheForm:
    """`ui/settings_form.py`: the field list, with no widget anywhere near it."""

    def test_it_offers_every_section_the_spec_lists(self) -> None:
        titles = [section.title for section in settings_form.sections()]
        assert titles == ["General", "Rules", "Colour", "Naming", "Output", "Advanced"]

    def test_the_sections_with_nothing_behind_them_say_so_and_are_disabled(self) -> None:
        """Disabled rather than absent, like the toolbar in M5.1: the shape is the spec."""
        for section in settings_form.sections():
            if section.enabled:
                assert section.fields, section.title
            else:
                assert not section.fields and section.note, section.title

    def test_every_field_belongs_to_something_that_can_be_written(self) -> None:
        """The prefix is what stops a value being written to the wrong object."""
        for section in settings_form.sections():
            for field in section.fields:
                assert field.key.split(".")[0] in {"app", "rules", "readonly"}, field.key

    def test_every_rules_field_is_a_real_threshold(self) -> None:
        """A field naming a threshold that does not exist would silently do nothing."""
        names = {f.name for f in qc.RuleSettings.__dataclass_fields__.values()}
        for section in settings_form.sections():
            for field in section.fields:
                if field.key.startswith("rules."):
                    assert field.key.removeprefix("rules.") in names, field.key

    def test_it_offers_no_source_encoding_setting(self) -> None:
        """There is no mode and no batch wide encoding (2026-09-12). OQ-39 dissolved."""
        keys = [f.key for s in settings_form.sections() for f in s.fields]
        assert not [key for key in keys if "encoding" in key]

    def test_the_pinned_colour_values_are_read_rather_than_copied(self) -> None:
        values = settings_form.readonly_values()
        assert values["readonly.config"] == color.BUILTIN_CONFIG
        assert values["readonly.working_space"] == color.WORKING_SPACE == "ACEScct"
        assert color.VIEW in values["readonly.output_transform"]
        for written, space in color.INPUT_TRANSFORMS.items():
            assert f"{written} = {space}" in values["readonly.input_transforms"]

    def test_values_round_trip_through_the_form(self) -> None:
        app = AppSettings(workers=7, show_pattern="ABC", path_map={"G:/": "/Volumes/g"})
        rules = qc.RuleSettings(min_duration_frames=11, target_resolution=(1920, 1080))
        applied = settings_form.apply_values(
            AppSettings(), settings_form.to_values(app, rules), qc.RuleSettings()
        )
        assert applied == rules

    def test_a_missing_key_leaves_the_app_setting_as_it_was(self) -> None:
        """A field that would not parse is absent, and absent must change nothing."""
        app = AppSettings(workers=7)
        settings_form.apply_values(app, settings_form.to_values(app, qc.RuleSettings()) | {})
        assert app.workers == 7

    def test_applying_records_the_thresholds_as_the_new_default(self) -> None:
        """What a new batch starts from, which is why they are on the app settings too."""
        app = AppSettings()
        values = settings_form.to_values(app, qc.RuleSettings(min_duration_frames=11))
        settings_form.apply_values(app, values)
        assert app.rules["min_duration_frames"] == 11

    def test_an_empty_pattern_means_the_default_rather_than_a_copy_of_it(self) -> None:
        assert settings_form.show_pattern_of(AppSettings()) == naming.DEFAULT_SHOW_PATTERN
        assert settings_form.show_pattern_of(AppSettings(show_pattern="ABC")) == "ABC"


@pytest.fixture
def dialog(qt_app: QApplication) -> SettingsDialog:
    return SettingsDialog(AppSettings(), qc.RuleSettings())


@pytest.fixture
def window(qt_app: QApplication, tmp_path: Path) -> DrivenWindow:
    """The same harness `test_ui_shell.py` uses, against a settings file of its own."""
    return DrivenWindow(tmp_path / "settings.json")


def editor(dialog: SettingsDialog, key: str) -> object:
    return dialog._editors[key]


@pytest.fixture
def restore_process() -> Iterator[None]:
    """Put back everything `apply_to_process` moves, since all four are process wide."""
    level = logging.getLogger().level
    override = ffmpeg.current_override()
    crf = ffmpeg.current_reference_crf()
    compression = exr.current_compression_level()
    yield
    logging.getLogger().setLevel(level)
    ffmpeg.set_override(override)
    ffmpeg.set_reference_crf(crf)
    exr.set_compression_level(compression)


class TestTheDialog:
    """`ui/settings_dialog.py`: the widgets, and what they hand back."""

    def test_it_draws_a_page_per_section(self, dialog: SettingsDialog) -> None:
        assert dialog.list.count() == len(settings_form.sections())
        assert dialog.pages.count() == dialog.list.count()

    def test_choosing_a_section_shows_its_page(self, dialog: SettingsDialog) -> None:
        dialog.list.setCurrentRow(2)
        assert dialog.pages.currentIndex() == 2

    def test_the_pages_with_nothing_behind_them_are_disabled(self, dialog: SettingsDialog) -> None:
        for index, section in enumerate(settings_form.sections()):
            page = dialog.pages.widget(index)
            assert page is not None and page.isEnabled() == section.enabled, section.title

    def test_a_threshold_typed_in_comes_back_out(self, dialog: SettingsDialog) -> None:
        spin = editor(dialog, "rules.min_duration_frames")
        assert isinstance(spin, QSpinBox)
        spin.setValue(96)
        _, rules = dialog.result_settings()
        assert rules.min_duration_frames == 96

    def test_a_resolution_is_read_as_two_numbers(self, dialog: SettingsDialog) -> None:
        edit = editor(dialog, "rules.target_resolution")
        assert isinstance(edit, QLineEdit)
        edit.setText("1920 x 1080")
        _, rules = dialog.result_settings()
        assert rules.target_resolution == (1920, 1080)

    def test_a_half_typed_resolution_changes_nothing(self, dialog: SettingsDialog) -> None:
        """UI_SPEC section 5's rule for In and Out: a value that will not parse is not
        a value, and correcting it to something plausible is worse than ignoring it."""
        edit = editor(dialog, "rules.target_resolution")
        assert isinstance(edit, QLineEdit)
        edit.setText("3840")
        _, rules = dialog.result_settings()
        assert rules.target_resolution == qc.RuleSettings().target_resolution

    def test_a_toggle_comes_back_out(self, dialog: SettingsDialog) -> None:
        check = editor(dialog, "rules.allow_non_4k")
        assert isinstance(check, QCheckBox)
        check.setChecked(True)
        _, rules = dialog.result_settings()
        assert rules.allow_non_4k

    def test_the_path_map_is_a_line_per_rewrite(self, dialog: SettingsDialog) -> None:
        block = editor(dialog, "app.path_map")
        assert isinstance(block, QPlainTextEdit)
        block.setPlainText("G:/media = /Volumes/drive\n\nnonsense\nH:/ = /Volumes/h")
        app, _ = dialog.result_settings()
        assert app.path_map == {"G:/media": "/Volumes/drive", "H:/": "/Volumes/h"}

    def test_the_folder_chooser_writes_into_the_field(self, dialog: SettingsDialog, tmp_path: Path) -> None:
        dialog.ask_folder = lambda start: str(tmp_path)  # type: ignore[method-assign]
        row_widget = editor(dialog, "app.color_session_folder")
        assert isinstance(row_widget, QWidget) and not isinstance(row_widget, QLineEdit)
        edit = row_widget.findChild(QLineEdit)
        assert isinstance(edit, QLineEdit)
        dialog._choose_into(edit)
        app, _ = dialog.result_settings()
        assert app.color_session_folder == str(tmp_path)

    def test_a_read_only_value_is_never_written_back(self, dialog: SettingsDialog) -> None:
        assert not [key for key in dialog.values() if key.startswith("readonly.")]


class TestApplyingFromTheWindow:
    """What an Apply reaches: the file, the open batch, and the checks."""

    def apply(self, window: DrivenWindow, edit: object = None) -> None:
        window.settings_answer = QDialog.DialogCode.Accepted
        if edit is not None:
            window.settings_edit = edit  # type: ignore[assignment]
        window.action_settings.trigger()

    def test_cancelling_writes_nothing(self, window: DrivenWindow, tmp_path: Path) -> None:
        window.action_settings.trigger()
        assert not (tmp_path / "settings.json").exists()

    def test_applying_saves_the_settings_file(self, window: DrivenWindow, tmp_path: Path) -> None:
        def edit(dialog: SettingsDialog) -> None:
            dialog._editors["app.workers"].setValue(9)  # type: ignore[attr-defined]

        self.apply(window, edit)
        assert core_settings.load(tmp_path / "settings.json").workers == 9

    def test_applying_writes_the_thresholds_onto_the_open_batch(self, window: DrivenWindow) -> None:
        """A batch keeps its own copy, so changing these later cannot re-judge it."""

        def edit(dialog: SettingsDialog) -> None:
            dialog._editors["rules.min_duration_frames"].setValue(400)  # type: ignore[attr-defined]

        window.set_batch(batch(row()))
        self.apply(window, edit)
        assert qc.settings_for(window.batch).min_duration_frames == 400

    def test_applying_re_checks_the_batch(self, window: DrivenWindow) -> None:
        """The whole point of the Rules section: the list says so immediately."""

        def edit(dialog: SettingsDialog) -> None:
            dialog._editors["rules.min_duration_frames"].setValue(400)  # type: ignore[attr-defined]

        window.set_batch(batch(row()))
        assert "QC-033" not in [result.rule_id for result in window.batch.rows[0].qc]
        self.apply(window, edit)
        assert "QC-033" in [result.rule_id for result in window.batch.rows[0].qc]
        assert window.statusBar().currentMessage() == SETTINGS_APPLIED

    def test_an_edit_after_applying_is_judged_by_the_new_thresholds(self, window: DrivenWindow) -> None:
        """A commit re-runs the row's rules; they must be the ones Apply just wrote."""

        def edit(dialog: SettingsDialog) -> None:
            dialog._editors["rules.min_duration_frames"].setValue(400)  # type: ignore[attr-defined]

        window.set_batch(batch(row()))
        self.apply(window, edit)
        set_in(window, "9")
        assert "QC-033" in [result.rule_id for result in window.batch.rows[0].qc]

    def test_it_opens_with_no_batch_and_writes_only_the_file(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        """Settings is where a new batch's defaults are set, so it cannot wait for one."""

        def edit(dialog: SettingsDialog) -> None:
            dialog._editors["rules.expected_handle_frames"].setValue(24)  # type: ignore[attr-defined]

        self.apply(window, edit)
        assert core_settings.load(tmp_path / "settings.json").rules["expected_handle_frames"] == 24

    def test_a_new_batch_starts_from_those_defaults(self, window: DrivenWindow) -> None:
        def edit(dialog: SettingsDialog) -> None:
            dialog._editors["rules.expected_handle_frames"].setValue(24)  # type: ignore[attr-defined]

        self.apply(window, edit)
        window.action_new.trigger()
        assert qc.settings_for(window.batch).expected_handle_frames == 24

    def test_unusable_defaults_in_the_file_do_not_stop_the_page_opening(self, window: DrivenWindow) -> None:
        """Refusing over a hand edited file would leave no way to fix the hand edit."""
        window._settings.rules = {"nonsense": 1}
        assert window._app_rules() == qc.RuleSettings()

    def test_unusable_defaults_in_the_file_do_not_stop_a_new_batch(self, window: DrivenWindow) -> None:
        """New copies the defaults onto the batch; the same fallback has to apply there."""
        window._settings.rules = {"nonsense": 1}
        window.action_new.trigger()
        assert window._batch_open
        assert qc.settings_for(window.batch) == qc.RuleSettings()


def test_every_rule_id_a_help_line_names_is_live_rather_than_retired() -> None:
    """A help line naming a retired rule sends somebody to a row that says "was".

    It catches a typo and a rule that has since been retired; **it cannot catch a help
    line naming the wrong live rule**, which is what two of these did when the page was
    first drawn, and what was found by looking at the page rather than by any test.
    Asserting that would mean writing the mapping out a second time here.
    """
    table = Path("docs/QC_RULES.md").read_text()
    rows = {line.split("|")[1].strip(): line for line in table.splitlines() if line.startswith("| QC-")}
    for section in settings_form.sections():
        for field in section.fields:
            for rule_id in re.findall(r"QC-\d{3}", field.help):
                assert rule_id in rows, f"{field.key} names {rule_id}, which is not a rule"
                assert "RETIRED" not in rows[rule_id], f"{field.key} names retired {rule_id}"


class TestTheAdvancedSection:
    """M5.8.3. The section M5.7.2 listed and disabled, waiting on there being a log."""

    def test_the_level_is_a_choice_rather_than_something_to_type(self, dialog: SettingsDialog) -> None:
        """A misspelt level in a settings file is a tool logging the wrong amount."""
        box = editor(dialog, "app.log_level")
        assert isinstance(box, QComboBox)
        assert [box.itemText(i) for i in range(box.count())] == list(logsetup.LEVEL_NAMES)

    def test_a_level_chosen_comes_back_out(self, dialog: SettingsDialog) -> None:
        box = editor(dialog, "app.log_level")
        assert isinstance(box, QComboBox)
        box.setCurrentText("Debug")
        app, _ = dialog.result_settings()
        assert app.log_level == "Debug"

    def test_the_page_says_where_the_log_file_is(self, dialog: SettingsDialog) -> None:
        """The one thing a person on this page wants and cannot otherwise find."""
        shown = settings_form.readonly_values()["readonly.log_file"]
        assert shown.endswith(logsetup.LOG_FILENAME)
        assert editor(dialog, "readonly.log_file") is not None

    def test_an_ffmpeg_path_typed_in_comes_back_out(self, dialog: SettingsDialog) -> None:
        row_widget = editor(dialog, "app.ffmpeg_path")
        assert isinstance(row_widget, QWidget)
        edit = row_widget.findChild(QLineEdit)
        assert edit is not None
        edit.setText("/opt/ffmpeg/bin")
        app, _ = dialog.result_settings()
        assert app.ffmpeg_path == "/opt/ffmpeg/bin"


class TestTheOutputSection:
    """M5.12. The last section M5.7.2 listed and disabled, waiting on the worker channel."""

    def test_every_section_is_live_now(self) -> None:
        assert [s.title for s in settings_form.sections() if not s.enabled] == []

    def test_it_offers_the_two_the_prd_lists(self) -> None:
        section = next(s for s in settings_form.sections() if s.title == settings_form.OUTPUT)
        assert [f.key for f in section.fields] == ["app.reference_crf", "app.exr_compression_level"]

    def test_the_quality_is_bounded_by_what_x264_accepts(self) -> None:
        """A rate factor outside 0 to 51 is an encode that fails on the first frame."""
        section = next(s for s in settings_form.sections() if s.title == settings_form.OUTPUT)
        crf = section.fields[0]
        assert (crf.minimum, crf.maximum) == (0, 51)

    def test_a_quality_typed_in_comes_back_out(self, dialog: SettingsDialog) -> None:
        spin = editor(dialog, "app.reference_crf")
        assert isinstance(spin, QSpinBox)
        spin.setValue(23)
        app, _ = dialog.result_settings()
        assert app.reference_crf == 23

    def test_a_compression_level_typed_in_comes_back_out(self, dialog: SettingsDialog) -> None:
        spin = editor(dialog, "app.exr_compression_level")
        assert isinstance(spin, QSpinBox)
        spin.setValue(60)
        app, _ = dialog.result_settings()
        assert app.exr_compression_level == 60

    def test_the_page_opens_on_the_spec_values(self, dialog: SettingsDialog) -> None:
        """The defaults are the spec's, read from core rather than typed in twice."""
        app, _ = dialog.result_settings()
        assert app.reference_crf == ffmpeg.REFERENCE_CRF
        assert app.exr_compression_level == exr.DWA_COMPRESSION_LEVEL

    def test_applying_saves_them(self, window: DrivenWindow, tmp_path: Path) -> None:
        def edit(dialog: SettingsDialog) -> None:
            dialog._editors["app.reference_crf"].setValue(23)  # type: ignore[attr-defined]
            dialog._editors["app.exr_compression_level"].setValue(60)  # type: ignore[attr-defined]

        window.settings_answer = QDialog.DialogCode.Accepted
        window.settings_edit = edit
        window.action_settings.trigger()
        saved = core_settings.load(tmp_path / "settings.json")
        assert (saved.reference_crf, saved.exr_compression_level) == (23, 60)


class TestPuttingThemInForce:
    """`apply_to_process`, which is apart from `apply_values` on purpose."""

    def test_the_level_reaches_the_root_logger(self, restore_process: None) -> None:
        settings_form.apply_to_process(AppSettings(log_level="Error"))
        assert logging.getLogger().getEffectiveLevel() == logging.ERROR

    def test_a_level_the_file_does_not_explain_falls_back_to_the_default(self, restore_process: None) -> None:
        """A settings file is disposable; an unreadable value is not an error."""
        settings_form.apply_to_process(AppSettings(log_level="Verbose"))
        assert logging.getLogger().getEffectiveLevel() == logsetup.DEFAULT_LEVEL

    def test_the_ffmpeg_override_reaches_resolve_tool(self, restore_process: None, tmp_path: Path) -> None:
        binary = tmp_path / "ffmpeg"
        binary.write_text("#!/bin/sh\n")
        settings_form.apply_to_process(AppSettings(ffmpeg_path=str(tmp_path)))
        assert ffmpeg.resolve_tool("ffmpeg") == binary

    def test_an_override_that_is_not_there_is_an_error_rather_than_a_fallback(
        self, restore_process: None, tmp_path: Path
    ) -> None:
        """An override quietly ignored is a render done with the wrong build of ffmpeg."""
        settings_form.apply_to_process(AppSettings(ffmpeg_path=str(tmp_path / "nowhere")))
        with pytest.raises(ffmpeg.FFmpegNotFound):
            ffmpeg.resolve_tool("ffmpeg")

    def test_an_empty_override_restores_the_normal_order(self, restore_process: None, tmp_path: Path) -> None:
        settings_form.apply_to_process(AppSettings(ffmpeg_path=str(tmp_path)))
        settings_form.apply_to_process(AppSettings())
        assert ffmpeg.current_override() is None

    def test_the_quality_reaches_the_encode_command(self, restore_process: None) -> None:
        settings_form.apply_to_process(AppSettings(reference_crf=23))
        assert ffmpeg.current_reference_crf() == 23

    def test_the_compression_level_reaches_the_exr_writer(self, restore_process: None) -> None:
        settings_form.apply_to_process(AppSettings(exr_compression_level=60))
        assert exr.current_compression_level() == 60.0

    def test_applying_the_page_puts_them_in_force_at_once(
        self, window: DrivenWindow, restore_process: None
    ) -> None:
        window.settings_answer = QDialog.DialogCode.Accepted
        window._settings.log_level = "Error"
        window.action_settings.trigger()
        assert logging.getLogger().getEffectiveLevel() == logging.ERROR
