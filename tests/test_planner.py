"""Planning: the type table, output placement, and versioning.

Names are checked against the examples in docs/NAMING_SPEC.md sections 3 and 5. The
round-trip test is the one QC-151 will lean on: every planned name must read back as
the kind, resolution and version the planner intended.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import clf, naming, planner
from proingest.core.models import (
    Batch,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    SideFiles,
    Turnover,
)

ROOT = Path("/delivery")
SHOT_DIR = ROOT / "MELT" / "MELT0001"
RATE = FrameRate(24)


def media(
    path: str = "/turnover/MELT0001_pl01.1001.exr",
    is_sequence: bool = True,
    has_audio: bool = False,
) -> MediaInfo:
    return MediaInfo(
        path=Path(path),
        codec="exr",
        pixel_format="gbrpf32le",
        width=3840,
        height=2160,
        rate=RATE,
        frame_count=300,
        start_frame=1001,
        is_sequence=is_sequence,
        has_audio=has_audio,
    )


def row(
    clip_name: str = "MELT0001_pl01",
    audio_path: Path | None = None,
    side_files: SideFiles | None = None,
    source: str = "/turnover/MELT0001_pl01.1001.exr",
    has_audio: bool = False,
    **overrides: object,
) -> ShotRow:
    built = ShotRow(
        turnover_id="t1",
        clip_name=clip_name,
        identity=naming.parse_clip_name(clip_name),
        media=media(source, has_audio=has_audio),
        snapshot=InOut(1001, 1240),
        current=InOut(1001, 1240),
        audio_path=audio_path,
        side_files=side_files or SideFiles(),
    )
    for key, value in overrides.items():
        setattr(built, key, value)
    return built


def names(jobs: list[planner.DeliverableJob]) -> list[str]:
    return [job.name for job in jobs]


def kinds(jobs: list[planner.DeliverableJob]) -> list[str]:
    return [job.kind for job in jobs]


class TestTypeTable:
    def test_plate_delivers_two_sequences_two_refs_and_audio(self) -> None:
        plan = planner.plan_row(row(audio_path=Path("/turnover/MELT0001_pl01.wav")), ROOT, 1)
        assert names(plan.jobs) == [
            "MELT0001_pl01_raw_4k_v01",
            "MELT0001_pl01_raw_HD_v01",
            "MELT0001_pl01_ref_4k_v01.mp4",
            "MELT0001_pl01_ref_HD_v01.mp4",
            "MELT0001_pl01_audio_v01.wav",
        ]

    @pytest.mark.parametrize("elem_type", ["cp", "el", "wit", "re"])
    def test_every_other_type_delivers_the_four_picture_outputs(self, elem_type: str) -> None:
        clip = f"MELT0001_{elem_type}01"
        plan = planner.plan_row(row(clip, audio_path=Path("/turnover/audio.wav")), ROOT, 1)
        assert kinds(plan.jobs) == ["raw_dir", "raw_dir", "ref_mp4", "ref_mp4"]
        assert all(job.name.startswith(f"MELT0001_{elem_type}01_") for job in plan.jobs)

    def test_witness_cam_is_a_sequence_like_the_others(self) -> None:
        """OQ-5, confirmed by the user 2026-09-11: `wit` is a normal deliverable treated
        like any other clip, so its raw output is a sequence. The spec PDF omits its frame
        range, which reads as though it meant something; it does not.
        """
        plan = planner.plan_row(row("MELT0001_wit01"), ROOT, 1)
        assert "MELT0001_wit01_raw_4k_v01" in names(plan.jobs)

    def test_resolutions_are_exact(self) -> None:
        plan = planner.plan_row(row(), ROOT, 1)
        sizes = {job.res: job.target_size for job in plan.jobs if job.res}
        assert sizes == {"4k": (3840, 2160), "HD": (1920, 1080)}


class TestPlacement:
    def test_deliverables_land_in_the_shot_folder(self) -> None:
        plan = planner.plan_row(row(), ROOT, 1)
        assert {job.destination.parent for job in plan.jobs} == {SHOT_DIR}

    def test_temp_name_is_the_final_name_plus_part(self) -> None:
        plan = planner.plan_row(row(), ROOT, 1)
        for job in plan.jobs:
            assert job.temp == job.destination.with_name(job.name + ".part")

    def test_a_part_leftover_never_parses_as_a_delivery(self) -> None:
        plan = planner.plan_row(row(), ROOT, 1)
        assert all(naming.parse_output_name(job.temp.name) is None for job in plan.jobs)


class TestFrameRange:
    def test_picture_jobs_carry_the_current_in_out(self) -> None:
        plan = planner.plan_row(row(current=InOut(1050, 1169)), ROOT, 1)
        picture = [job for job in plan.jobs if job.kind in ("raw_dir", "ref_mp4")]
        assert all((job.in_frame, job.out_frame) == (1050, 1169) for job in picture)
        assert all(job.frame_count == 120 for job in picture)

    def test_output_frames_start_at_1001(self) -> None:
        job = planner.plan_row(row(current=InOut(1050, 1169)), ROOT, 1).jobs[0]
        assert job.frame_path(1001).name == "MELT0001_pl01_raw_4k_v01.1001.exr"
        assert job.source_frame(1001) == 1050
        assert job.source_frame(1120) == 1169

    def test_frames_are_written_into_the_temp_folder(self) -> None:
        job = planner.plan_row(row(), ROOT, 1).jobs[0]
        assert job.frame_path(1001, temp=True) == (
            SHOT_DIR / "MELT0001_pl01_raw_4k_v01.part" / "MELT0001_pl01_raw_4k_v01.1001.exr"
        )

    def test_only_a_sequence_has_frame_paths(self) -> None:
        mp4 = next(job for job in planner.plan_row(row(), ROOT, 1).jobs if job.kind == "ref_mp4")
        with pytest.raises(ValueError, match="not a sequence"):
            mp4.frame_path(1001)

    def test_a_copy_has_no_frame_range(self) -> None:
        plan = planner.plan_row(row(side_files=SideFiles(hdri=Path("/t/MELT0001_pl01_HDRI.exr"))), ROOT, 1)
        copy = next(job for job in plan.jobs if job.kind == "hdri")
        assert copy.frame_count == 0
        with pytest.raises(ValueError, match="no frame range"):
            copy.source_frame(1001)


class TestAudio:
    def test_audio_comes_from_the_associated_clip(self) -> None:
        wav = Path("/turnover/MELT0001_pl01.wav")
        plan = planner.plan_row(row(audio_path=wav), ROOT, 1)
        audio = next(job for job in plan.jobs if job.kind == "audio")
        assert audio.source == wav
        assert audio.destination == SHOT_DIR / "MELT0001_pl01_audio_v01.wav"

    def test_audio_inside_the_picture_container_is_used_when_there_is_no_clip(self) -> None:
        """COLOR_AND_FORMAT section 3: extract it rather than deliver no audio."""
        plan = planner.plan_row(row(source="/turnover/MELT0001_pl01.mov", has_audio=True), ROOT, 1)
        audio = next(job for job in plan.jobs if job.kind == "audio")
        assert audio.source == Path("/turnover/MELT0001_pl01.mov")

    def test_no_audio_anywhere_means_no_audio_job(self) -> None:
        plan = planner.plan_row(row(), ROOT, 1)
        assert "audio" not in kinds(plan.jobs)

    def test_only_the_plate_delivers_audio(self) -> None:
        plan = planner.plan_row(row("MELT0001_cp01", audio_path=Path("/t/a.wav")), ROOT, 1)
        assert "audio" not in kinds(plan.jobs)

    def test_reference_mp4s_carry_the_audio_to_mux(self) -> None:
        wav = Path("/turnover/MELT0001_pl01.wav")
        plan = planner.plan_row(row(audio_path=wav), ROOT, 1)
        for job in plan.jobs:
            assert job.audio_source == (wav if job.kind == "ref_mp4" else None)


class TestSideFiles:
    def test_hdri_and_camdata_are_copied_under_delivery_names(self) -> None:
        side = SideFiles(hdri=Path("/t/MELT0001_pl01_HDRI.exr"), camdata=Path("/t/MELT0001_pl01_camData.rtf"))
        plan = planner.plan_row(row(side_files=side), ROOT, 1)
        assert names(plan.jobs)[-2:] == [
            "MELT0001_pl01_HDRI_v01.exr",
            "MELT0001_pl01_camData_v01.rtf",
        ]

    def test_camdata_keeps_its_own_extension(self) -> None:
        plan = planner.plan_row(row(side_files=SideFiles(camdata=Path("/t/x_camData.txt"))), ROOT, 1)
        assert names(plan.jobs)[-1] == "MELT0001_pl01_camData_v01.txt"

    def test_side_files_follow_the_shot_version(self) -> None:
        side = SideFiles(hdri=Path("/t/MELT0001_pl01_HDRI.exr"))
        plan = planner.plan_row(row(side_files=side), ROOT, 7)
        assert all(job.version == 7 for job in plan.jobs)


class TestAuxStills:
    def test_reference_still_delivers_one_4k_exr(self) -> None:
        plan = planner.plan_row(row("MELT0001_pl01_colorChart_01"), ROOT, 1)
        assert names(plan.jobs) == ["MELT0001_pl01_colorChart_01_4k_v01.exr"]
        assert plan.jobs[0].res == "4k"

    @pytest.mark.parametrize("aux", naming.AUX_NAMES)
    def test_every_aux_name(self, aux: str) -> None:
        plan = planner.plan_row(row(f"MELT0001_pl01_{aux}_01"), ROOT, 1)
        assert names(plan.jobs) == [f"MELT0001_pl01_{aux}_01_4k_v01.exr"]

    def test_only_the_first_frame_of_the_clip_is_used(self) -> None:
        plan = planner.plan_row(row("MELT0001_pl01_greyBall_01", current=InOut(1005, 1030)), ROOT, 1)
        job = plan.jobs[0]
        assert (job.in_frame, job.out_frame) == (1005, 1005)
        assert job.frame_count == 1

    def test_an_aux_clip_delivers_nothing_else(self) -> None:
        side = SideFiles(hdri=Path("/t/MELT0001_pl01_HDRI.exr"))
        plan = planner.plan_row(
            row("MELT0001_pl01_sizeRef_01", side_files=side, audio_path=Path("/t/a.wav")), ROOT, 1
        )
        assert kinds(plan.jobs) == ["aux_still"]

    def test_bts_is_copied_in_its_own_format(self) -> None:
        plan = planner.plan_row(
            row("MELT0001_pl01_BTS_01", source="/turnover/MELT0001_pl01_BTS_01.jpg"), ROOT, 1
        )
        assert names(plan.jobs) == ["MELT0001_pl01_BTS_01_v01.jpg"]
        assert plan.jobs[0].kind == "bts"

    def test_bts_in_an_undeliverable_format_is_reported_not_dropped(self) -> None:
        plan = planner.plan_row(
            row("MELT0001_pl01_BTS_01", source="/turnover/MELT0001_pl01_BTS_01.tif"), ROOT, 1
        )
        assert plan.jobs == []
        assert [result.rule_id for result in plan.qc] == ["QC-056"]


class TestVersioning:
    def test_first_delivery_is_v01(self, tmp_path: Path) -> None:
        assert planner.resolve_version(tmp_path / "nothing_here") == 1
        assert planner.resolve_version(tmp_path) == 1

    def test_next_version_is_one_past_the_highest(self, tmp_path: Path) -> None:
        (tmp_path / "MELT0001_pl01_raw_4k_v01").mkdir()
        (tmp_path / "MELT0001_pl01_ref_HD_v03.mp4").touch()
        assert planner.resolve_version(tmp_path) == 4

    def test_a_part_leftover_does_not_inflate_the_version(self, tmp_path: Path) -> None:
        (tmp_path / "MELT0001_pl01_raw_4k_v01").mkdir()
        (tmp_path / "MELT0001_pl01_raw_4k_v09.part").mkdir()
        (tmp_path / "notes_v12.txt").touch()
        assert planner.resolve_version(tmp_path) == 2

    def test_every_element_of_a_shot_shares_one_version(self, tmp_path: Path) -> None:
        shot = tmp_path / "MELT" / "MELT0001"
        shot.mkdir(parents=True)
        (shot / "MELT0001_cp01_raw_4k_v01").mkdir()

        batch = Batch(rows=[row("MELT0001_pl01"), row("MELT0001_cp01")])
        jobs = planner.plan_batch(batch, tmp_path)
        assert {job.version for job in jobs} == {2}

    def test_a_different_shot_versions_independently(self, tmp_path: Path) -> None:
        shot = tmp_path / "MELT" / "MELT0001"
        shot.mkdir(parents=True)
        (shot / "MELT0001_pl01_raw_4k_v01").mkdir()

        batch = Batch(rows=[row("MELT0001_pl01"), row("MELT0002_pl01")])
        planner.plan_batch(batch, tmp_path)
        assert [job.version for job in batch.rows[0].deliverables] == [2, 2, 2, 2]
        assert [job.version for job in batch.rows[1].deliverables] == [1, 1, 1, 1]

    def test_existing_versions_are_reported_on_the_row(self, tmp_path: Path) -> None:
        shot = tmp_path / "MELT" / "MELT0001"
        shot.mkdir(parents=True)
        (shot / "MELT0001_pl01_raw_4k_v02").mkdir()

        batch = Batch(rows=[row()])
        planner.plan_batch(batch, tmp_path)
        results = [result for result in batch.rows[0].qc if result.rule_id == "QC-060"]
        assert len(results) == 1
        assert "v02" in results[0].message and "v03" in results[0].message

    def test_no_warning_on_a_first_delivery(self, tmp_path: Path) -> None:
        batch = Batch(rows=[row()])
        planner.plan_batch(batch, tmp_path)
        assert batch.rows[0].qc == []


class TestShotCodeCorrection:
    def test_a_corrected_code_renames_every_deliverable(self) -> None:
        plan = planner.plan_row(row(shot_code_override="MELT0009"), ROOT, 1)
        assert names(plan.jobs)[0] == "MELT0009_pl01_raw_4k_v01"
        assert plan.jobs[0].destination.parent == ROOT / "MELT" / "MELT0009"

    def test_the_element_still_comes_from_the_clip_name(self) -> None:
        identity = planner.effective_identity(row("MELT0001_cp02", shot_code_override="ABC1234"))
        assert identity is not None
        assert identity.shot_code == "ABC1234"
        assert identity.elem == "cp02"

    def test_a_correction_that_does_not_parse_names_nothing(self) -> None:
        assert planner.effective_identity(row(shot_code_override="melt1")) is None
        assert planner.plan_row(row(shot_code_override="melt1"), ROOT, 1).jobs == []


class TestRowsThatOweNothing:
    def test_a_skipped_row(self) -> None:
        assert planner.plan_row(row(skipped=True), ROOT, 1).jobs == []

    def test_a_row_carrying_an_error(self) -> None:
        blocked = row(qc=[QCResult("QC-023", "error", "row", "not 4k")])
        assert planner.plan_row(blocked, ROOT, 1).jobs == []

    def test_a_warning_does_not_block(self) -> None:
        warned = row(qc=[QCResult("QC-021", "warning", "row", "integer container")])
        assert len(planner.plan_row(warned, ROOT, 1).jobs) == 4

    def test_a_row_whose_clip_name_never_parsed(self) -> None:
        assert planner.plan_row(row("scene_7_take_2"), ROOT, 1).jobs == []

    def test_a_row_with_no_media(self) -> None:
        assert planner.plan_row(row(media=None), ROOT, 1).jobs == []

    def test_planning_clears_a_previous_plan_from_a_row(self, tmp_path: Path) -> None:
        batch = Batch(rows=[row()])
        planner.plan_batch(batch, tmp_path)
        assert batch.rows[0].deliverables

        batch.rows[0].skipped = True
        planner.plan_batch(batch, tmp_path)
        assert batch.rows[0].deliverables == []


class TestPlanBatch:
    def test_the_batch_delivery_root_is_used_when_none_is_passed(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, rows=[row()])
        jobs = planner.plan_batch(batch)
        assert jobs[0].destination.is_relative_to(tmp_path)

    def test_no_delivery_root_at_all_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="delivery root"):
            planner.plan_batch(Batch(rows=[row()]))

    def test_the_plan_is_recorded_on_the_row(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, rows=[row()])
        jobs = planner.plan_batch(batch)
        recorded = batch.rows[0].deliverables
        assert [item.name for item in recorded] == names(jobs)
        assert all(item.status == "planned" for item in recorded)
        assert recorded[0].frame_count == 240

    def test_a_recorded_plan_survives_the_batch_file(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, rows=[row()])
        planner.plan_batch(batch)
        restored = Batch.from_dict(batch.to_dict())
        assert restored.rows[0].deliverables == batch.rows[0].deliverables


class TestOutputNamesReadBack:
    """QC-151 in advance: what the planner writes must parse back to what it meant."""

    def test_every_planned_name_round_trips(self) -> None:
        side = SideFiles(hdri=Path("/t/MELT0001_pl01_HDRI.exr"), camdata=Path("/t/x_camData.rtf"))
        plan = planner.plan_row(
            row(audio_path=Path("/t/a.wav"), side_files=side), ROOT, 4
        )
        for job in plan.jobs:
            parsed = naming.parse_output_name(job.name)
            assert parsed is not None, job.name
            assert parsed.kind == job.kind
            assert parsed.version == job.version
            assert parsed.res == job.res
            assert parsed.shot_code == job.shot_code
            assert parsed.elem == job.elem

    def test_a_planned_frame_reads_back_as_its_sequence(self) -> None:
        job = planner.plan_row(row(), ROOT, 2).jobs[0]
        parsed = naming.parse_output_name(job.frame_path(1001).name)
        assert parsed is not None
        assert (parsed.kind, parsed.res, parsed.version, parsed.frame) == ("raw_frame", "4k", 2, 1001)

    def test_aux_names_round_trip(self) -> None:
        for clip, source in (
            ("MELT0001_pl01_mirrorBall_01", "/t/x.exr"),
            ("MELT0001_pl01_BTS_01", "/t/x.png"),
        ):
            job = planner.plan_row(row(clip, source=source), ROOT, 1).jobs[0]
            parsed = naming.parse_output_name(job.name)
            assert parsed is not None
            assert parsed.kind == job.kind


class TestShotColourOnJobs:
    """Which chain each deliverable is rendered through. COLOR_AND_FORMAT section 1.

    A job is self contained, so the colour rides on it. The one that matters here is
    the aux still: `colorChart`, `mirrorBall`, `greyBall` and `sizeRef` are the
    references a comp matches lighting against, and a creative grade applied to a
    colour chart destroys the only thing the chart is delivered for.
    """

    def ingest(self, batch: Batch, tmp_path: Path) -> None:
        """Ingest a session onto the batch's rows, which is what a run does first."""
        turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
        batch.turnovers.append(turnover)
        clf.ingest(turnover, batch.rows, self.session(tmp_path))

    def session(self, tmp_path: Path) -> clf.ColorSession:
        edl = tmp_path / "MELT_FINAL.edl"
        edl.write_text(
            "TITLE: MELT_FINAL\nFCM: NON-DROP FRAME\n\n"
            "001  MELT0001 V     C        01:00:00:00 01:00:10:00 01:00:00:00 01:00:10:00\n"
            "* FROM CLIP NAME: MELT0001_pl01.mov\n"
            "*ASC_SOP (1.020000 0.990000 1.010000)"
            "(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)\n"
            "*ASC_SAT 1.050000\n"
        )
        (tmp_path / "MELT0001_grade.clf").touch()
        return clf.load_session(edl, RATE)

    def test_a_picture_job_carries_the_session_s_clf_and_cdl(self, tmp_path: Path) -> None:
        batch = Batch(name="b", rows=[row()], delivery_root=ROOT)
        self.ingest(batch, tmp_path)
        jobs = planner.plan_batch(batch)
        picture = [job for job in jobs if job.kind in ("raw_dir", "ref_mp4")]
        assert picture
        for job in picture:
            assert job.shot_color.clf_path == tmp_path / "MELT0001_grade.clf"
            assert job.shot_color.cdl is not None

    def test_the_row_records_the_clf_for_the_qc_log(self, tmp_path: Path) -> None:
        """Ingest is what records it, and planning reads it back off the row."""
        batch = Batch(name="b", rows=[row()], delivery_root=ROOT)
        self.ingest(batch, tmp_path)
        planner.plan_batch(batch)
        assert batch.rows[0].clf_path == tmp_path / "MELT0001_grade.clf"

    def test_an_aux_still_is_never_given_the_shot_s_grade(self, tmp_path: Path) -> None:
        """It still gets the input transform, so it lands in ACEScg like every EXR."""
        aux = row("MELT0001_pl01_colorChart_01", source_encoding="ACEScc")
        batch = Batch(name="b", rows=[aux], delivery_root=ROOT)
        self.ingest(batch, tmp_path)
        jobs = planner.plan_batch(batch)
        still = next(job for job in jobs if job.kind == "aux_still")
        assert still.shot_color.clf_path is None
        assert still.shot_color.source_encoding == "ACEScc"

    def test_without_an_ingest_every_job_plans_ungraded(self) -> None:
        """The same files in the same places; the CLF is the only difference."""
        batch = Batch(name="b", rows=[row()], delivery_root=ROOT)
        jobs = planner.plan_batch(batch)
        assert all(job.shot_color == clf.DEFAULT_SHOT_COLOR for job in jobs)

    def test_the_source_encoding_reaches_every_job_from_its_own_row(self) -> None:
        """Per clip, off the row the clip's metadata was read into (M4.6.1)."""
        batch = Batch(name="b", rows=[row(source_encoding="ACEScc")], delivery_root=ROOT)
        jobs = planner.plan_batch(batch)
        assert {job.shot_color.source_encoding for job in jobs} == {"ACEScc"}

    def test_what_the_shooter_wrote_reaches_the_job_as_a_colour_space(self) -> None:
        """The table resolves it at plan time, so a worker is handed a space (M4.6.3)."""
        batch = Batch(name="b", rows=[row(source_encoding="C-Log3")], delivery_root=ROOT)
        jobs = planner.plan_batch(batch)
        assert {job.shot_color.source_encoding for job in jobs} == {"CanonLog3 CinemaGamut D55"}

    def test_a_name_that_does_not_resolve_leaves_the_job_naming_none(self) -> None:
        """`S-Log3` is four colour spaces. QC-047 reports it; the chain carries nothing."""
        batch = Batch(name="b", rows=[row(source_encoding="S-Log3")], delivery_root=ROOT)
        jobs = planner.plan_batch(batch)
        assert {job.shot_color.source_encoding for job in jobs} == {None}

    def test_where_the_name_came_from_reaches_every_job_too(self) -> None:
        """The resolved space loses the shooter's string, so the origin is what traces it."""
        scanned = row(source_encoding="C-Log3", source_encoding_origin="container tag")
        batch = Batch(name="b", rows=[scanned], delivery_root=ROOT)
        jobs = planner.plan_batch(batch)
        assert {job.shot_color.source_encoding_origin for job in jobs} == {"container tag"}

    def test_an_aux_still_carries_the_origin_as_well_as_the_encoding(self) -> None:
        """Its chain is the one the encoding is applied on, so its header states both."""
        aux = row(
            "MELT0001_pl01_colorChart_01",
            source_encoding="ACEScc",
            source_encoding_origin="clip metadata",
        )
        batch = Batch(name="b", rows=[aux], delivery_root=ROOT)
        jobs = planner.plan_batch(batch)
        still = next(job for job in jobs if job.kind == "aux_still")
        assert still.shot_color.source_encoding_origin == "clip metadata"

    def test_two_rows_may_name_two_different_encodings(self) -> None:
        """A turnover may mix encodings freely, so nothing batch wide can stand in."""
        rows = [
            row("MELT0001_pl01", source_encoding="ACEScc"),
            row("MELT0002_pl01", source_encoding="S-Log3 S-Gamut3.Cine"),
        ]
        batch = Batch(name="b", rows=rows, delivery_root=ROOT)
        jobs = planner.plan_batch(batch)
        by_shot = {job.shot_code: job.shot_color.source_encoding for job in jobs}
        assert by_shot == {"MELT0001": "ACEScc", "MELT0002": "S-Log3 S-Gamut3.Cine"}

    def test_a_row_that_plans_nothing_keeps_the_clf_it_was_ingested_with(
        self, tmp_path: Path
    ) -> None:
        """Planning no longer owns `clf_path`: a skipped row is not un-ingested."""
        skipped = row(skipped=True)
        batch = Batch(name="b", rows=[skipped], delivery_root=ROOT)
        self.ingest(batch, tmp_path)
        planner.plan_batch(batch)
        assert skipped.deliverables == []
        assert skipped.clf_path == tmp_path / "MELT0001_grade.clf"
