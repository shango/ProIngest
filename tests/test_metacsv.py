"""Ben's metadata CSV, the carrier of identity and encoding (FR-1).

The real file lives in `Turnover199/` and is git-ignored, so everything here is
synthetic and modelled on it: docs/SAMPLE_TURNOVER_199.md section 7 records what the
real one contains, including the 44 columns and the `Shot Type` collision at positions
12 and 44.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import metacsv
from proingest.core.metacsv import MetaCsvError

REAL_HEADER = ["File Name", "Shot", "Shot Type", "Gamma Notes", "Color Space Notes", "Shot Code", "Shot Type"]
"""The real file's shape in miniature: `Shot Type` twice, the built-in then the custom."""


def write_csv(path: Path, header: list[str], rows: list[list[str]], encoding: str = "utf-16") -> Path:
    lines = [",".join(f'"{cell}"' for cell in row) for row in [header, *rows]]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode(encoding))
    return path


def read(tmp_path: Path, header: list[str], rows: list[list[str]], **kwargs: str) -> metacsv.MetaCsv:
    return metacsv.read(write_csv(tmp_path / "meta.csv", header, rows), **kwargs)


class TestDecoding:
    @pytest.mark.parametrize("encoding", ["utf-16", "utf-8-sig", "utf-8"])
    def test_reads_utf16_and_utf8(self, tmp_path: Path, encoding: str) -> None:
        path = write_csv(
            tmp_path / "m.csv", ["File Name", "Shot", "Shot Type"], [["C1.MP4", "MELT0001", "pl01"]], encoding
        )
        assert metacsv.read(path).rows[0].file_name == "C1.MP4"

    def test_empty_file_is_not_a_csv(self, tmp_path: Path) -> None:
        path = tmp_path / "m.csv"
        path.write_bytes(b"")
        with pytest.raises(MetaCsvError, match="empty"):
            metacsv.read(path)

    def test_no_file_name_column_is_not_a_csv(self, tmp_path: Path) -> None:
        with pytest.raises(MetaCsvError, match="File Name"):
            read(tmp_path, ["Shot", "Shot Type"], [["MELT0001", "pl01"]])

    def test_missing_file_is_not_a_csv(self, tmp_path: Path) -> None:
        with pytest.raises(MetaCsvError):
            metacsv.read(tmp_path / "absent.csv")


class TestShotType:
    def test_both_columns_agree(self, tmp_path: Path) -> None:
        result = read(
            tmp_path,
            REAL_HEADER,
            [["C1.MP4", "MELT0001", "pl01", "S-Log3", "S-Gamut3.Cine", "MELT0001", "pl01"]],
        )
        row = result.rows[0]
        assert (row.kind, row.index) == ("pl", "01")
        assert row.qc == ()

    def test_builtin_framing_value_loses_to_the_custom_field(self, tmp_path: Path) -> None:
        """The case the real sample got away with: `Wide` in Resolve's own field."""
        result = read(
            tmp_path,
            REAL_HEADER,
            [["C1.MP4", "MELT0001", "Wide", "S-Log3", "S-Gamut3.Cine", "MELT0001", "cp01"]],
        )
        row = result.rows[0]
        assert (row.kind, row.index) == ("cp", "01")
        assert row.qc == (), "one resolving and one not is the normal shape, not a disagreement"

    def test_two_that_both_resolve_and_differ_is_qc_065(self, tmp_path: Path) -> None:
        result = read(
            tmp_path,
            REAL_HEADER,
            [["C1.MP4", "MELT0001", "pl01", "S-Log3", "S-Gamut3.Cine", "MELT0001", "cp02"]],
        )
        row = result.rows[0]
        assert (row.kind, row.index) == ("cp", "02"), "the custom field wins"
        assert [q.rule_id for q in row.qc] == ["QC-065"]
        assert "'pl01'" in row.qc[0].message and "'cp02'" in row.qc[0].message

    def test_no_shot_type_column_at_all_ignores_every_row(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot"], [["C1.MP4", "MELT0001"], ["C2.MP4", "MELT0001"]])
        assert result.rows == []
        assert result.ignored == ["C1.MP4", "C2.MP4"]

    def test_blank_shot_type_is_ignored_not_an_error(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["C1.MP4", "MELT0001", ""]])
        assert result.rows == []
        assert result.ignored == ["C1.MP4"]

    def test_unknown_shot_type_is_a_row_carrying_qc_010(self, tmp_path: Path) -> None:
        """Neither column resolving is QC-010, not an ignored clip: somebody typed something."""
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["C1.MP4", "MELT0001", "Banana"]])
        row = result.rows[0]
        assert row.kind is None
        assert row.shot_type == "Banana"
        assert [q.rule_id for q in row.qc] == ["QC-010"]

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("pl", ("pl", "01")),
            ("colorChart", ("colorChart", "01")),
            ("COLORCHART", ("colorChart", "01")),
            ("cl", ("cp", "01")),
            ("cl02", ("cp", "02")),
        ],
    )
    def test_reading_rules(self, tmp_path: Path, written: str, expected: tuple[str, str]) -> None:
        """A bare code means 01, casing is ignored, `cl` is written `cp` (OQ-72)."""
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["C1.MP4", "MELT0001", written]])
        assert (result.rows[0].kind, result.rows[0].index) == expected


class TestShot:
    def test_blank_shot_is_qc_010(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["C1.MP4", "", "pl01"]])
        assert [q.rule_id for q in result.rows[0].qc] == ["QC-010"]
        assert "no Shot" in result.rows[0].qc[0].message

    def test_shot_that_is_not_a_shot_code_is_qc_010(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["C1.MP4", "not a code", "pl01"]])
        assert [q.rule_id for q in result.rows[0].qc] == ["QC-010"]

    def test_show_pattern_is_honoured(self, tmp_path: Path) -> None:
        rows = [["C1.MP4", "zz0001", "pl01"]]
        assert read(tmp_path, ["File Name", "Shot", "Shot Type"], rows).rows[0].qc, (
            "default pattern is uppercase"
        )
        assert (
            read(tmp_path, ["File Name", "Shot", "Shot Type"], rows, show_pattern="[a-z]{2}").rows[0].qc == ()
        )


class TestEncoding:
    def test_two_fields_join_in_order(self, tmp_path: Path) -> None:
        result = read(
            tmp_path, REAL_HEADER, [["C1.MP4", "MELT0001", "pl01", "S-Log3", "S-Gamut3.Cine", "", "pl01"]]
        )
        assert result.rows[0].written_encoding == "S-Log3 S-Gamut3.Cine"

    def test_one_field_alone_carries_what_there_is(self, tmp_path: Path) -> None:
        result = read(
            tmp_path,
            ["File Name", "Shot", "Shot Type", "Gamma Notes"],
            [["C1.MP4", "MELT0001", "pl01", "S-Log3"]],
        )
        assert result.rows[0].written_encoding == "S-Log3"

    def test_absent_columns_are_empty_rather_than_malformed(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["C1.MP4", "MELT0001", "pl01"]])
        assert result.rows[0].written_encoding == ""
        assert result.rows[0].qc == ()


class TestFileShape:
    def test_short_rows_do_not_raise(self, tmp_path: Path) -> None:
        """Resolve pads with empty cells; nothing guarantees every row is full width."""
        result = read(tmp_path, REAL_HEADER, [["C1.MP4", "MELT0001", "pl01"]])
        assert result.rows[0].written_encoding == ""

    def test_blank_lines_are_skipped(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [[], ["C1.MP4", "MELT0001", "pl01"], []])
        assert len(result.rows) == 1

    def test_a_row_with_no_file_name_is_skipped(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["", "MELT0001", "pl01"]])
        assert result.rows == [] and result.ignored == []

    def test_nothing_reads_a_duration_a_frame_count_or_a_path(self) -> None:
        """The real file's `Frames` and `Clip Directory` describe the originals, so the
        reader must not expose them at all: a caller cannot misuse what it cannot reach."""
        fields = set(metacsv.MetaRow.__dataclass_fields__)
        assert not fields & {"frames", "duration", "clip_directory", "start_tc", "end_tc", "path"}


class TestFind:
    def test_finds_csvs_directly_in_the_folder(self, tmp_path: Path) -> None:
        (tmp_path / "b.csv").touch()
        (tmp_path / "a.csv").touch()
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "c.csv").touch()
        assert [p.name for p in metacsv.find(tmp_path)] == ["a.csv", "b.csv"]
