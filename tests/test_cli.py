"""The headless `proingest scan` entry point (M1's definition of done)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.__main__ import main
from proingest.core import batchfile
from tests.fixtures import media as fixtures

FOLDER = "turnover001_02_23_2026_danielluckett"


class TestScanCommand:
    def test_clean_turnover_exits_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=2, frames=4)

        assert main(["scan", str(folder)]) == 0
        out = capsys.readouterr().out
        assert "MELT0001" in out
        assert "MELT0002" in out
        assert "2 rows, 0 errors, 0 warnings" in out

    def test_prints_the_turnover_header(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        main(["scan", str(folder)])
        assert "turnover001  02_23_2026  danielluckett" in capsys.readouterr().out

    def test_errors_exit_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A row-level error is a non-zero exit so a script can react."""
        folder = tmp_path / FOLDER
        folder.mkdir(parents=True)
        fixtures.make_otio(
            folder / "t.otio", [("MELT0001_pl01", "file:///nowhere/x.exr")], duration=4
        )
        assert main(["scan", str(folder)]) == 1
        assert "QC-012" in capsys.readouterr().out

    def test_missing_folder_exits_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["scan", str(tmp_path / "absent")]) == 2
        assert "is not a directory" in capsys.readouterr().err

    def test_save_writes_a_loadable_batch(self, tmp_path: Path) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        target = tmp_path / "melt"

        main(["scan", str(folder), "--save", str(target), "--name", "melt"])
        loaded = batchfile.load(target.with_suffix(".pibatch"))
        assert loaded.name == "melt"
        assert len(loaded.rows) == 1

    def test_scans_several_folders(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        first = tmp_path / "turnover001_02_23_2026_dan"
        second = tmp_path / "turnover002_02_24_2026_sam"
        fixtures.make_turnover(first, shots=1, frames=4)
        fixtures.make_turnover(second, shots=1, frames=4)

        assert main(["scan", str(first), str(second)]) == 0
        out = capsys.readouterr().out
        assert "turnover001" in out and "turnover002" in out
        assert "2 rows" in out


class TestTopLevel:
    def test_no_command_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([]) == 0
        assert "usage: proingest" in capsys.readouterr().out

    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["--version"])
        assert exit_info.value.code == 0
        assert "proingest" in capsys.readouterr().out
