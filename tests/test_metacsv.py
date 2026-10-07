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
        lower = read(tmp_path, ["File Name", "Shot", "Shot Type"], rows, show_pattern="[a-z]{2}").rows[0]
        assert (lower.shot, lower.qc) == ("zz0001", ())

    def test_a_lower_case_shot_under_the_default_reads_as_upper_case(self, tmp_path: Path) -> None:
        """F27: a person typed it, and `zz0001` is not a different shot from `ZZ0001`."""
        read_back = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["C1.MP4", "zz0001", "pl01"]]).rows[0]
        assert (read_back.shot, read_back.qc) == ("ZZ0001", ())

    def test_column_names_are_matched_in_any_case(self, tmp_path: Path) -> None:
        read_back = read(tmp_path, ["file name", "SHOT", "shot type"], [["C1.MP4", "ZZ0001", "pl01"]])
        assert read_back.rows[0].shot == "ZZ0001"


class TestColumnsNotRead:
    def test_scene_is_read_for_the_stringout(self, tmp_path: Path) -> None:
        """Burned in as the Primary Effect (2026-09-25)."""
        result = read(
            tmp_path,
            ["File Name", "Shot", "Shot Type", "Scene"],
            [["C1.mov", "SECA0001", "pl01", "Laser/Melt"]],
        )
        assert result.rows[0].scene == "Laser/Melt"

    def test_the_colour_columns_are_not_read(self, tmp_path: Path) -> None:
        """Colour comes from each clip's AMF since 2026-09-28 (user); these are ignored."""
        result = read(
            tmp_path,
            ["File Name", "Shot", "Shot Type", "Gamma Notes", "Color Space Notes", "Input Color Space"],
            [["C1.MP4", "MELT0001", "pl01", "S-Log3", "S-Gamut3.Cine", "Gamma 2.4"]],
        )
        assert result.rows[0].qc == ()
        assert not hasattr(result.rows[0], "written_encoding")


class TestHdri:
    """Its EXR is copied as it is and no check runs on it (user, 2026-10-07)."""

    @pytest.mark.parametrize(("written", "index"), [("HDRI", "01"), ("hdri", "01"), ("HDRI2", "02")])
    def test_an_hdri_row_is_marked_and_carries_only_info(
        self, tmp_path: Path, written: str, index: str
    ) -> None:
        result = read(
            tmp_path, ["File Name", "Shot", "Shot Type"], [["DALU0012_pl01_02_HDRI.exr", "TEST0013", written]]
        )
        (row,) = result.rows
        assert row.hdri and (row.kind, row.index) == ("HDRI", index)
        assert [(q.rule_id, q.severity) for q in row.qc] == [("QC-080", "info")]

    def test_one_with_no_shot_code_has_no_kind_to_deliver(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["x.exr", "", "HDRI"]])
        (row,) = result.rows
        assert row.hdri and row.kind is None

    def test_an_hdri_keeps_its_take(self, tmp_path: Path) -> None:
        header = ["File Name", "Shot", "Shot Type", "Take"]
        result = read(tmp_path, header, [["x.exr", "TEST0013", "HDRI", "2"]])
        assert result.rows[0].take == "2"

    def test_a_type_merely_containing_hdri_is_still_qc_010(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["x.exr", "TEST0013", "HDRIref"]])
        assert [q.rule_id for q in result.rows[0].qc] == ["QC-010"]


class TestStyleFrame:
    """A pre-graded still on the stringout, never delivered (user, 2026-10-07)."""

    @pytest.mark.parametrize("written", ["styleFrame", "styleframe", "STYLEFRAME"])
    def test_a_style_frame_row_carries_only_info(self, tmp_path: Path, written: str) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["sf.png", "SECA0009", written]])
        (row,) = result.rows
        assert (row.kind, row.index) == ("styleFrame", "01") and not row.hdri
        assert [(q.rule_id, q.severity) for q in row.qc] == [("QC-085", "info")]

    def test_one_with_no_shot_code_has_no_kind(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["sf.jpg", "", "styleFrame"]])
        (row,) = result.rows
        assert row.kind is None and [q.rule_id for q in row.qc] == ["QC-085"]


class TestFileShape:
    def test_short_rows_do_not_raise(self, tmp_path: Path) -> None:
        """Resolve pads with empty cells; nothing guarantees every row is full width."""
        result = read(tmp_path, REAL_HEADER, [["C1.MP4", "MELT0001", "pl01"]])
        assert result.rows[0].shot == "MELT0001"

    def test_the_take_is_read_as_written(self, tmp_path: Path) -> None:
        header = ["File Name", "Shot", "Shot Type", "Take"]
        result = read(tmp_path, header, [["C1.MP4", "MELT0001", "pl01", "3"]])
        assert result.rows[0].take == "3"

    def test_blank_lines_are_skipped(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [[], ["C1.MP4", "MELT0001", "pl01"], []])
        assert len(result.rows) == 1

    def test_a_row_with_no_file_name_is_skipped(self, tmp_path: Path) -> None:
        result = read(tmp_path, ["File Name", "Shot", "Shot Type"], [["", "MELT0001", "pl01"]])
        assert result.rows == [] and result.ignored == []

    def test_nothing_reads_a_duration_a_frame_count_or_a_path(self) -> None:
        """The real file's `Frames` and `Clip Directory` describe the originals, so the
        reader must not expose them at all: a caller cannot misuse what it cannot reach.
        `Start TC` is the one exception, read only when the file's own timecode puts the
        EDL's cut outside it (QC-084, user 2026-10-07)."""
        fields = set(metacsv.MetaRow.__dataclass_fields__)
        assert not fields & {"frames", "duration", "clip_directory", "end_tc", "path"}


class TestFind:
    def test_finds_csvs_directly_in_the_folder(self, tmp_path: Path) -> None:
        (tmp_path / "b.csv").touch()
        (tmp_path / "a.csv").touch()
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "c.csv").touch()
        assert [p.name for p in metacsv.find(tmp_path)] == ["a.csv", "b.csv"]
