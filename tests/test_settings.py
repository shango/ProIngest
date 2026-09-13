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

from proingest.core import settings


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
