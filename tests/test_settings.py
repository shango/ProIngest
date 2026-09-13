"""Application settings. `core/settings.py`, M5.1.

A settings file is disposable in a way a batch file is not, and these pin that
difference: nothing here raises for a bad file, and nothing here loses a key it did not
recognise.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from proingest.core import logsetup, settings
from proingest.core.render import DEFAULT_WORKERS


class TestRoundTrip:
    def test_what_was_saved_is_what_loads(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        saved = settings.AppSettings(window_geometry="Z2VvbQ==", window_state="c3RhdGU=")
        settings.save(saved, path)
        assert settings.load(path) == saved

    def test_the_folder_is_created_on_first_save(self, tmp_path: Path) -> None:
        """First run has no Application Support folder for this app yet."""
        path = tmp_path / "ProIngest" / "settings.json"
        settings.save(settings.AppSettings(), path)
        assert path.is_file()

    def test_the_write_is_atomic(self, tmp_path: Path) -> None:
        """Same rule as a deliverable: a crash mid-write leaves the previous file."""
        path = tmp_path / "settings.json"
        settings.save(settings.AppSettings(window_geometry="first"), path)
        settings.save(settings.AppSettings(window_geometry="second"), path)
        assert settings.load(path).window_geometry == "second"
        assert list(tmp_path.iterdir()) == [path]

    def test_the_two_advanced_fields_survive(self, tmp_path: Path) -> None:
        """M5.8.3. The level is stored by name, because a settings file is sometimes read."""
        path = tmp_path / "settings.json"
        saved = settings.AppSettings(log_level="Debug", ffmpeg_path="/opt/ffmpeg")
        settings.save(saved, path)
        assert settings.load(path).log_level == "Debug"
        assert settings.load(path).ffmpeg_path == "/opt/ffmpeg"
        assert json.loads(path.read_text())["log_level"] == "Debug"

    def test_a_level_the_file_names_wrongly_reads_back_as_the_default(
        self, tmp_path: Path
    ) -> None:
        """A hand edit, or a later version's level this one does not know. Not an error."""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"schema_version": 1, "log_level": "Chatty"}))
        assert settings.load(path).log_level == logsetup.name_of(logsetup.DEFAULT_LEVEL)

    def test_a_file_written_before_the_advanced_section_existed_logs_normally(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"schema_version": 1}))
        loaded = settings.load(path)
        assert loaded.log_level == logsetup.name_of(logsetup.DEFAULT_LEVEL)
        assert loaded.ffmpeg_path == ""

    def test_the_collapsed_metadata_sections_survive(self, tmp_path: Path) -> None:
        """Titles rather than indexes, so reordering the sections cannot collapse a
        different one the next time the window opens (UI_SPEC section 12.1)."""
        path = tmp_path / "settings.json"
        settings.save(settings.AppSettings(metadata_collapsed=["Range", "Turnover"]), path)
        assert settings.load(path).metadata_collapsed == ["Range", "Turnover"]

    def test_a_file_written_before_the_pane_existed_collapses_nothing(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"schema_version": settings.SCHEMA_VERSION}))
        assert settings.load(path).metadata_collapsed == []

    def test_what_the_settings_page_edits_survives(self, tmp_path: Path) -> None:
        """M5.7.2's five fields, additive, so the schema version does not move."""
        path = tmp_path / "settings.json"
        settings.save(
            settings.AppSettings(
                workers=9,
                show_pattern="ABC",
                path_map={"G:/media": "/Volumes/drive"},
                rules={"min_duration_frames": 11},
                color_session_folder="/Volumes/drive/colour",
            ),
            path,
        )
        loaded = settings.load(path)
        assert loaded.workers == 9
        assert loaded.show_pattern == "ABC"
        assert loaded.path_map == {"G:/media": "/Volumes/drive"}
        assert loaded.rules == {"min_duration_frames": 11}
        assert loaded.color_session_folder == "/Volumes/drive/colour"

    def test_a_file_written_before_the_settings_page_existed_reads_back_bare(
        self, tmp_path: Path
    ) -> None:
        """`workers` has to read back as what the tool would have done anyway."""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"schema_version": settings.SCHEMA_VERSION}))
        loaded = settings.load(path)
        assert loaded.workers == DEFAULT_WORKERS
        assert loaded.show_pattern == ""
        assert loaded.path_map == {} and loaded.rules == {}

    def test_the_schema_version_is_written(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        settings.save(settings.AppSettings(), path)
        assert json.loads(path.read_text())["schema_version"] == settings.SCHEMA_VERSION


class TestAFileThatCannotBeUsed:
    """None of these raise. Refusing to launch over a preferences file is the worse bug."""

    def test_no_file_at_all_is_the_first_run(self, tmp_path: Path) -> None:
        assert settings.load(tmp_path / "nothing.json") == settings.AppSettings()

    def test_a_corrupt_file_falls_back_and_says_so(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "settings.json"
        path.write_text("{ this is not json")
        with caplog.at_level(logging.WARNING):
            assert settings.load(path) == settings.AppSettings()
        assert "could not be read" in caplog.text

    def test_json_that_is_not_an_object_falls_back(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("[1, 2, 3]")
        assert settings.load(path) == settings.AppSettings()

    @pytest.mark.parametrize(
        "content",
        ['{"workers": "lots"}', '{"workers": null}', '{"path_map": [1, 2]}', '{"metadata_collapsed": 5}'],
    )
    def test_a_value_of_the_wrong_type_falls_back(self, tmp_path: Path, content: str) -> None:
        path = tmp_path / "settings.json"
        path.write_text(content)
        assert settings.load(path) == settings.AppSettings()

    def test_a_missing_key_takes_its_default(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"schema_version": 1}))
        assert settings.load(path).window_geometry == ""


class TestADowngrade:
    def test_a_key_this_version_does_not_know_survives_a_save(self, tmp_path: Path) -> None:
        """An older build opening a newer build's file must not delete what it cannot read."""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"schema_version": 99, "delivery_root": "/deliveries"}))
        loaded = settings.load(path)
        settings.save(loaded, path)
        assert json.loads(path.read_text())["delivery_root"] == "/deliveries"

    def test_the_unknown_keys_do_not_overwrite_the_known_ones(self, tmp_path: Path) -> None:
        """A key this version owns is written from the field, whatever the file said."""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"window_geometry": "old", "spare": 1}))
        loaded = settings.load(path)
        loaded.window_geometry = "new"
        settings.save(loaded, path)
        written = json.loads(path.read_text())
        assert (written["window_geometry"], written["spare"]) == ("new", 1)


class TestTheLastFolder:
    """Where the file choosers open when the batch cannot say (UI_SPEC section 11)."""

    def test_it_survives_a_save_and_a_load(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        settings.save(settings.AppSettings(last_folder="/Volumes/drive/turnovers"), path)
        assert settings.load(path).last_folder == "/Volumes/drive/turnovers"

    def test_a_first_run_has_none_and_guesses_none(self) -> None:
        """A wrong guess opens somewhere plausible and empty, which reads as the folder
        being wrong rather than as nothing having been chosen yet."""
        assert settings.AppSettings().last_folder == ""
