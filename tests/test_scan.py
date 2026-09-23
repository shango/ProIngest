"""Scanning a turnover folder into shot rows, and the QC the scan uncovers."""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import scan
from proingest.core.models import Batch, ShotRow, Turnover
from tests.fixtures import media as fixtures

GOOD_FOLDER = "turnover001_02_23_2026_danielluckett"


def rules(row: ShotRow) -> set[str]:
    return {result.rule_id for result in row.qc}


def turnover_rules(batch: Batch) -> set[str]:
    return {result.rule_id for turnover in batch.turnovers for result in turnover.qc}


class TestParseTurnoverFolder:
    def test_parses_the_documented_pattern(self) -> None:
        fields = scan.parse_turnover_folder(Path(f"/x/{GOOD_FOLDER}"))
        assert fields is not None
        assert (fields.number, fields.month, fields.day, fields.year) == (1, 2, 23, 2026)
        assert fields.shooter == "danielluckett"

    @pytest.mark.parametrize(
        "name", ["messy", "turnover1_02_23_2026_dan", "turnover001_2_23_2026_dan", "turnover001"]
    )
    def test_rejects_other_names(self, name: str) -> None:
        assert scan.parse_turnover_folder(Path(f"/x/{name}")) is None


class TestTheHandoverFolder:
    """One folder holding the media, Ben's EDL and his metadata CSV (OQ-74)."""

    def test_both_files_are_recorded_on_the_turnover(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        turnover, _ = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        assert turnover.edl_path is not None and turnover.edl_path.name == "FINAL_v01.edl"
        assert turnover.csv_path is not None and turnover.csv_path.name == "metadata.csv"
        assert turnover.color_session_edl == turnover.edl_path, "read once, at the scan"

    def test_no_edl_is_qc_001_and_says_which_file(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        (folder / "FINAL_v01.edl").unlink()
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert {r.rule_id for r in turnover.qc} == {"QC-001"}
        assert "EDL" in turnover.qc[0].message
        assert rows == []

    def test_no_csv_is_qc_001_and_says_which_file(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        (folder / "metadata.csv").unlink()
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert {r.rule_id for r in turnover.qc} == {"QC-001"}
        assert "CSV" in turnover.qc[0].message
        assert rows == []

    @pytest.mark.parametrize("extra", ["SECOND_v02.edl", "second.csv"])
    def test_two_of_either_is_refused_rather_than_chosen_between(self, tmp_path: Path, extra: str) -> None:
        """Choosing between two cuts is choosing a cut, and the same goes for two CSVs."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        (folder / extra).write_bytes((folder / "FINAL_v01.edl").read_bytes())
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert {r.rule_id for r in turnover.qc} == {"QC-001"}
        assert rows == []

    def test_neither_file_is_looked_for_in_a_subfolder(self, tmp_path: Path) -> None:
        """The handover is one folder; a recursive search would find a working copy."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        nested = folder / "exports"
        nested.mkdir()
        (folder / "FINAL_v01.edl").rename(nested / "FINAL_v01.edl")
        turnover, _ = scan.scan_turnover(folder, "t1")
        assert {r.rule_id for r in turnover.qc} == {"QC-001"}


class TestScanTurnover:
    def test_happy_path(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=2, frames=6)
        settings = scan.ScanSettings(rules=fixtures.SMALL_RULES)
        turnover, rows = scan.scan_turnover(folder, "t1", settings)

        assert turnover.number == 1
        assert turnover.shooter == "danielluckett"
        assert turnover.qc == []
        assert len(rows) == 2
        assert all(row.qc == [] for row in rows)

    def test_one_row_per_csv_row_rather_than_per_timeline_clip(self, tmp_path: Path) -> None:
        """`Shot Type` is the whole of the tool's scope, so the CSV decides what exists."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=3, frames=4)
        _, rows = scan.scan_turnover(folder, "t1")
        assert [row.clip_name for row in rows] == ["MELT0001_pl01", "MELT0002_pl01", "MELT0003_pl01"]

    def test_identity_comes_off_the_two_csv_fields(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6, shot_types=["colorChart"])
        _, rows = scan.scan_turnover(folder, "t1")
        identity = rows[0].identity
        assert identity is not None
        assert (identity.shot_code, identity.kind, identity.index) == ("MELT0001", "colorChart", "01")

    def test_rows_carry_media_the_encoding_and_the_cut(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        _, rows = scan.scan_turnover(folder, "t1")
        row = rows[0]

        assert row.shot_code == "MELT0001"
        assert row.identity is not None and row.identity.elem == "pl01"
        assert row.media is not None and row.media.is_sequence
        assert row.source_encoding == fixtures.SOURCE_ENCODING
        assert row.source_encoding_origin == "clip metadata"
        assert row.cdl is not None, "the CDL on the event is the grade"
        assert row.approved is not None
        assert row.current == row.snapshot == row.approved, "a fresh scan has not been edited"
        assert row.audio_path is not None

    def test_the_encoding_is_the_two_fields_joined_in_order(self, tmp_path: Path) -> None:
        """`Gamma Notes` then `Color Space Notes`, verbatim: QC-047 quotes it back."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6, source_encoding="S-Log3 S-Gamut3.Cine")
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].source_encoding == "S-Log3 S-Gamut3.Cine"

    def test_a_clip_naming_no_encoding_says_so_rather_than_guessing(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6, source_encoding=None)
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].source_encoding is None
        assert "QC-046" in rules(rows[0])

    def test_a_clip_with_no_shot_type_is_ignored_and_counted(self, tmp_path: Path) -> None:
        """QC-064 at turnover scope: ignoring is intended, a whole turnover ignored is not."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=2, frames=4, shot_types=["pl01", ""])
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert [row.clip_name for row in rows] == ["MELT0001_pl01"]
        found = [r for r in turnover.qc if r.rule_id == "QC-064"]
        assert len(found) == 1
        assert "MELT0002_pl01" in found[0].message
        assert found[0].severity == "warning"

    def test_a_turnover_nobody_filled_in_delivers_nothing_and_says_so(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=2, frames=4, shot_types=["", ""])
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert rows == []
        assert {r.rule_id for r in turnover.qc} == {"QC-064", "QC-004"}

    def test_a_row_the_edl_says_nothing_about_is_an_error_not_a_guess(self, tmp_path: Path) -> None:
        """A neighbour's cut and a neighbour's grade both look entirely plausible."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=2, frames=4)
        fixtures.make_final_edl(folder / "FINAL_v01.edl", ["MELT0001_pl01"], duration=4)
        _, rows = scan.scan_turnover(folder, "t1")
        orphan = next(row for row in rows if row.clip_name == "MELT0002_pl01")
        assert "QC-066" in rules(orphan)
        assert orphan.cdl is None and orphan.approved is None
        assert orphan.current is not None, "it still shows what arrived, so it can be trimmed by hand"

    def test_media_the_csv_names_but_the_folder_lacks_is_qc_012(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        fixtures.make_meta_csv(folder / "metadata.csv", [("GONE_pl01", "MELT0001", "pl01")])
        _, rows = scan.scan_turnover(folder, "t1")
        assert "QC-012" in rules(rows[0])
        assert rows[0].media is None

    def test_an_unreadable_csv_is_qc_002(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        (folder / "metadata.csv").write_bytes(b"")
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert "QC-002" in {r.rule_id for r in turnover.qc}
        assert rows == []

    def test_an_unreadable_edl_is_qc_002(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        (folder / "FINAL_v01.edl").write_text("not an edl\n")
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert "QC-002" in {r.rule_id for r in turnover.qc}
        assert rows == []

    def test_nothing_reads_a_duration_or_a_path_out_of_the_csv(self, tmp_path: Path) -> None:
        """The real file's Frames and Clip Directory describe the pre-consolidation
        originals, so the media facts come off ffprobe and the cut off the EDL."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].media is not None and rows[0].media.frame_count == 6


class TestTurnoverLevelProblems:
    def test_unmatched_folder_name_is_qc_005(self, tmp_path: Path) -> None:
        folder = tmp_path / "messy"
        fixtures.make_turnover(folder, shots=1, frames=4)
        turnover, _ = scan.scan_turnover(folder, "t1")
        assert "QC-005" in {r.rule_id for r in turnover.qc}

    def test_a_bad_turnover_does_not_raise(self, tmp_path: Path) -> None:
        """One bad folder must not take down a batch."""
        folder = tmp_path / "empty"
        folder.mkdir()
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert rows == []
        assert turnover.qc


class TestScanBatch:
    def test_scans_several_turnovers(self, tmp_path: Path) -> None:
        first = tmp_path / "turnover001_02_23_2026_dan"
        second = tmp_path / "turnover002_02_24_2026_sam"
        fixtures.make_turnover(first, shots=2, frames=4)
        fixtures.make_turnover(second, shots=1, frames=4)

        batch = scan.scan_batch([first, second], name="melt")
        assert len(batch.turnovers) == 2
        assert len(batch.rows) == 3
        assert len(batch.rows_for("t1")) == 2
        assert len(batch.rows_for("t2")) == 1

    def test_probe_cache_is_shared_across_turnovers(self, tmp_path: Path) -> None:
        """FR-3 probes each media item once; the cache is per batch, not per turnover."""
        folder = tmp_path / "turnover001_02_23_2026_dan"
        fixtures.make_turnover(folder, shots=2, frames=4)
        batch = scan.scan_batch([folder])
        assert len(batch.probe_cache) == 2

    def test_a_broken_turnover_does_not_stop_the_others(self, tmp_path: Path) -> None:
        good = tmp_path / "turnover001_02_23_2026_dan"
        broken = tmp_path / "turnover002_02_24_2026_sam"
        fixtures.make_turnover(good, shots=1, frames=4)
        broken.mkdir(parents=True)

        batch = scan.scan_batch([good, broken])
        assert len(batch.rows) == 1
        assert "QC-001" in turnover_rules(batch)


class TestNextTurnoverId:
    """One authority for the numbering, whether the CLI or the window is adding it."""

    def test_an_empty_batch_starts_at_one(self) -> None:
        assert scan.next_turnover_id(Batch()) == "t1"

    def test_it_counts_past_the_highest_rather_than_filling_a_gap(self) -> None:
        """A row points at its turnover by id, so a gap is not an id to hand out again."""
        batch = Batch(turnovers=[Turnover("t1", Path("/a")), Turnover("t5", Path("/b"))])
        assert scan.next_turnover_id(batch) == "t6"

    def test_an_id_that_is_not_t_and_a_number_is_left_out_of_the_count(self) -> None:
        batch = Batch(turnovers=[Turnover("hand_edited", Path("/a")), Turnover("t2", Path("/b"))])
        assert scan.next_turnover_id(batch) == "t3"

    def test_scan_batch_numbers_them_the_same_way(self, tmp_path: Path) -> None:
        first = tmp_path / "turnover001_02_23_2026_dan"
        second = tmp_path / "turnover002_02_24_2026_sam"
        fixtures.make_turnover(first, shots=1, frames=4)
        fixtures.make_turnover(second, shots=1, frames=4)

        batch = scan.scan_batch([first, second])
        assert [turnover.turnover_id for turnover in batch.turnovers] == ["t1", "t2"]
