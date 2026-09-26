"""Scanning a turnover folder into shot rows, and the QC the scan uncovers."""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import scan
from proingest.core.models import Batch, Deliverable, InOut, ShotRow, Turnover
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
        assert orphan.cdl is None and orphan.approved is None
        assert orphan.current is not None, "it still shows what arrived, so it can be trimmed by hand"

    def test_an_unnamed_event_inside_two_files_is_refused_on_both(self, tmp_path: Path) -> None:
        """Both fixture sequences start at 01:00:00:00, so a nameless event fits either."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=2, frames=4)
        fixtures.make_final_edl(folder / "FINAL_v01.edl", [""], duration=4)
        _, rows = scan.scan_turnover(folder, "t1")
        for row in rows:
            assert "QC-067" in rules(row)
            assert row.cdl is None and row.approved is None

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
