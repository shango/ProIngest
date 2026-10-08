"""Scanning a turnover folder into shot rows, and the QC the scan uncovers."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from proingest.core import planner, qc, scan
from proingest.core.models import Batch, Deliverable, InOut, ShotRow, Turnover
from tests.fixtures import color as color_fixtures
from tests.fixtures import media as fixtures
from tests.test_amf import CDL_LOOK

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

    def test_a_two_digit_year_is_read_as_this_century(self) -> None:
        """Turnover097's folder: `09_28_26`, the form a turnover is dated in (user, 2026-10-05)."""
        fields = scan.parse_turnover_folder(Path("/x/turnover097_09_28_26_danielluckett"))
        assert fields is not None
        assert (fields.number, fields.month, fields.day, fields.year) == (97, 9, 28, 2026)

    @pytest.mark.parametrize(
        "name",
        [
            "messy",
            "turnover001_02_23_202_dan",
            "turnover1_02_23_2026_dan",
            "turnover001_2_23_2026_dan",
            "turnover001",
        ],
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
        assert row.source_encoding_origin == "AMF"
        assert row.grade is not None and row.grade.graded, "the AMF's CLF is the grade"
        assert (row.grade.display, row.grade.view) == (color_fixtures.DISPLAY, color_fixtures.VIEW)
        assert row.approved is not None
        assert row.current == row.snapshot == row.approved, "a fresh scan has not been edited"
        assert row.audio_path is not None

    @pytest.mark.parametrize("kind", ["cp01", "el01"])
    def test_only_a_plate_takes_the_audio_beside_it(self, tmp_path: Path, kind: str) -> None:
        """Only a pl has an associated audio clip (user, 2026-09-23), so a wav named for
        another clip type is not looked for, and raises nothing."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6, shot_types=[kind])
        _, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        row = rows[0]
        assert row.audio_path is None and row.audio is None
        assert row.audio_clip_count == 0
        assert not rules(row) & {"QC-040", "QC-041", "QC-042", "QC-043", "QC-044"}

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
        assert orphan.grade is None and orphan.approved is None
        assert orphan.current is not None, "it still shows what arrived, so it can be trimmed by hand"

    def test_an_unnamed_event_inside_two_files_is_refused_on_both(self, tmp_path: Path) -> None:
        """Both fixture sequences start at 01:00:00:00, so a nameless event fits either."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=2, frames=4)
        fixtures.make_final_edl(folder / "FINAL_v01.edl", [""], duration=4)
        _, rows = scan.scan_turnover(folder, "t1")
        for row in rows:
            assert "QC-067" in rules(row)
            assert row.grade is None and row.approved is None

    def test_an_event_no_row_claims_is_recorded_at_turnover_scope(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        fixtures.make_final_edl(folder / "FINAL_v01.edl", ["MELT0001_pl01", "SOMETHING_ELSE"], duration=4)
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert "QC-068" in {result.rule_id for result in turnover.qc}
        assert "QC-066" not in rules(rows[0]) and rows[0].approved is not None

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

    def test_a_two_digit_year_raises_nothing(self, tmp_path: Path) -> None:
        """It was QC-081 from 2026-09-29; two digits is the expected form since 2026-10-05 (user)."""
        folder = tmp_path / "turnover097_09_28_26_danielluckett"
        fixtures.make_turnover(folder, shots=1, frames=4)
        turnover, _ = scan.scan_turnover(folder, "t1")
        assert turnover.qc == []
        assert (turnover.number, turnover.year, turnover.shooter) == (97, 2026, "danielluckett")

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


class TestIsTurnoverFolder:
    """What a drop onto the window keeps: a folder with an EDL and a CSV directly in it."""

    def test_an_edl_and_a_csv_make_a_turnover(self, tmp_path: Path) -> None:
        (tmp_path / "Turnover121.EDL").write_text("")
        (tmp_path / "Turnover121.csv").write_text("")
        assert scan.is_turnover_folder(tmp_path)

    @pytest.mark.parametrize("names", [(), ("cut.edl",), ("meta.csv",), ("sub/cut.edl", "sub/meta.csv")])
    def test_anything_less_is_not(self, tmp_path: Path, names: tuple[str, ...]) -> None:
        for name in names:
            (tmp_path / name).parent.mkdir(exist_ok=True)
            (tmp_path / name).write_text("")
        assert not scan.is_turnover_folder(tmp_path)

    def test_a_file_or_a_missing_path_is_not(self, tmp_path: Path) -> None:
        clip = tmp_path / "clip.mov"
        clip.write_text("")
        assert not scan.is_turnover_folder(clip)
        assert not scan.is_turnover_folder(tmp_path / "gone")


class TestNextTurnoverId:
    """One authority for the numbering, whether the CLI or the window is adding it."""

    def test_an_empty_batch_starts_at_one(self) -> None:
        assert scan.next_turnover_id(Batch()) == "t1"

    def test_it_counts_past_the_highest_rather_than_filling_a_gap(self) -> None:
        """A row points at its turnover by id, so a gap is not an id to hand out again."""
        batch = Batch(turnovers=[Turnover("t1", Path("/a")), Turnover("t5", Path("/b"))])
        assert scan.next_turnover_id(batch) == "t6"

    def test_several_at_once_follow_on_from_the_highest(self) -> None:
        batch = Batch(turnovers=[Turnover("t2", Path("/a"))])
        assert scan.next_turnover_ids(batch, 3) == ["t3", "t4", "t5"]

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


class TestCarryOver:
    """D8 and D16: a turnover scanned again keeps what the editor did, by File Name."""

    def rows(self, *names: str) -> list[ShotRow]:
        return [
            ShotRow(turnover_id="t1", clip_name=name, snapshot=InOut(10, 20), current=InOut(10, 20))
            for name in names
        ]

    def test_the_editor_s_work_follows_the_file_name(self) -> None:
        old, new = self.rows("C0145.MP4"), self.rows("C0145.MP4")
        old[0].current = InOut(12, 18)
        old[0].skipped, old[0].skip_reason, old[0].notes = True, "not needed", "sky"
        old[0].shot_code_override = "TEST0009"
        scan.carry_over(Turnover("t1", Path("/a")), old, Turnover("t1", Path("/b")), new)
        assert new[0].current == InOut(12, 18)
        assert (new[0].skipped, new[0].skip_reason, new[0].notes) == (True, "not needed", "sky")
        assert new[0].shot_code == "TEST0009"

    def test_a_re_run_asked_for_survives_the_rescan_it_starts(self) -> None:
        old, new = self.rows("C0145.MP4"), self.rows("C0145.MP4")
        old[0].rerun = True
        old[0].delivered_range = InOut(10, 20)
        scan.carry_over(Turnover("t1", Path("/a")), old, Turnover("t1", Path("/b")), new)
        assert new[0].rerun
        assert new[0].delivered_range == InOut(10, 20)

    def test_the_stringout_stays_with_the_turnover(self) -> None:
        was, now = Turnover("t1", Path("/a")), Turnover("t1", Path("/a"))
        was.stringout = Deliverable(kind="stringout", name="so.mp4", path=Path("/d/so.mp4"), version=1)
        scan.carry_over(was, [], now, [])
        assert now.stringout == was.stringout

    def test_a_trim_never_made_follows_the_new_edl(self) -> None:
        old, new = self.rows("C0145.MP4"), self.rows("C0145.MP4")
        new[0].snapshot = new[0].current = InOut(14, 24)
        scan.carry_over(Turnover("t1", Path("/a")), old, Turnover("t1", Path("/b")), new)
        assert new[0].current == InOut(14, 24)

    def test_a_clip_used_twice_pairs_in_order(self) -> None:
        """D3: each instance is its own row, so the first keeps the first's edits."""
        old, new = self.rows("C0145.MP4", "C0145.MP4"), self.rows("C0145.MP4", "C0145.MP4")
        old[0].notes, old[1].notes = "first", "second"
        scan.carry_over(Turnover("t1", Path("/a")), old, Turnover("t1", Path("/b")), new)
        assert [row.notes for row in new] == ["first", "second"]

    def test_a_changed_edl_is_a_warning_on_the_turnover(self) -> None:
        was = Turnover("t1", Path("/a"), edl_digest="1", csv_digest="2")
        now = Turnover("t1", Path("/b"), edl_digest="3", csv_digest="2")
        scan.carry_over(was, self.rows("C0145.MP4"), now, self.rows("C0145.MP4"))
        assert [(r.rule_id, r.severity) for r in now.qc] == [("QC-070", "warning")]
        assert "EDL" in now.qc[0].message and "CSV" not in now.qc[0].message

    def test_nothing_changed_says_nothing(self) -> None:
        was = Turnover("t1", Path("/a"), edl_digest="1", csv_digest="2")
        now = Turnover("t1", Path("/b"), edl_digest="1", csv_digest="2")
        scan.carry_over(was, [], now, [])
        assert now.qc == []

    def test_a_scan_records_both_digests(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        turnover, _ = scan.scan_turnover(folder, "t1")
        assert turnover.edl_digest and turnover.csv_digest


class TestCaseOfTheHandover:
    def test_an_upper_case_edl_suffix_is_ben_s_edl(self, tmp_path: Path) -> None:
        """F27: `.EDL` is as much an EDL as `.edl`."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        (folder / "FINAL_v01.edl").rename(folder / "FINAL_v01.EDL")
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert "QC-001" not in turnover_rules_of(turnover)
        assert len(rows) == 1


def turnover_rules_of(turnover: Turnover) -> set[str]:
    return {result.rule_id for result in turnover.qc}


def _event(number: int, source_in: int, source_out: int, record: int, freeze: bool = False) -> str:
    tc = fixtures.timecode
    lines = [
        f"{number:03d}  AX       V     C        {tc(source_in)} {tc(source_out)} "
        f"{tc(record)} {tc(record + source_out - source_in)}  "
    ]
    if freeze:
        lines.append(f"M2   AX             000.0                {tc(source_in)}")
    lines += ["*ASC_SOP (1.0 1.0 1.0)(0.0 0.0 0.0)(1.0 1.0 1.0)", "*ASC_SAT 1.0", ""]
    return "\n".join(lines)


def overlapping_turnover(folder: Path, ale_names: list[str] | None) -> Path:
    """Turnover121's shape: three clips whose timecodes all start at 01:00:00:00, an EDL
    that names nothing, a chart cut three times at two frames, and a clean plate held
    twice on one frame for two different lengths."""
    for base in ("A", "B", "C"):
        fixtures.make_exr_sequence(folder / "media", base=base, count=10)
    fixtures.make_meta_csv(
        folder / "metadata.csv",
        [
            ("A", "MELT0001", "pl01"),
            ("B", "MELT0001", "colorChart"),
            ("B", "MELT0001", "colorChart"),
            ("C", "MELT0001", "cp01"),
            ("C", "MELT0001", "cp01"),
        ],
    )
    start = 86400
    events = [
        _event(1, start + 2, start + 7, 90000),
        _event(2, start + 1, start + 2, 90005),
        _event(3, start + 3, start + 51, 90006, freeze=True),
        _event(4, start + 4, start + 5, 90054),
        _event(5, start + 3, start + 75, 90055, freeze=True),
        _event(6, start + 1, start + 2, 90127),
    ]
    (folder / "FINAL.edl").write_text("TITLE: T\nFCM: NON-DROP FRAME\n\n" + "\n".join(events))
    for number, clip in enumerate(ALE_ORDER, 1):
        color_fixtures.make_amf(folder, number, clip)
    if ale_names is not None:
        header = "Heading\nFPS\t24\n\nColumn\nName\tTracks\t\n\nData\n"
        (folder / "T.ale").write_text(header + "".join(f"{name}\tV\t\n" for name in ale_names))
    return folder


ALE_ORDER = ["A", "B", "C", "B", "C", "B"]


class TestTheAleNamesTheEvents:
    """When the EDL names no clips and timecodes overlap, the ALE's row order names them."""

    def scan(self, tmp_path: Path, ale_names: list[str] | None) -> tuple[Turnover, dict[str, ShotRow]]:
        folder = overlapping_turnover(tmp_path / GOOD_FOLDER, ale_names)
        turnover, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        return turnover, {row.clip_name: row for row in rows}

    def test_every_row_conforms_with_no_error(self, tmp_path: Path) -> None:
        turnover, rows = self.scan(tmp_path, ALE_ORDER)
        assert turnover.ale_path is not None and turnover.ale_path.name == "T.ale"
        assert sorted(rows) == ["A", "B", "C"], "one row per thing delivered"
        assert not [r for row in rows.values() for r in row.qc if r.severity == "error"]
        assert rows["A"].current == InOut(1003, 1007)

    def test_a_still_is_delivered_once_per_shot_code_from_its_first_use(self, tmp_path: Path) -> None:
        _, rows = self.scan(tmp_path, ALE_ORDER)
        chart = rows["B"]
        assert chart.current == InOut(1002, 1002), "event 002, the first use, not 004's frame"
        assert "QC-072" in rules(chart)
        assert "QC-055" not in rules(chart), "one frame cut out of a longer file is the normal case"

    def test_a_freeze_is_one_frame_and_two_holds_of_it_are_one_row(self, tmp_path: Path) -> None:
        _, rows = self.scan(tmp_path, ALE_ORDER)
        plate = rows["C"]
        assert plate.freeze
        assert plate.current == InOut(1004, 1004)
        assert "QC-072" in rules(plate)
        assert not rules(plate) & {"QC-029", "QC-030", "QC-033"}, "a hold runs past the file by design"

    def test_an_ale_that_does_not_count_the_events_is_qc_071(self, tmp_path: Path) -> None:
        turnover, rows = self.scan(tmp_path, ALE_ORDER[:-1])
        assert "QC-071" in turnover_rules(Batch(turnovers=[turnover]))
        assert turnover.ale_path is None
        assert "QC-067" in rules(rows["A"]), "falling back to timecode refuses what overlaps"

    def test_with_no_ale_the_overlap_is_refused_as_before(self, tmp_path: Path) -> None:
        _, rows = self.scan(tmp_path, None)
        assert "QC-067" in rules(rows["A"])

    def test_a_retimed_clip_is_refused(self, tmp_path: Path) -> None:
        folder = overlapping_turnover(tmp_path / GOOD_FOLDER, ALE_ORDER)
        edl = folder / "FINAL.edl"
        first = edl.read_text().split("\n*ASC_SOP", 1)
        edl.write_text(
            first[0]
            + f"\nM2   AX             048.0                {fixtures.timecode(86402)}\n*ASC_SOP"
            + first[1]
        )
        _, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        plate = next(row for row in rows if row.clip_name == "A")
        assert "QC-073" in rules(plate)


class TestTheAmf:
    """Each event's AMF is the clip's colour (user, 2026-09-28). QC-075 to QC-080."""

    def scanned(self, folder: Path) -> tuple[Turnover, ShotRow]:
        turnover, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        return turnover, rows[0]

    def folder(self, tmp_path: Path) -> Path:
        return fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=1, frames=4)

    def amf(self, folder: Path) -> Path:
        return next(folder.glob("*.amf"))

    def test_a_clean_amf_raises_nothing_of_its_own(self, tmp_path: Path) -> None:
        _, row = self.scanned(self.folder(tmp_path))
        assert not rules(row) & {"QC-075", "QC-076", "QC-077", "QC-078", "QC-079"}
        assert row.grade is not None
        assert [look.kind for look in row.grade.looks] == ["look", "clf"]

    def test_an_event_with_no_amf_and_no_csv_colour_space_is_held_by_qc_046(self, tmp_path: Path) -> None:
        """Nothing says what colour it is in, so the tool cannot recreate it."""
        folder = self.folder(tmp_path)
        self.amf(folder).unlink()
        _, row = self.scanned(folder)
        assert "QC-075" not in rules(row)
        assert [result.rule_id for result in row.errors()] == ["QC-046"]
        assert row.grade is None and row.source_encoding is None

    def test_an_event_with_no_amf_renders_ungraded_from_the_csv(self, tmp_path: Path) -> None:
        """User, 2026-10-07: "If there is no CLF, AMF or CDL, assume ungraded". Resolve's
        `Input Color Space` (Apple Log in turnovers 134 and 135) is what it is read as."""
        folder = self.folder(tmp_path)
        rows = [("MELT0001_pl01", "MELT0001", "pl01")]
        fixtures.make_meta_csv(folder / "metadata.csv", rows, input_color_space="Apple Log")
        self.amf(folder).unlink()
        _, row = self.scanned(folder)
        assert not row.errors() and row.grade is None
        assert (row.source_encoding, row.source_encoding_origin) == ("Apple Log", "CSV")
        (said,) = [result for result in row.qc if result.rule_id == "QC-009"]
        assert said.severity == "info" and said.message.startswith("Clip ungraded in Resolve project")
        assert planner.plannable_identity(row) is not None

    def test_the_amf_wins_over_the_csv_colour_space(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        rows = [("MELT0001_pl01", "MELT0001", "pl01")]
        fixtures.make_meta_csv(folder / "metadata.csv", rows, input_color_space="Apple Log")
        _, row = self.scanned(folder)
        assert (row.source_encoding, row.source_encoding_origin) == (fixtures.SOURCE_ENCODING, "AMF")

    def test_an_amf_naming_another_file_is_qc_075_info_and_ungraded(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        path = self.amf(folder)
        path.write_text(path.read_text().replace("<aces:file>MELT0001_pl01<", "<aces:file>MELT0009_pl01<"))
        _, row = self.scanned(folder)
        assert row.grade is None
        assert [result.severity for result in row.qc if result.rule_id == "QC-075"] == ["info"]

    def test_two_amfs_claiming_one_event_hold_it(self, tmp_path: Path) -> None:
        """The tool cannot tell which grade is Ben's."""
        folder = self.folder(tmp_path)
        path = self.amf(folder)
        stamp = path.name.rsplit("_", 1)[-1]
        (folder / path.name.replace(stamp, "235959Z.amf")).write_text(path.read_text())
        turnover, row = self.scanned(folder)
        assert [result.rule_id for result in row.errors()] == ["QC-075"], turnover.qc

    def test_an_audio_only_event_does_not_shift_the_amfs(self, tmp_path: Path) -> None:
        """Turnover134 (2026-10-05): its EDL numbers audio-only events of its own and every
        AMF after the first was paired with the event before its clip (QC-075 on each)."""
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=2, frames=4)
        edl = folder / "FINAL_v01.edl"
        lines = edl.read_text().splitlines()
        second = next(i for i, line in enumerate(lines) if line.startswith("002 "))
        audio = lines[second - 2].replace("001 ", "002 ").replace(" V ", " A ")
        lines[second] = lines[second].replace("002 ", "003 ", 1)
        lines[second:second] = [audio, ""]
        edl.write_text("\n".join(lines) + "\n")
        _, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        assert len(rows) == 2
        for row in rows:
            assert "QC-075" not in rules(row) and row.grade is not None, row.clip_name

    def test_a_missing_file_is_only_qc_012(self, tmp_path: Path) -> None:
        """Turnover135's SECA0012 stills (user, 2026-10-06): QC-012, QC-075 and QC-046 for
        one missing file. The AMF is checked on the scan that finds the file."""
        folder = self.folder(tmp_path)
        self.amf(folder).unlink()
        for path in folder.rglob("MELT0001_pl01*.exr"):
            path.unlink()
        _, row = self.scanned(folder)
        assert row.media is None
        assert [r.rule_id for r in row.errors()] == ["QC-012"]

    def test_an_amf_numbered_for_another_event_still_grades_the_clip_it_names(self, tmp_path: Path) -> None:
        """Turnover135 (2026-10-06): its one AMF, exported on its own, is numbered 0 and
        names the sixth clip. It was reported against the first clip as the wrong AMF."""
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=2, frames=4)
        first, second = sorted(folder.glob("*.amf"), key=lambda path: path.name.rsplit("_", 3)[1])
        first.unlink()
        second.rename(folder / second.name.replace("_1_2026", "_0_2026"))
        _, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        graded = [row for row in rows if row.grade is not None]
        (lost,) = [row for row in rows if row.grade is None]
        assert len(graded) == 1 and graded[0].clip_name != lost.clip_name
        assert "QC-075" in rules(lost) and "QC-075" not in rules(graded[0])

    def cdl_instead_of_clf(self, folder: Path, keep_clf: bool = False) -> None:
        """Turnover134's AMFs: the grade as a CDL inside the AMF, and (unless kept) no CLF."""
        path = self.amf(folder)
        text = path.read_text()
        if not keep_clf:
            text = re.sub(
                r'<aces:lookTransform applied="false"><aces:file>[^<]*</aces:file></aces:lookTransform>',
                "",
                text,
            )
        text = text.replace("<aces:outputTransform", CDL_LOOK + "<aces:outputTransform", 1)
        path.write_text(text)

    def test_with_no_clf_the_amfs_cdl_is_the_grade_and_a_warning(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        self.cdl_instead_of_clf(folder)
        _, row = self.scanned(folder)
        assert row.grade is not None and row.grade.graded
        assert [look.kind for look in row.grade.looks] == ["look", "cdl"]
        assert row.grade.looks[1].cdl[:3] == (1.90655, 1.79367, 1.83671)
        (warning,) = [r for r in row.qc if r.rule_id == "QC-082"]
        assert warning.severity == "warning" and warning.message.startswith("Fix in Resolve - ")
        assert not row.errors()

    def test_a_clf_wins_over_the_cdl(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        self.cdl_instead_of_clf(folder, keep_clf=True)
        _, row = self.scanned(folder)
        assert row.grade is not None and [look.kind for look in row.grade.looks] == ["look", "clf"]
        assert "QC-082" not in rules(row) and "QC-077" in rules(row)

    def test_an_unreadable_amf_is_reported_on_the_turnover(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        (folder / "Broken_1_2026-09-28_180306Z.amf").write_text("not xml")
        turnover, _ = self.scanned(folder)
        assert "QC-075" in {r.rule_id for r in turnover.qc}

    def test_a_missing_clf_is_qc_076(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        next(folder.glob("*.clf")).unlink()
        _, row = self.scanned(folder)
        assert "QC-076" in rules(row)
        assert row.grade is not None and not row.grade.graded

    def test_a_clf_whose_md5_differs_is_qc_076(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        path = self.amf(folder)
        text = path.read_text().replace(
            "<aces:file>MELT0001_pl01_0",
            '<aces:hash algorithm="md5">00</aces:hash><aces:file>MELT0001_pl01_0',
        )
        path.write_text(text)
        _, row = self.scanned(folder)
        message = next(r.message for r in row.qc if r.rule_id == "QC-076")
        assert "md5" in message

    def test_a_look_the_config_lacks_is_ignored_with_a_warning(self, tmp_path: Path) -> None:
        """User, 2026-09-28: anything beyond primaries is ignored with a warning."""
        folder = self.folder(tmp_path)
        path = self.amf(folder)
        path.write_text(path.read_text().replace("ReferenceGamutCompress", "FilmEmulation"))
        _, row = self.scanned(folder)
        assert [r.severity for r in row.qc if r.rule_id == "QC-077"] == ["warning"]
        assert row.grade is not None and [look.kind for look in row.grade.looks] == ["clf"]

    def test_the_dailies_preset_is_info(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        path = self.amf(folder)
        path.write_text(path.read_text().replace("VFX Request", "Dailies Request"))
        _, row = self.scanned(folder)
        assert [r.severity for r in row.qc if r.rule_id == "QC-078"] == ["info"]

    def test_an_output_transform_the_config_lacks_is_qc_079(self, tmp_path: Path) -> None:
        folder = self.folder(tmp_path)
        path = self.amf(folder)
        path.write_text(path.read_text().replace("sRGB-Piecewise", "Unknown-Display"))
        _, row = self.scanned(folder)
        assert "QC-079" in rules(row)
        assert row.grade is not None and row.grade.display is None

    def test_a_display_a_reference_cannot_be_labelled_for_is_qc_079(self, tmp_path: Path) -> None:
        """P3 is in the config, but an 8 bit Rec.709 mp4 is not a P3 encode."""
        folder = self.folder(tmp_path)
        path = self.amf(folder)
        p3 = "Output.Academy.P3-D65_100nit_in_P3-D65_sRGB-Piecewise.a2.v1"
        text = path.read_text().replace(
            "Output.Academy.Rec709-D65_100nit_in_Rec709-D65_sRGB-Piecewise.a2.v1", p3
        )
        path.write_text(text)
        _, row = self.scanned(folder)
        assert "QC-079" in rules(row)
        assert row.grade is not None and row.grade.display is None

    def test_an_amf_with_no_clf_is_qc_009_info_at_preflight(self, tmp_path: Path) -> None:
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=1, frames=4, graded=False)
        turnover, row = self.scanned(folder)
        batch = Batch(delivery_root=tmp_path, turnovers=[turnover], rows=[row])
        qc.preflight(batch)
        assert [(r.rule_id, r.severity) for r in row.qc if r.rule_id == "QC-009"] == [("QC-009", "info")]
        assert not qc.must_fix(batch)

    def test_an_hdri_row_is_delivered_and_blocks_nothing(self, tmp_path: Path) -> None:
        """User, 2026-10-07: its EXR is copied as it is; no pre-render beside it is QC-083."""
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=1, frames=4, shot_types=["HDRI"])
        turnover, row = self.scanned(folder)
        assert not row.skipped and row.identity is not None and row.identity.is_hdri
        assert {"QC-080", "QC-083"} <= set(rules(row)) and not row.errors()
        assert not qc.must_fix(Batch(delivery_root=tmp_path, turnovers=[turnover], rows=[row]))

    def test_a_style_frame_blocks_nothing_and_delivers_nothing(self, tmp_path: Path) -> None:
        """User, 2026-10-07: a pre-graded PNG or JPG held on the stringout, and that is all."""
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=1, frames=4, shot_types=["styleFrame"])
        for path in (folder / "media").iterdir():
            path.unlink()
        fixtures.make_still(folder / "media" / "MELT0001_pl01.png")
        turnover, row = self.scanned(folder)
        assert row.identity is not None and row.identity.is_style_frame and qc.is_style_frame(row)
        assert row.media is not None and row.media.frame_count == 1
        assert rules(row) == {"QC-085"}, "no rule runs on it, and its AMF's findings go unsaid"
        batch = Batch(delivery_root=tmp_path, turnovers=[turnover], rows=[row])
        qc.preflight(batch)
        assert not qc.must_fix(batch) and planner.plannable_identity(row) is None

    def test_an_hdri_and_its_pre_render_are_not_ambiguous(self, tmp_path: Path) -> None:
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=1, frames=4, shot_types=["HDRI"])
        fixtures.make_mp4(folder / "media" / "MELT0001_pl01.mp4", count=4)
        _, row = self.scanned(folder)
        assert row.media is not None and row.media.path.suffix == ".exr"
        assert row.hdri_render is not None and row.hdri_render.path.suffix == ".mp4"
        assert "QC-013" not in rules(row) and "QC-083" not in rules(row)

    def test_an_hdri_with_no_amf_is_not_an_error(self, tmp_path: Path) -> None:
        """Turnover135 (2026-10-05): QC-075 on each HDRI, which is never graded (QC-080)."""
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=1, frames=4, shot_types=["HDRI"])
        self.amf(folder).unlink()
        _, row = self.scanned(folder)
        assert "QC-080" in rules(row) and not row.errors()


class TestAPreRenderOnTheTimeline:
    """Turnover134 and 135 (2026-10-07): the timeline cuts Ben's pre-render, named
    `<HDRI EXR> Render 1.mov`, typed HDRI; the EXR is off the cut. The pre-render is the
    stringout's event, and the EXR it is named after is delivered when it is in the folder
    (user: "If the EXR isn't in the turnover folder ... do nothing for the HDRI delivery")."""

    RENDER = "MELT0001_pl01_HDRI_01_v01.exr Render 1.mp4"
    EXR = "MELT0001_pl01_HDRI_01_v01.exr"

    def folder(self, tmp_path: Path, exr: bool, render: bool = True, exr_row: bool = False) -> Path:
        root = tmp_path / GOOD_FOLDER
        if render:
            fixtures.make_mp4(root / self.RENDER, count=4)
        if exr:
            fixtures.make_exr_sequence(root / "x", count=1)
            next((root / "x").glob("*.exr")).rename(root / self.EXR)
        rows = [(self.RENDER, "MELT0001", "HDRI")] + ([(self.EXR, "MELT0001", "HDRI")] if exr_row else [])
        fixtures.make_meta_csv(root / "metadata.csv", rows)
        fixtures.make_final_edl(root / "FINAL_v01.edl", [self.RENDER], duration=4)
        return root

    def scanned(self, folder: Path) -> list[ShotRow]:
        _, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        return rows

    def test_the_exr_it_is_named_after_is_delivered(self, tmp_path: Path) -> None:
        (row,) = self.scanned(self.folder(tmp_path, exr=True))
        assert row.media is not None and row.media.path.name == self.EXR
        assert row.hdri_render is not None and row.hdri_render.path.name == self.RENDER
        assert not row.errors() and not rules(row) & {"QC-083", "QC-086"}
        jobs = planner.plan_row(row, tmp_path / "out", 1).jobs
        assert [job.kind for job in jobs] == ["hdri"] and jobs[0].source.name == self.EXR

    def test_no_exr_is_qc_086_and_nothing_is_delivered(self, tmp_path: Path) -> None:
        (row,) = self.scanned(self.folder(tmp_path, exr=False))
        (note,) = [result for result in row.qc if result.rule_id == "QC-086"]
        assert note.severity == "warning"
        assert note.message.startswith("HDRI EXR File Missing from turnover folder, omitted from delivery")
        assert row.hdri_render is not None and not row.errors()
        assert planner.plan_row(row, tmp_path / "out", 1).jobs == []

    def test_the_csv_s_own_exr_row_folds_into_the_pre_render(self, tmp_path: Path) -> None:
        """Turnover135 lists the EXR too, which no EDL event cuts: not a second HDRI (QC-066)."""
        rows = self.scanned(self.folder(tmp_path, exr=True, exr_row=True))
        assert [row.clip_name for row in rows] == [self.RENDER]
        assert "QC-066" not in rules(rows[0])

    def test_a_pre_render_not_in_the_folder_is_qc_083(self, tmp_path: Path) -> None:
        """Rendered somewhere else, or the timeline points at another folder."""
        (row,) = self.scanned(self.folder(tmp_path, exr=True, render=False))
        (note,) = [result for result in row.qc if result.rule_id == "QC-083"]
        assert note.severity == "warning" and "not in the turnover folder" in note.message
        assert row.media is not None and not row.errors()

    def test_with_no_color_files_it_is_shown_as_it_is(self, tmp_path: Path) -> None:
        """User, 2026-10-07: "If there's not color files, you can skip any color correction"."""
        (row,) = self.scanned(self.folder(tmp_path, exr=True))
        (note,) = [result for result in row.qc if result.rule_id == "QC-009"]
        assert note.severity == "info" and "no color correction" in note.message


class TestAnLdri:
    """User, 2026-10-08: an LDRI is an HDRI whose file is a JPG or PNG. Its pre-render is
    named the same way (`<LDRI image> Render 1.mov`) and the image is delivered byte for
    byte under its own extension."""

    RENDER = "MELT0001_pl01_LDRI_01_v01.jpg Render 1.mp4"
    IMAGE = "MELT0001_pl01_LDRI_01_v01.jpg"

    def folder(self, tmp_path: Path, image: bool, render: bool = True, image_row: bool = False) -> Path:
        root = tmp_path / GOOD_FOLDER
        if render:
            fixtures.make_mp4(root / self.RENDER, count=4)
        if image:
            fixtures.make_still(root / self.IMAGE)
        rows = [(self.RENDER, "MELT0001", "LDRI")] + ([(self.IMAGE, "MELT0001", "LDRI")] if image_row else [])
        fixtures.make_meta_csv(root / "metadata.csv", rows)
        fixtures.make_final_edl(root / "FINAL_v01.edl", [self.RENDER], duration=4)
        return root

    def scanned(self, folder: Path) -> list[ShotRow]:
        _, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        return rows

    def test_the_image_it_is_named_after_is_delivered_as_an_ldri(self, tmp_path: Path) -> None:
        (row,) = self.scanned(self.folder(tmp_path, image=True))
        assert qc.is_hdri(row) and qc.is_ldri(row)
        assert row.media is not None and row.media.path.name == self.IMAGE
        assert row.hdri_render is not None and row.hdri_render.path.name == self.RENDER
        assert not row.errors() and not rules(row) & {"QC-083", "QC-086"}
        (job,) = planner.plan_row(row, tmp_path / "out", 1).jobs
        assert (job.kind, job.source.name, job.destination.name) == ("hdri", self.IMAGE, self.IMAGE)

    def test_no_image_is_qc_086_in_ldri_words(self, tmp_path: Path) -> None:
        (row,) = self.scanned(self.folder(tmp_path, image=False))
        (note,) = [result for result in row.qc if result.rule_id == "QC-086"]
        assert note.message.startswith("LDRI JPG File Missing from turnover folder, omitted from delivery")
        assert planner.plan_row(row, tmp_path / "out", 1).jobs == []

    def test_the_csv_s_own_image_row_folds_into_the_pre_render(self, tmp_path: Path) -> None:
        rows = self.scanned(self.folder(tmp_path, image=True, image_row=True))
        assert [row.clip_name for row in rows] == [self.RENDER]

    def test_a_pre_render_not_in_the_folder_holds_the_image(self, tmp_path: Path) -> None:
        (row,) = self.scanned(self.folder(tmp_path, image=True, render=False))
        (note,) = [result for result in row.qc if result.rule_id == "QC-083"]
        assert "the LDRI JPG held still" in note.message and not row.errors()


@pytest.mark.parametrize(
    ("prerender", "source"),
    [
        ("SECA0009_pl01_HDRI_01_v01.exr Render 1.mov", "SECA0009_pl01_HDRI_01_v01.exr"),
        ("SECA0009_pl01_LDRI_01_v01.jpg Render.mov", "SECA0009_pl01_LDRI_01_v01.jpg"),
        ("SECA0009_pl01_LDRI_01_v01.JPEG Render 1.mov", "SECA0009_pl01_LDRI_01_v01.JPEG"),
        ("SECA0009_pl01_LDRI_01_v01.png Render 1.mov", "SECA0009_pl01_LDRI_01_v01.png"),
        ("SECA0009_pl01_HDRI_01_v01 Render 1.mov", None),
        ("a.exrs Render.mov", None),
    ],
)
def test_hdri_source_name(prerender: str, source: str | None) -> None:
    assert scan.hdri_source_name(prerender) == source


class TestACutOutsideItsFile:
    """User, 2026-10-07: the timeline at face value. A cut the file's own timecode puts
    outside it is read by Resolve's clock, the CSV's `Start TC`, with nothing said; when
    neither fits, the frames the file has are rendered and QC-029 notes it."""

    def folder(self, tmp_path: Path, start_tc: str | None) -> Path:
        folder = fixtures.make_turnover(tmp_path / GOOD_FOLDER, shots=1, frames=4)
        edl = folder / "FINAL_v01.edl"
        edl.write_text(edl.read_text().replace("01:00:00:00 01:00:00:04 ", "00:59:50:00 00:59:50:04 ", 1))
        if start_tc is not None:
            csv = folder / "metadata.csv"
            lines = csv.read_bytes().decode("utf-16").splitlines()
            lines = [f'{lines[0]},"Start TC"'] + [f'{line},"{start_tc}"' for line in lines[1:]]
            csv.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-16"))
        return folder

    def scanned(self, folder: Path) -> ShotRow:
        _, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
        return rows[0]

    def test_resolve_s_clock_puts_it_inside_and_nothing_is_said(self, tmp_path: Path) -> None:
        """Turnover134's mirror balls: probe noise from media management, not a fault."""
        row = self.scanned(self.folder(tmp_path, "00:59:50:00"))
        assert row.media is not None
        assert not rules(row) & {"QC-029", "QC-084"} and not row.errors()
        assert row.current == InOut(row.media.start_frame, row.media.start_frame + 3)

    def test_with_no_clock_that_fits_it_renders_what_the_file_has_with_a_note(self, tmp_path: Path) -> None:
        row = self.scanned(self.folder(tmp_path, None))
        assert row.media is not None and not row.errors()
        (said,) = [result for result in row.qc if result.rule_id == "QC-029"]
        assert said.severity == "info"
        assert "00:59:50:00 to 00:59:50:03" in said.message
        assert "rendered the 4 frames the file has" in said.message
        assert row.current == InOut(row.media.start_frame, row.media.start_frame + 3)
        assert planner.plannable_identity(row) is not None
