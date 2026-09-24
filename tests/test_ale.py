"""The ALE beside Ben's EDL, read for its row order: which clip each event is."""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import ale

HEADER = "Heading\nFIELD_DELIM\tTABS\nFPS\t24\n\nColumn\nName\tTracks\tStart\tEnd\t\n\nData\n"


def write(path: Path, rows: list[str], encoding: str = "utf-8") -> Path:
    body = HEADER + "".join(f"{name}\tVA1\t00:00:00:00\t00:00:01:00\t\n" for name in rows)
    path.write_text(body, encoding=encoding)
    return path


class TestReadNames:
    def test_names_come_back_in_row_order(self, tmp_path: Path) -> None:
        """Turnover121's shape: a clip used three times is three rows."""
        rows = ["Laser Eyes Effect .mov", "MacBeth Chart.mov", "MacBeth Chart.mov"]
        assert ale.read_names(write(tmp_path / "t.ale", rows)) == rows

    def test_utf_16_is_read_too(self, tmp_path: Path) -> None:
        assert ale.read_names(write(tmp_path / "t.ale", ["A.mov"], "utf-16")) == ["A.mov"]

    def test_no_name_column_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "t.ale"
        path.write_text("Heading\nFPS\t24\n\nColumn\nTracks\tStart\n\nData\nVA1\t00:00:00:00\n")
        with pytest.raises(ale.AleError, match="Name"):
            ale.read_names(path)

    def test_a_row_with_no_name_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "t.ale"
        path.write_text(HEADER + "\tVA1\t00:00:00:00\t00:00:01:00\n")
        with pytest.raises(ale.AleError, match="no Name"):
            ale.read_names(path)

    def test_found_by_suffix_in_any_case(self, tmp_path: Path) -> None:
        write(tmp_path / "T121.ALE", ["A.mov"])
        (tmp_path / "notes.txt").write_text("")
        assert [p.name for p in ale.find(tmp_path)] == ["T121.ALE"]
