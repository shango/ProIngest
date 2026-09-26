"""The turnover stringout (OQ-38, reopened 2026-09-25): planned from the final EDL, cut from
the delivered HD references, the ungraded source or black where there is none."""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from proingest.core import ffmpeg, naming, planner, qc, render, scan, stringout
from proingest.core.models import Batch, InOut
from tests.fixtures import media as fixtures

FOLDER = "turnover007_09_23_2026_testshooter"
FRAMES = 12


@pytest.fixture(scope="module")
def delivered(tmp_path_factory: pytest.TempPathFactory) -> Batch:
    """Two plates scanned and rendered once for the module; each test takes a copy."""
    base = tmp_path_factory.mktemp("stringout")
    folder = fixtures.make_turnover(base / FOLDER, shots=2, frames=FRAMES)
    settings = scan.ScanSettings(rules=fixtures.SMALL_RULES)
    batch = Batch(delivery_root=base / "delivery")
    turnover, rows = scan.scan_turnover(folder, "t1", settings, probe_cache=batch.probe_cache)
    batch.turnovers, batch.rows = [turnover], rows
    assert batch.delivery_root is not None
    render.apply_results(batch, render.execute(planner.plan_batch(batch, batch.delivery_root), workers=2))
    return batch


@pytest.fixture
def batch(delivered: Batch) -> Batch:
    return copy.deepcopy(delivered)


def planned(batch: Batch) -> stringout.Plan:
    assert batch.delivery_root is not None
    return stringout.plan(batch, batch.turnovers[0], batch.delivery_root)


class TestNaming:
    def test_the_stem_is_dated_as_the_turnover_folder_is(self) -> None:
        stem = naming.stringout_stem(121, 9, 23, 2026, "danielluckett", 1)
        assert stem == "turnover121_09_23_2026_danielluckett_SO_v01"
        assert naming.stringout_mp4(7, 9, 23, 2026, "x", 2) == "turnover007_09_23_2026_x_SO_v02.mp4"

    def test_a_version_is_read_back_only_for_the_same_turnover(self) -> None:
        name = "turnover121_09_23_2026_danielluckett_SO_v03.mp4"
        assert naming.stringout_version(name, 121, 9, 23, 2026, "danielluckett") == 3
        assert naming.stringout_version(name, 122, 9, 23, 2026, "danielluckett") is None
        assert naming.stringout_version("qc_ingest_log.xlsx", 121, 9, 23, 2026, "danielluckett") is None

    def test_the_label_is_the_shot_and_element_or_the_still(self) -> None:
        assert naming.shot_label(naming.ShotIdentity("TIME1001", "pl", "01")) == "TIME1001_pl01"
        assert (
            naming.shot_label(naming.ShotIdentity("SECA0002", "colorChart", "01")) == "SECA0002_colorChart_01"
        )


class TestPlan:
    def test_every_event_is_cut_from_its_delivered_reference(self, batch: Batch) -> None:
        made = planned(batch)
        assert [s.kind for s in made.segments] == ["reference", "reference"]
        assert [s.label for s in made.segments] == ["MELT0001_pl01", "MELT0002_pl01"]
        assert all(s.first_frame == 1001 and s.start == 0 and s.length == FRAMES for s in made.segments)
        assert all(s.audio for s in made.segments), "plates carry their sound"
        assert made.stem == f"{FOLDER}_SO_v01" and made.total == 2 * FRAMES
        assert made.timecode == "01:00:00:00", "the EDL's record start"

    def test_a_skipped_shot_is_the_ungraded_source(self, batch: Batch) -> None:
        batch.rows[1].skipped = True
        second = planned(batch).segments[1]
        assert second.kind == "source" and not second.audio
        assert second.path == batch.rows[1].media.path if batch.rows[1].media else False

    def test_the_counter_is_the_delivered_frame_under_a_trim(self, batch: Batch) -> None:
        """Handles trimmed in ahead of the cut: the cut's first frame is the plate's 1003."""
        row = batch.rows[0]
        assert row.delivered_range is not None
        row.delivered_range = InOut(row.delivered_range.in_frame - 2, row.delivered_range.out_frame)
        first = planned(batch).segments[0]
        assert (first.kind, first.first_frame, first.start) == ("reference", 1003, 2)

    def test_a_cut_the_delivery_does_not_hold_falls_back_to_the_source(self, batch: Batch) -> None:
        row = batch.rows[0]
        assert row.delivered_range is not None
        row.delivered_range = InOut(row.delivered_range.in_frame + 2, row.delivered_range.out_frame)
        assert planned(batch).segments[0].kind == "source"

    def test_an_event_nothing_claims_is_black(self, batch: Batch) -> None:
        batch.rows = [batch.rows[0]]
        second = planned(batch).segments[1]
        assert second.kind == "black" and second.length == FRAMES

    def test_a_gap_in_the_record_timeline_is_black_with_only_the_name(self, batch: Batch) -> None:
        edl = batch.turnovers[0].edl_path
        assert edl is not None
        original = edl.read_text()
        lines = original.splitlines()
        second = next(i for i, line in enumerate(lines) if line.startswith("002"))
        parts = lines[second].split()
        rec_in = fixtures.timecode(86400 + FRAMES + 5)
        rec_out = fixtures.timecode(86400 + 2 * FRAMES + 5)
        lines[second] = "  ".join([*parts[:6], rec_in, rec_out])
        edl.write_text("\n".join(lines) + "\n")
        try:
            made = planned(batch)
        finally:
            edl.write_text(original)  # the folder is the module's, shared by every test
        assert [(s.kind, s.gap, s.length) for s in made.segments] == [
            ("reference", False, FRAMES),
            ("black", True, 5),
            ("reference", False, FRAMES),
        ]

    def test_the_next_one_takes_the_next_version(self, batch: Batch) -> None:
        made = planned(batch)
        made.destination.parent.mkdir(parents=True, exist_ok=True)
        made.destination.touch()
        try:
            assert planned(batch).stem.endswith("_SO_v02")
        finally:
            made.destination.unlink()

    def test_a_folder_name_with_no_date_cannot_be_named(self, batch: Batch) -> None:
        batch.turnovers[0] = replace(batch.turnovers[0], number=None)
        with pytest.raises(stringout.StringoutError, match="no name"):
            planned(batch)


class TestBuild:
    def test_it_is_written_checked_and_recorded(self, batch: Batch) -> None:
        batch.rows[1].skipped = True
        assert batch.delivery_root is not None
        turnover = batch.turnovers[0]
        made = stringout.build(batch, turnover, batch.delivery_root)

        assert made is not None and made.path.is_file() and turnover.stringout == made
        assert qc.check_stringout(made.path, 2 * FRAMES, stringout.SIZE, stringout.RATE) == []
        assert not list(made.path.parent.glob("*.part")) and not list(made.path.parent.glob(".*.parts"))
        video = next(s for s in ffmpeg.probe_raw(made.path)["streams"] if s["codec_type"] == "video")
        assert video["tags"]["timecode"] == "01:00:00:00"
        assert [r.rule_id for r in turnover.qc if r.rule_id in stringout.STRINGOUT_RULES] == ["QC-143"]
        made.path.unlink()

    def test_one_that_cannot_be_made_is_qc_142_and_raises_nothing(self, batch: Batch) -> None:
        batch.turnovers[0] = replace(batch.turnovers[0], shooter="")
        assert batch.delivery_root is not None
        assert stringout.build(batch, batch.turnovers[0], batch.delivery_root) is None
        assert [r.rule_id for r in batch.turnovers[0].qc] == ["QC-142"]
        assert not qc.must_fix(batch), "phase B: it reports, it does not block the next run"


class TestBurnIns:
    def test_a_freeze_holds_its_frame_number(self, tmp_path: Path) -> None:
        held = stringout.Segment(kind="reference", length=48, first_frame=1001, freeze=True, label="X_pl01")
        stringout._burn_ins("so", held, tmp_path / "0000")
        assert (tmp_path / "0000_1.txt").read_text() == "Frame: 1001"

    def test_a_running_shot_counts_from_its_first_frame(self, tmp_path: Path) -> None:
        running = stringout.Segment(kind="reference", length=48, first_frame=1009, label="X_pl01")
        stringout._burn_ins("so", running, tmp_path / "0000")
        assert (tmp_path / "0000_1.txt").read_text() == "Frame: %{eif:n+1009:d}"

    def test_a_gap_carries_only_the_name(self, tmp_path: Path) -> None:
        assert (
            len(
                stringout._burn_ins("so", stringout.Segment(kind="black", length=5, gap=True), tmp_path / "g")
            )
            == 1
        )


class TestFfmpeg:
    def test_text_from_a_csv_is_printed_as_written(self) -> None:
        assert ffmpeg.drawtext_literal("50% rain \\ wind") == "50\\% rain \\\\ wind"

    def test_segments_are_joined_by_stream_copy_at_the_record_timecode(self, tmp_path: Path) -> None:
        command = ffmpeg.concat_command(tmp_path / "list.txt", tmp_path / "out.part", "01:00:00:00")
        assert command[command.index("-c") + 1] == "copy"
        assert command[command.index("-timecode") + 1] == "01:00:00:00"
