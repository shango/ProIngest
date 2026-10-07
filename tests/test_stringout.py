"""The turnover stringout (OQ-38, reopened 2026-09-25): planned from the final EDL, cut from
the delivered HD references, the ungraded source or black where there is none."""

from __future__ import annotations

import copy
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from proingest.core import clf, color, ffmpeg, naming, planner, qc, render, scan, stringout
from proingest.core.models import Batch, Deliverable, FrameRate, InOut, MediaInfo
from tests.fixtures import media as fixtures

FOLDER = "turnover007_09_23_26_testshooter"
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
        assert stem == "turnover121_09_23_26_danielluckett_SO_v01"
        assert naming.stringout_mp4(7, 9, 23, 2026, "x", 2) == "turnover007_09_23_26_x_SO_v02.mp4"

    def test_a_version_is_read_back_only_for_the_same_turnover(self) -> None:
        name = "turnover121_09_23_26_danielluckett_SO_v03.mp4"
        assert naming.stringout_version(name, 121, 9, 23, 2026, "danielluckett") == 3
        assert naming.stringout_version(name, 122, 9, 23, 2026, "danielluckett") is None
        assert naming.stringout_version("qc_ingest_log.xlsx", 121, 9, 23, 2026, "danielluckett") is None

    def test_a_stringout_named_with_a_four_digit_year_is_still_a_version(self) -> None:
        """Written before 2026-10-05, when the stem carried the year in full."""
        name = "turnover121_09_23_2026_danielluckett_SO_v02.mp4"
        assert naming.stringout_version(name, 121, 9, 23, 2026, "danielluckett") == 2

    def test_the_label_is_the_shot_and_element_or_the_still(self) -> None:
        assert naming.shot_label(naming.ShotIdentity("TIME1001", "pl", "01")) == "TIME1001_pl01"
        assert (
            naming.shot_label(naming.ShotIdentity("SECA0002", "colorChart", "01")) == "SECA0002_colorChart_01"
        )


class TestPlan:
    def test_every_event_is_cut_from_its_delivered_exrs(self, batch: Batch) -> None:
        """User, 2026-10-07: the stringout is from the EXRs, the HD sequence of each plate."""
        made = planned(batch)
        assert [s.kind for s in made.segments] == ["reference", "reference"]
        assert [s.label for s in made.segments] == ["MELT0001_pl01", "MELT0002_pl01"]
        assert all(s.first_frame == 1001 and s.start == 0 and s.length == FRAMES for s in made.segments)
        assert all(s.exr is not None and s.exr.source.name.endswith("_raw_HD_v01") for s in made.segments)
        assert all(s.wav is not None and s.wav.suffix == ".wav" for s in made.segments), "plates carry sound"
        assert made.stem == f"{FOLDER}_SO_v01" and made.total == 2 * FRAMES
        assert made.timecode == "01:00:00:00", "the EDL's record start"

    def test_a_take_above_1_follows_the_label(self, batch: Batch) -> None:
        """User, 2026-10-07: `SECA0009_pl01 Take 02`; take 1 or none shows no take."""
        batch.rows[0].take, batch.rows[1].take = "1", "2"
        assert [s.label for s in planned(batch).segments] == ["MELT0001_pl01", "MELT0002_pl01 Take 02"]

    def test_with_no_hd_exr_the_reference_stands_in(self, batch: Batch) -> None:
        for item in batch.rows[1].deliverables:
            if item.kind == "raw_dir" and item.res == "HD":
                item.status = "failed"
        plate = planned(batch).segments[1]
        assert plate.exr is None and plate.path is not None and plate.path.name.endswith("_ref_HD_v01.mp4")
        assert plate.audio and plate.wav is None, "its sound comes with the reference"

    def test_a_held_reference_clip_is_cut_from_its_delivered_exr(self, batch: Batch) -> None:
        """Held (an `M2` freeze), a chart is its one delivered EXR frame, graded, for a second."""
        edl = batch.turnovers[0].edl_path
        assert edl is not None
        lines = edl.read_text().splitlines()
        second = next(i for i, line in enumerate(lines) if line.startswith("002"))
        lines.insert(second + 1, "M2   AX             000.0                00:00:00:00")
        edl.write_text("\n".join(lines) + "\n")
        row = batch.rows[1]
        row.identity = naming.ShotIdentity("MELT0002", "colorChart", "01")
        frame = next(item.path for item in row.deliverables if item.kind == "raw_dir" and item.res == "HD")
        still = sorted(frame.glob("*.exr"))[0]
        row.deliverables = [Deliverable("aux_still", still.name, still, 1, "4k", status="done")]
        try:
            segment = planned(batch).segments[1]
        finally:
            del lines[second + 1]
            edl.write_text("\n".join(lines) + "\n")
        assert segment.exr is not None and segment.exr.source == still
        assert segment.exr.color.source_encoding == "ACEScg" and segment.exr.color.looks, "graded"
        assert (segment.start, segment.freeze, segment.length) == (0, True, stringout.STILL_LENGTH)

    def test_a_playing_reference_clip_is_not_cut_from_its_one_exr_frame(self, batch: Batch) -> None:
        row = batch.rows[1]
        row.identity = naming.ShotIdentity("MELT0002", "colorChart", "01")
        frame = next(item.path for item in row.deliverables if item.kind == "raw_dir" and item.res == "HD")
        still = sorted(frame.glob("*.exr"))[0]
        row.deliverables = [Deliverable("aux_still", still.name, still, 1, "4k", status="done")]
        segment = planned(batch).segments[1]
        assert segment.exr is None and segment.kind == "source" and segment.length == FRAMES

    def test_an_exr_is_seen_through_its_output_transform_on_the_hd_canvas(self, batch: Batch) -> None:
        segment = planned(batch).segments[0]
        assert segment.exr is not None
        first = sorted(segment.exr.source.glob("*.exr"))[0]
        assert segment.exr.color.looks == (), "a plate's EXR has its grade in it already"
        cpu = color.processor(*segment.exr.color.view_transforms())
        shown = stringout._shown(first, cpu)
        assert shown.shape == (1080, 1920, 3) and float(shown.min()) >= 0.0 and float(shown.max()) <= 1.0

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


class TestInsets:
    """A plate carries its shot's cp top left and wit top right (user, 2026-09-29)."""

    @staticmethod
    def as_kind(batch: Batch, index: int, shot: str, kind: str) -> None:
        batch.rows[index].identity = naming.ShotIdentity(shot, kind, "01")

    def test_a_plate_carries_its_shots_cp_top_left(self, batch: Batch) -> None:
        self.as_kind(batch, 1, "MELT0001", "cp")
        plate, clean = planned(batch).segments
        assert clean.path is not None
        assert plate.insets == (
            stringout.PictureInPicture(
                ffmpeg.Inset(clean.path, 0, FRAMES, 0, 0, stringout.INSET_SIZE), "cp01", clean.exr
            ),
        )
        assert clean.insets == (), "only a plate carries insets"

    def test_a_wit_goes_top_right(self, batch: Batch) -> None:
        self.as_kind(batch, 1, "MELT0001", "wit")
        (inset,) = planned(batch).segments[0].insets
        assert (inset.picture.x, inset.picture.y, inset.label) == (1440, 0, "wit01")

    def test_another_shots_cp_is_not_inset(self, batch: Batch) -> None:
        self.as_kind(batch, 1, "MELT0009", "cp")
        assert planned(batch).segments[0].insets == ()

    def test_a_cp_with_no_delivered_reference_is_no_inset(self, batch: Batch) -> None:
        self.as_kind(batch, 1, "MELT0001", "cp")
        batch.rows[1].skipped = True
        assert planned(batch).segments[0].insets == ()

    def test_an_inset_never_outruns_the_plate(self) -> None:
        clip = stringout.Segment(
            kind="reference",
            length=300,
            path=Path("/r.mp4"),
            start=4,
            identity=naming.ShotIdentity("A0001", "cp", "01"),
        )
        inset = stringout._inset(clip, 120, (0, 0))
        assert inset is not None and (inset.picture.start, inset.picture.length) == (4, 120)

    def test_an_inset_is_labelled_with_its_element_a_little_smaller(self, tmp_path: Path) -> None:
        picture = ffmpeg.Inset(Path("/r.mp4"), 0, 5, 0, 0, stringout.INSET_SIZE)
        plate = stringout.Segment(
            kind="reference", length=5, insets=(stringout.PictureInPicture(picture, "cp01"),)
        )
        (labelled,) = stringout._labelled(plate, tmp_path / "0000")
        (drawn,) = labelled.filters
        assert (tmp_path / "0000_inset0.txt").read_text() == "cp01"
        assert (
            f"fontsize={stringout.INSET_FONT_SIZE}" in drawn
            and stringout.INSET_FONT_SIZE < stringout.FONT_SIZE
        )
        assert "drawtext" in ffmpeg.inset_graph(["null"], [labelled], ["null"]).split("[p0]")[0]

    def test_an_inset_is_drawn_and_then_gone(self, tmp_path: Path) -> None:
        """Rendered: red in the top left for the inset's frames, then the plate again."""

        def clip(path: Path, colour: str, count: int) -> Path:
            source = f"color=c={colour}:s=192x108:r=24"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source, "-frames:v", str(count),
                 "-pix_fmt", "yuv420p", str(path)],
                check=True,
            )  # fmt: skip
            return path

        plate, red = clip(tmp_path / "plate.mp4", "black", 12), clip(tmp_path / "red.mp4", "red", 10)
        out = tmp_path / "out.mp4"
        inset = ffmpeg.Inset(red, 2, 5, 0, 0, (48, 28))
        command = ffmpeg.encode_command(
            str(plate), out, 0, 11, is_sequence=False, rate="24/1",
            color_space="bt709", color_range="tv", insets=[inset], silence=True,
        )  # fmt: skip
        assert ffmpeg.run(command).returncode == 0
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True,
        ).stdout  # fmt: skip
        frames = [decoded[i : i + 192 * 108 * 3] for i in range(0, len(decoded), 192 * 108 * 3)]
        assert len(frames) == 12

        def red_at(frame: bytes, x: int, y: int) -> bool:
            r, g, b = frame[(y * 192 + x) * 3 : (y * 192 + x) * 3 + 3]
            return r > 150 and g < 80 and b < 80

        assert [red_at(frame, 20, 12) for frame in frames] == [True] * 5 + [False] * 7
        assert not any(red_at(frame, 100, 60) for frame in frames), "only inside the inset"


class TestReferenceClips:
    """A chart, ball or size ref is a video on the timeline: its event plays its cut at full
    speed, graded through its AMF (user, 2026-10-07). It is delivered as one EXR frame."""

    @staticmethod
    def as_chart(batch: Batch) -> None:
        """No HD reference, as a still has none: its frame comes from the source."""
        batch.rows[1].identity = naming.ShotIdentity("MELT0002", "colorChart", "01")
        batch.rows[1].deliverables = []

    def test_a_reference_clip_plays_its_cut_through_its_amf(self, batch: Batch) -> None:
        self.as_chart(batch)
        clip = planned(batch).segments[1]
        assert (clip.kind, clip.length, clip.freeze) == ("source", FRAMES, False)
        assert clip.color is not None and clip.color.looks, "graded"
        assert planned(batch).total == 2 * FRAMES

    def test_its_colour_is_baked_as_a_reference_is(self, batch: Batch, tmp_path: Path) -> None:
        self.as_chart(batch)
        still = planned(batch).segments[1]
        lut = stringout._still_lut(still, tmp_path / "still.cube")
        assert lut is not None and lut.read_text().startswith("LUT_3D_SIZE")

    def test_a_still_whose_amf_resolves_to_nothing_stays_ungraded(self, tmp_path: Path) -> None:
        still = stringout.Segment(kind="source", length=24, color=clf.ShotColor())
        assert stringout._still_lut(still, tmp_path / "still.cube") is None

    def test_a_one_frame_cut_of_any_clip_is_held_too(self, batch: Batch) -> None:
        """User: "the same for any still image frames". The cut decides, not the type."""
        event = scan.read_session(batch.turnovers[0], batch.project_rate).events[1]
        plate = batch.rows[1].identity
        assert plate is not None and plate.kind == "pl"
        assert stringout._held(event, InOut(1001, 1001))
        assert not stringout._held(event, InOut(1001, 1011))

    def test_a_plate_is_not_held(self, batch: Batch) -> None:
        batch.rows[1].skipped = True
        plate = planned(batch).segments[1]
        assert (plate.kind, plate.length, plate.freeze) == ("source", FRAMES, False)
        assert plate.color is not None and plate.color.looks, "graded through its AMF (user, 2026-10-07)"


class TestAnHdri:
    """The HDRI on the timeline is a frame hold on the HDRI EXR with a pan (user, 2026-10-07).
    Its EXR is delivered byte for byte; its event is cut from Ben's pre-render, a video under
    the EXR's name, graded through the HDRI's AMF. No pre-render: QC-083, the EXR as it is."""

    @staticmethod
    def scanned(folder: Path, batch: Batch) -> Batch:
        settings = scan.ScanSettings(rules=fixtures.SMALL_RULES)
        turnover, rows = scan.scan_turnover(folder, "t1", settings, probe_cache=batch.probe_cache)
        batch.turnovers, batch.rows = [turnover], rows
        assert batch.delivery_root is not None
        render.apply_results(batch, render.execute(planner.plan_batch(batch, batch.delivery_root), workers=2))
        return batch

    @pytest.fixture
    def folder(self, tmp_path: Path) -> Path:
        return fixtures.make_turnover(tmp_path / FOLDER, shots=2, frames=FRAMES, shot_types=["pl01", "HDRI"])

    @pytest.fixture
    def with_hdri(self, folder: Path, tmp_path: Path) -> Batch:
        return self.scanned(folder, Batch(delivery_root=tmp_path / "delivery"))

    @pytest.fixture
    def with_render(self, folder: Path, tmp_path: Path) -> Batch:
        fixtures.make_mp4(folder / "media" / "MELT0002_pl01.mp4", count=FRAMES)
        return self.scanned(folder, Batch(delivery_root=tmp_path / "delivery"))

    def test_its_exr_is_delivered_byte_for_byte(self, with_hdri: Batch) -> None:
        hdri = with_hdri.rows[1]
        assert qc.is_hdri(hdri) and not hdri.skipped and hdri.media is not None
        (item,) = hdri.deliverables
        assert (item.kind, item.name, item.status) == ("hdri", "MELT0002_pl01_HDRI_01_v01.exr", "done")
        assert item.path.read_bytes() == hdri.media.path.read_bytes()

    def test_with_no_pre_render_it_asks_for_one_and_holds_the_exr_graded(self, with_hdri: Batch) -> None:
        hdri = with_hdri.rows[1]
        assert [(q.rule_id, q.severity) for q in hdri.qc if q.rule_id == "QC-083"] == [("QC-083", "warning")]
        segment = planned(with_hdri).segments[1]
        assert hdri.media is not None and segment.path == hdri.media.path
        assert segment.exr is not None and segment.exr.color.source_encoding == "Linear Rec.709 (sRGB)"
        assert segment.exr.color.looks and segment.freeze and not segment.prerender

    def test_the_stringout_is_written_with_the_held_exr(self, with_hdri: Batch) -> None:
        assert with_hdri.delivery_root is not None
        made = stringout.build(with_hdri, with_hdri.turnovers[0], with_hdri.delivery_root)
        assert made is not None and made.frame_count == 2 * FRAMES

    def test_its_event_is_cut_from_the_pre_render_and_graded(
        self, with_render: Batch, tmp_path: Path
    ) -> None:
        hdri = with_render.rows[1]
        assert hdri.hdri_render is not None and not any(q.rule_id == "QC-083" for q in hdri.qc)
        assert hdri.media is not None and hdri.media.path.suffix == ".exr", "the stem is not ambiguous"
        segment = planned(with_render).segments[1]
        assert segment.prerender and segment.path == hdri.hdri_render.path
        assert (segment.kind, segment.start, segment.length, segment.freeze) == ("source", 0, FRAMES, False)
        assert segment.color is not None and segment.color.source_encoding == "Linear Rec.709 (sRGB)"
        assert stringout._still_lut(segment, tmp_path / "hdri.cube") is not None, "graded, not as it is"

    def test_its_pre_render_is_held_on_a_frame_hold_too(self, with_render: Batch) -> None:
        """The EDL's event is an `M2` hold on the EXR; the pre-render plays, for the event's length."""
        edl = with_render.turnovers[0].edl_path
        assert edl is not None
        lines = edl.read_text().splitlines()
        second = next(i for i, line in enumerate(lines) if line.startswith("002"))
        lines.insert(second + 1, "M2   AX             000.0                00:00:00:00")
        edl.write_text("\n".join(lines) + "\n")
        segment = planned(with_render).segments[1]
        assert (segment.length, segment.freeze, segment.prerender) == (FRAMES, False, True)

    def test_the_stringout_is_written_with_it_and_it_is_no_stand_in(self, with_render: Batch) -> None:
        assert with_render.delivery_root is not None
        made = stringout.build(with_render, with_render.turnovers[0], with_render.delivery_root)
        assert made is not None and made.frame_count == 2 * FRAMES
        stand_ins = [q.message for q in with_render.turnovers[0].qc if q.rule_id == "QC-143"]
        assert not any("MELT0002" in message for message in stand_ins)

    def test_a_short_pre_render_holds_its_last_frame(self, folder: Path, tmp_path: Path) -> None:
        fixtures.make_mp4(folder / "media" / "MELT0002_pl01.mp4", count=FRAMES - 3)
        batch = self.scanned(folder, Batch(delivery_root=tmp_path / "delivery"))
        assert batch.delivery_root is not None
        made = stringout.build(batch, batch.turnovers[0], batch.delivery_root)
        assert made is not None and made.frame_count == 2 * FRAMES


class TestAPreRenderOnTheTimeline:
    """Turnover134 (2026-10-07): the timeline cuts Ben's pre-render, typed HDRI, and the
    HDRI EXR is not in the folder. Its AMF carries no grade, so the stringout shows it as
    it is (user: "If there's not color files, you can skip any color correction"), and
    nothing is delivered for it (QC-086)."""

    RENDER = "MELT0002_pl01_HDRI_01_v01.exr Render 1.mp4"

    @pytest.fixture
    def batch(self, tmp_path: Path) -> Batch:
        folder = fixtures.make_turnover(tmp_path / FOLDER, shots=1, frames=FRAMES)
        fixtures.make_mp4(folder / self.RENDER, count=FRAMES)
        rows = [("MELT0001_pl01", "MELT0001", "pl01"), (self.RENDER, "MELT0002", "HDRI")]
        fixtures.make_meta_csv(folder / "metadata.csv", rows)
        fixtures.make_final_edl(folder / "FINAL_v01.edl", ["MELT0001_pl01", self.RENDER], duration=FRAMES)
        return TestAnHdri.scanned(folder, Batch(delivery_root=tmp_path / "delivery"))

    def test_it_is_shown_as_it_is_and_nothing_is_delivered(self, batch: Batch, tmp_path: Path) -> None:
        hdri = batch.rows[1]
        assert hdri.media is None and hdri.deliverables == [] and not hdri.errors()
        assert {"QC-009", "QC-086"} <= {q.rule_id for q in hdri.qc}
        segment = planned(batch).segments[1]
        assert segment.prerender and hdri.hdri_render is not None and segment.path == hdri.hdri_render.path
        assert segment.color is None and stringout._still_lut(segment, tmp_path / "x.cube") is None

    def test_the_stringout_is_written(self, batch: Batch) -> None:
        assert batch.delivery_root is not None
        made = stringout.build(batch, batch.turnovers[0], batch.delivery_root)
        assert made is not None and made.frame_count == 2 * FRAMES


class TestAStyleFrame:
    """User, 2026-10-07: a pre-graded PNG or JPG before its shot's plate, held as it is for the
    EDL's length, burned in `SECA0009 styleFrame` with no counter, and never delivered."""

    @pytest.fixture
    def folder(self, tmp_path: Path) -> Path:
        folder = fixtures.make_turnover(
            tmp_path / FOLDER, shots=2, frames=FRAMES, shot_types=["styleFrame", "pl01"]
        )
        for path in (folder / "media").glob("MELT0001_pl01*"):
            path.unlink()
        return folder

    @pytest.fixture
    def with_style(self, folder: Path, tmp_path: Path) -> Batch:
        fixtures.make_still(folder / "media" / "MELT0001_pl01.png", size=(160, 90))
        return TestAnHdri.scanned(folder, Batch(delivery_root=tmp_path / "delivery"))

    def test_it_is_held_as_it_is_for_the_events_length(self, with_style: Batch) -> None:
        style = with_style.rows[0]
        assert qc.is_style_frame(style) and not style.deliverables
        segment = planned(with_style).segments[0]
        assert style.media is not None and segment.path == style.media.path
        assert (segment.kind, segment.length, segment.freeze, segment.style_frame) == (
            "source",
            FRAMES,
            True,
            True,
        )
        assert segment.color is None and segment.label == "MELT0001 styleFrame"

    def test_its_burn_in_has_no_frame_counter(self, tmp_path: Path) -> None:
        held = stringout.Segment(
            kind="source", length=48, freeze=True, label="X styleFrame", style_frame=True
        )
        stringout._burn_ins("so", held, tmp_path / "0000")
        texts = [path.read_text() for path in sorted(tmp_path.glob("0000_*.txt"))]
        assert not any(text.startswith("Frame:") for text in texts) and "X styleFrame" in texts

    def test_the_stringout_is_written_with_it_and_it_is_no_stand_in(self, with_style: Batch) -> None:
        assert with_style.delivery_root is not None
        reported: list[tuple[int, int]] = []
        turnover = with_style.turnovers[0]
        made = stringout.build(
            with_style, turnover, with_style.delivery_root, progress=lambda *done: reported.append(done)
        )
        assert made is not None and made.frame_count == 2 * FRAMES
        assert reported == [(FRAMES, 2 * FRAMES), (2 * FRAMES, 2 * FRAMES)]
        assert not [q for q in turnover.qc if q.rule_id in ("QC-143", "QC-144")]

    def test_its_file_missing_is_black_and_qc_144(self, folder: Path, tmp_path: Path) -> None:
        batch = TestAnHdri.scanned(folder, Batch(delivery_root=tmp_path / "delivery"))
        assert batch.delivery_root is not None
        segment = planned(batch).segments[0]
        assert (segment.kind, segment.length) == ("black", FRAMES)
        made = stringout.build(batch, batch.turnovers[0], batch.delivery_root)
        assert made is not None
        said = [(q.rule_id, q.severity) for q in batch.turnovers[0].qc]
        assert [s for s in said if s[0] in stringout.STRINGOUT_RULES] == [("QC-144", "warning")]


class TestAFileThatIsThereAlwaysPlays:
    """User, 2026-09-29: an event whose file is present is never black."""

    def test_a_file_with_no_timecode_counts_from_zero(self, batch: Batch) -> None:
        media = batch.rows[1].media
        assert media is not None
        batch.rows[1].media = replace(media, start_timecode=None)
        batch.rows[1].deliverables = []
        segment = planned(batch).segments[1]
        assert segment.kind == "source" and segment.path == media.path

    def test_a_single_image_with_no_timecode_is_its_one_frame(self) -> None:
        event = clf.ConformEvent("008", "AX", "hdri.exr", 0, 72, 100, 172, freeze=True)
        still = MediaInfo(Path("/t/hdri.exr"), "exr", "gbrpf32le", 6483, 3242, FrameRate(24), frame_count=0)
        assert stringout._cut(event, still) == InOut(0, 0)
