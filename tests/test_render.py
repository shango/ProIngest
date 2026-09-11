"""Executing one job.

The invariant every test here circles is atomicity: after `render_job` either the
destination exists complete, or it does not exist and no `.part` is left behind. A
half written sequence that looks finished is the failure this module exists to
prevent, so the failure paths get as much attention as the happy ones.

Header assertions are deliberately the same ones QC-103 to QC-105 will make in M4. A
frame is checked against the delivery spec at the point it is written, not only at the
point it is verified.
"""

from __future__ import annotations

import multiprocessing
from dataclasses import replace
from pathlib import Path

import OpenEXR
import pytest

from proingest.core import color, exr, ffmpeg, frames, media, naming, render
from proingest.core.models import Batch, Deliverable, FrameRate, ShotRow
from proingest.core.planner import DeliverableJob
from tests.fixtures import media as fixtures

FPS = FrameRate(24)
ONE_HOUR = frames.timecode_to_frames("01:00:00:00", 24.0)
SMALL = fixtures.SMALL
HALF = (SMALL[0] // 2, SMALL[1] // 2)


def sequence_job(
    source: Path,
    destination: Path,
    in_frame: int,
    out_frame: int,
    kind: str = "raw_dir",
    is_sequence: bool = True,
    start_frame: int = 1001,
    start_timecode: int | None = ONE_HOUR,
    res: str | None = None,
) -> DeliverableJob:
    """A picture job pointed at test media, with the source facts a worker needs.

    `res` is left off by default so no resample runs: the fixtures are tiny, and a job
    with a resolution set would scale them to the real 4k or HD numbers.
    """
    job = DeliverableJob(
        kind=kind,  # type: ignore[arg-type]
        source=source,
        destination=destination,
        version=1,
        shot_code="MELT0001",
        elem="pl01",
        in_frame=in_frame,
        out_frame=out_frame,
        source_is_sequence=is_sequence,
        source_size=SMALL,
        rate=FPS,
        source_start_frame=start_frame,
        source_start_timecode=start_timecode,
        res=res,  # type: ignore[arg-type]
    )
    return job


def raw_job(tmp_path: Path, count: int = 4, first: int = 1001, **kwargs: object) -> DeliverableJob:
    fixture = fixtures.make_exr_sequence(tmp_path / "src", count=count, first=first)
    destination = tmp_path / "out" / "MELT0001" / "MELT0001_pl01_raw_4k_v01"
    return sequence_job(
        fixture.path_for(first),
        destination,
        first,
        first + count - 1,
        start_frame=first,
        **kwargs,  # type: ignore[arg-type]
    )


def frame_names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


class TestRawSequence:
    def test_a_sequence_lands_with_one_frame_per_source_frame(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=4)
        deliverable = render.render_job(job)
        assert job.destination.is_dir()
        assert deliverable.frame_count == 4
        assert frame_names(job.destination) == [
            "MELT0001_pl01_raw_4k_v01.1001.exr",
            "MELT0001_pl01_raw_4k_v01.1002.exr",
            "MELT0001_pl01_raw_4k_v01.1003.exr",
            "MELT0001_pl01_raw_4k_v01.1004.exr",
        ]

    def test_output_numbering_starts_at_1001_whatever_the_source_numbering(
        self, tmp_path: Path
    ) -> None:
        job = raw_job(tmp_path, count=3, first=5000)
        render.render_job(job)
        assert frame_names(job.destination)[0].endswith(".1001.exr")

    def test_a_sub_range_delivers_only_that_range(self, tmp_path: Path) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=8, first=1001)
        job = sequence_job(
            fixture.path_for(1001),
            tmp_path / "out" / "MELT0001_pl01_raw_4k_v01",
            1003,
            1005,
        )
        deliverable = render.render_job(job)
        assert deliverable.frame_count == 3
        assert len(frame_names(job.destination)) == 3

    def test_every_frame_is_dwaa_half_with_matching_windows(self, tmp_path: Path) -> None:
        """QC-104 and QC-105, asserted where the frame is written."""
        job = raw_job(tmp_path, count=2)
        render.render_job(job)
        for path in sorted(job.destination.iterdir()):
            header = exr.read_header(path)
            assert header.compression == "DWAA_COMPRESSION"
            assert header.windows_match
            assert header.resolution == SMALL

    def test_each_frame_carries_its_own_timecode(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=3, first=1001)
        render.render_job(job)
        written = sorted(job.destination.iterdir())
        got = [exr.start_timecode_frames(path, 24.0) for path in written]
        assert got == [ONE_HOUR, ONE_HOUR + 1, ONE_HOUR + 2]

    def test_a_sub_range_timecode_counts_from_the_media_start_not_the_in_point(
        self, tmp_path: Path
    ) -> None:
        """Source TC is the media's start plus the offset into the media (section 5)."""
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=8, first=1001)
        job = sequence_job(
            fixture.path_for(1001), tmp_path / "out" / "MELT0001_pl01_raw_4k_v01", 1004, 1005
        )
        render.render_job(job)
        first = sorted(job.destination.iterdir())[0]
        assert exr.start_timecode_frames(first, 24.0) == ONE_HOUR + 3

    def test_media_with_no_timecode_writes_frames_without_one(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=2, start_timecode=None)
        render.render_job(job)
        assert exr.read_header(sorted(job.destination.iterdir())[0]).timecode is None

    def test_the_colorspace_label_reaches_the_header(self, tmp_path: Path) -> None:
        """It labels the file. Nothing here transforms the pixels either way."""
        job = raw_job(tmp_path, count=1)
        render.render_job(job, colorspace=color.SCENE_LINEAR_SRGB)
        with OpenEXR.File(str(job.frame_path(1001))) as handle:
            assert handle.header()[exr.COLORSPACE_ATTRIBUTE] == "scene_linear_sRGB"


class TestChecksums:
    def test_one_checksum_per_frame_in_output_order(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=4)
        deliverable = render.render_job(job)
        assert len(deliverable.frame_checksums) == 4
        for path, digest in zip(
            sorted(job.destination.iterdir()), deliverable.frame_checksums, strict=True
        ):
            assert render.file_digest(path) == digest

    def test_frames_of_different_content_hash_differently(self, tmp_path: Path) -> None:
        """The fixture ramps per frame, so identical hashes would mean a stuck read."""
        job = raw_job(tmp_path, count=4)
        deliverable = render.render_job(job)
        assert len(set(deliverable.frame_checksums)) == 4

    def test_size_is_the_sum_of_the_frames(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=3)
        deliverable = render.render_job(job)
        assert deliverable.size == sum(p.stat().st_size for p in job.destination.iterdir())

    def test_a_re_render_of_the_same_pixels_hashes_the_same(self, tmp_path: Path) -> None:
        """QC-106 only means anything if the encoder is deterministic. It is."""
        first = render.render_job(raw_job(tmp_path / "a", count=2))
        second = render.render_job(raw_job(tmp_path / "b", count=2))
        assert first.frame_checksums == second.frame_checksums


class TestAtomicity:
    def test_nothing_is_left_at_the_destination_when_the_source_is_short(
        self, tmp_path: Path
    ) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=3, first=1001)
        job = sequence_job(
            fixture.path_for(1001), tmp_path / "out" / "MELT0001_pl01_raw_4k_v01", 1001, 1008
        )
        with pytest.raises(render.RenderError):
            render.render_job(job)
        assert not job.destination.exists()
        assert not job.temp.exists()

    def test_a_missing_source_frame_leaves_no_part_behind(self, tmp_path: Path) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=5, first=1001)
        fixture.path_for(1003).unlink()
        job = sequence_job(
            fixture.path_for(1001), tmp_path / "out" / "MELT0001_pl01_raw_4k_v01", 1001, 1005
        )
        with pytest.raises(render.RenderError, match="missing"):
            render.render_job(job)
        assert not job.destination.exists()
        assert not job.temp.exists()

    def test_a_stale_part_from_a_previous_crash_is_replaced(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=2)
        job.temp.mkdir(parents=True)
        (job.temp / "MELT0001_pl01_raw_4k_v01.1001.exr").write_bytes(b"half written")
        render.render_job(job)
        assert len(frame_names(job.destination)) == 2
        assert not job.temp.exists()

    def test_an_occupied_destination_is_refused_rather_than_overwritten(
        self, tmp_path: Path
    ) -> None:
        job = raw_job(tmp_path, count=1)
        job.destination.mkdir(parents=True)
        with pytest.raises(render.RenderError, match="already exists"):
            render.render_job(job)

    def test_the_destination_appears_only_at_the_end(self, tmp_path: Path) -> None:
        """The temp carries the final frame names, so only the rename makes it real."""
        job = raw_job(tmp_path, count=2)
        assert job.temp.name == job.destination.name + ".part"
        render.render_job(job)
        assert job.frame_path(1001).is_file()


class TestContainerSource:
    def test_a_mov_source_delivers_the_same_frame_count(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=6)
        job = sequence_job(
            source,
            tmp_path / "out" / "MELT0001_pl01_raw_4k_v01",
            1,
            4,
            is_sequence=False,
            start_frame=0,
        )
        deliverable = render.render_job(job)
        assert deliverable.frame_count == 4
        assert len(frame_names(job.destination)) == 4

    def test_a_dpx_sequence_goes_through_ffmpeg_not_the_exr_reader(
        self, tmp_path: Path
    ) -> None:
        directory = fixtures.make_dpx_sequence(tmp_path / "src", count=5, first=1001)
        job = sequence_job(
            directory / "MELT0002_pl01.1001.dpx",
            tmp_path / "out" / "MELT0002_pl01_raw_4k_v01",
            1001,
            1003,
        )
        deliverable = render.render_job(job)
        assert deliverable.frame_count == 3

    def test_a_container_that_runs_out_leaves_nothing_behind(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=3)
        job = sequence_job(
            source,
            tmp_path / "out" / "MELT0001_pl01_raw_4k_v01",
            0,
            9,
            is_sequence=False,
            start_frame=0,
        )
        with pytest.raises(render.RenderError):
            render.render_job(job)
        assert not job.destination.exists()
        assert not job.temp.exists()


class TestResample:
    """A job with a resolution set is resampled to exactly that size, never to the
    source's. COLOR_AND_FORMAT section 4: the two delivery sizes are fixed numbers and
    are never derived from the source."""

    def test_an_exr_source_is_resampled_by_numpy(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=2, res="HD")
        render.render_job(job)
        assert exr.read_header(job.frame_path(1001)).resolution == (1920, 1080)

    def test_a_container_source_is_resampled_by_ffmpeg(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=2)
        job = sequence_job(
            source,
            tmp_path / "out" / "MELT0001_pl01_raw_HD_v01",
            0,
            1,
            is_sequence=False,
            start_frame=0,
            res="HD",
        )
        render.render_job(job)
        assert exr.read_header(job.frame_path(1001)).resolution == (1920, 1080)

    def test_no_resolution_means_the_source_size_is_kept(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=1)
        render.render_job(job)
        assert exr.read_header(job.frame_path(1001)).resolution == SMALL


class TestAuxStill:
    def test_an_aux_still_is_one_exr_file_not_a_folder(self, tmp_path: Path) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=4, first=1001)
        job = sequence_job(
            fixture.path_for(1001),
            tmp_path / "out" / "MELT0001_pl01_colorChart_01_4k_v01.exr",
            1002,
            1002,
            kind="aux_still",
        )
        deliverable = render.render_job(job)
        assert job.destination.is_file()
        assert deliverable.frame_count == 1
        assert deliverable.checksum == render.file_digest(job.destination)
        assert exr.start_timecode_frames(job.destination, 24.0) == ONE_HOUR + 1


class TestAudio:
    def test_a_wav_is_copied_byte_for_byte(self, tmp_path: Path) -> None:
        source = fixtures.make_wav(tmp_path / "src" / "plate.wav", seconds=0.25)
        job = DeliverableJob(
            kind="audio",
            source=source,
            destination=tmp_path / "out" / "MELT0001_pl01_audio_v01.wav",
            version=1,
            shot_code="MELT0001",
            elem="pl01",
        )
        deliverable = render.render_job(job)
        assert job.destination.read_bytes() == source.read_bytes()
        assert deliverable.checksum == render.file_digest(source)

    def test_audio_inside_a_container_is_extracted_as_16_bit_pcm(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=8, with_audio=True)
        job = DeliverableJob(
            kind="audio",
            source=source,
            destination=tmp_path / "out" / "MELT0001_pl01_audio_v01.wav",
            version=1,
            shot_code="MELT0001",
            elem="pl01",
        )
        render.render_job(job)
        info = media.probe_audio(job.destination)
        assert info.bit_depth == 16
        assert info.sample_rate == 48000
        assert info.channels == 2

    def test_a_source_with_no_audio_at_all_fails_and_leaves_nothing(
        self, tmp_path: Path
    ) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=4, with_audio=False)
        job = DeliverableJob(
            kind="audio",
            source=source,
            destination=tmp_path / "out" / "MELT0001_pl01_audio_v01.wav",
            version=1,
            shot_code="MELT0001",
            elem="pl01",
        )
        with pytest.raises(render.RenderError):
            render.render_job(job)
        assert not job.destination.exists()
        assert not job.temp.exists()


class TestCopies:
    @pytest.mark.parametrize(
        ("kind", "name"),
        [
            ("hdri", "MELT0001_pl01_HDRI_v01.exr"),
            ("camdata", "MELT0001_pl01_camData_v01.txt"),
            ("bts", "MELT0001_pl01_BTS_01_v01.png"),
        ],
    )
    def test_a_side_file_arrives_with_the_same_bytes_under_the_delivery_name(
        self, tmp_path: Path, kind: str, name: str
    ) -> None:
        source = tmp_path / "src" / "whatever.bin"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"camera: ARRI\nlens: 40mm\n" * 100)
        job = DeliverableJob(
            kind=kind,  # type: ignore[arg-type]
            source=source,
            destination=tmp_path / "out" / name,
            version=1,
            shot_code="MELT0001",
            elem="pl01",
        )
        deliverable = render.render_job(job)
        assert job.destination.read_bytes() == source.read_bytes()
        assert deliverable.checksum == render.file_digest(source)
        assert deliverable.status == "done"


def ref_job(
    tmp_path: Path,
    source: Path,
    in_frame: int,
    out_frame: int,
    is_sequence: bool = False,
    start_frame: int = 0,
    audio: Path | None = None,
    res: str | None = None,
) -> DeliverableJob:
    """A reference mp4 job. The destination carries the `.mp4` the name spec gives it."""
    job = sequence_job(
        source,
        tmp_path / "out" / "MELT0001_pl01_ref_4k_v01.mp4",
        in_frame,
        out_frame,
        kind="ref_mp4",
        is_sequence=is_sequence,
        start_frame=start_frame,
        res=res,
    )
    return job if audio is None else replace(job, audio_source=audio)


def streams(path: Path) -> list[dict[str, object]]:
    probed: list[dict[str, object]] = ffmpeg.probe_raw(path)["streams"]
    return probed


def video_stream(path: Path) -> dict[str, object]:
    return next(s for s in streams(path) if s["codec_type"] == "video")


class TestReferenceMp4:
    """COLOR_AND_FORMAT section 3. One ffmpeg pass, and the file has to be real.

    These assert on the encoded file rather than the command because the command is
    already pinned in test_ffmpeg; what is worth proving here is that the pieces meet.
    """

    def test_a_container_source_delivers_the_range_as_a_playable_mp4(
        self, tmp_path: Path
    ) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=8)
        job = ref_job(tmp_path, source, 0, 3)
        deliverable = render.render_job(job)
        assert job.destination.is_file()
        assert ffmpeg.count_frames(job.destination) == 4
        assert video_stream(job.destination)["codec_name"] == "h264"
        assert deliverable.status == "done"

    def test_an_exr_sequence_reference_plays_at_the_timeline_rate(
        self, tmp_path: Path
    ) -> None:
        """The image2 demuxer defaults to 25, so this is the `-framerate` trap."""
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=6, first=1001)
        job = ref_job(
            tmp_path, fixture.path_for(1001), 1001, 1004, is_sequence=True, start_frame=1001
        )
        render.render_job(job)
        assert video_stream(job.destination)["r_frame_rate"] == "24/1"
        assert ffmpeg.count_frames(job.destination) == 4

    def test_a_sub_range_delivers_only_that_range(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=8)
        job = ref_job(tmp_path, source, 2, 4)
        deliverable = render.render_job(job)
        assert ffmpeg.count_frames(job.destination) == 3
        assert deliverable.frame_count == 3

    def test_the_record_carries_a_checksum_and_a_size(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=4)
        deliverable = render.render_job(ref_job(tmp_path, source, 0, 3))
        assert deliverable.checksum
        assert deliverable.size > 0

    def test_a_resolution_scales_the_output_exactly(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=2)
        job = ref_job(tmp_path, source, 0, 1, res="HD")
        render.render_job(job)
        stream = video_stream(job.destination)
        assert (stream["width"], stream["height"]) == (1920, 1080)

    def test_associated_audio_is_muxed_as_aac(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=8)
        wav = fixtures.make_wav(tmp_path / "src" / "MELT0001_pl01.wav", seconds=8 / 24)
        job = ref_job(tmp_path, source, 0, 7, audio=wav)
        render.render_job(job)
        audio = [s for s in streams(job.destination) if s["codec_type"] == "audio"]
        assert [s["codec_name"] for s in audio] == ["aac"]

    def test_audio_in_the_source_does_not_reach_a_row_that_delivers_none(
        self, tmp_path: Path
    ) -> None:
        """`-an`, not silence. The mov's timecode track does ride along, deliberately."""
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=4, with_audio=True)
        job = ref_job(tmp_path, source, 0, 3)
        render.render_job(job)
        kinds = [s["codec_type"] for s in streams(job.destination)]
        assert "audio" not in kinds
        assert "video" in kinds

    def test_a_source_that_cannot_be_read_leaves_nothing_behind(self, tmp_path: Path) -> None:
        job = ref_job(tmp_path, tmp_path / "src" / "missing.mov", 0, 3)
        with pytest.raises(render.RenderError):
            render.render_job(job)
        assert not job.destination.exists()
        assert not job.temp.exists()

    def test_a_range_past_the_end_of_the_media_leaves_nothing_behind(
        self, tmp_path: Path
    ) -> None:
        """ffmpeg exits 0 having written fewer frames, so the count is what catches it."""
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=4)
        job = ref_job(tmp_path, source, 0, 99)
        with pytest.raises(render.RenderError):
            render.render_job(job)
        assert not job.destination.exists()
        assert not job.temp.exists()


class TestAudioAlignment:
    """OQ-27: the wav covers the clip, the picture may be a trimmed part of it."""

    def test_an_untrimmed_shot_skips_no_audio(self, tmp_path: Path) -> None:
        job = ref_job(tmp_path, tmp_path / "p.mov", 1001, 1004, start_frame=1001, audio=Path("a.wav"))
        assert render._audio_skip(job) == 0.0

    def test_a_trimmed_shot_skips_the_length_of_the_trim(self, tmp_path: Path) -> None:
        job = ref_job(tmp_path, tmp_path / "p.mov", 1013, 1016, start_frame=1001, audio=Path("a.wav"))
        assert render._audio_skip(job) == pytest.approx(0.5)

    def test_a_row_with_no_audio_has_nothing_to_skip(self, tmp_path: Path) -> None:
        job = ref_job(tmp_path, tmp_path / "p.mov", 1013, 1016, start_frame=1001)
        assert render._audio_skip(job) == 0.0


class TestSequencePaths:
    def test_a_frame_of_the_source_is_found_by_number(self, tmp_path: Path) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=4, first=1001)
        found = media.frame_path_for(fixture.path_for(1001), 1003)
        assert found == fixture.path_for(1003)
        assert found.is_file()

    def test_output_frames_start_at_the_first_output_frame(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=3)
        assert list(job.output_frames()) == [
            naming.FIRST_OUTPUT_FRAME,
            naming.FIRST_OUTPUT_FRAME + 1,
            naming.FIRST_OUTPUT_FRAME + 2,
        ]


class TestUnwritablePixels:
    def test_a_source_frame_that_will_not_read_leaves_nothing(self, tmp_path: Path) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=4, first=1001)
        fixture.path_for(1002).write_bytes(b"not an exr")
        job = sequence_job(
            fixture.path_for(1001), tmp_path / "out" / "MELT0001_pl01_raw_4k_v01", 1001, 1004
        )
        with pytest.raises(exr.ExrError):
            render.render_job(job)
        assert not job.destination.exists()
        assert not job.temp.exists()


def test_a_digest_is_stable_and_content_dependent(tmp_path: Path) -> None:
    one = tmp_path / "one.bin"
    two = tmp_path / "two.bin"
    one.write_bytes(b"x" * (render.DIGEST_CHUNK + 17))
    two.write_bytes(b"x" * (render.DIGEST_CHUNK + 17) + b"y")
    assert render.file_digest(one) == render.file_digest(one)
    assert render.file_digest(one) != render.file_digest(two)


class TestHooks:
    """The two seams the pool hangs off. Both are plain callables, so they are
    tested here without a process in sight."""

    def test_progress_counts_every_frame_in_order(self, tmp_path: Path) -> None:
        seen: list[int] = []
        render.render_job(raw_job(tmp_path, count=4), on_frame=seen.append)
        assert seen == [1, 2, 3, 4]

    def test_cancelling_before_the_start_writes_nothing_at_all(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=4)
        with pytest.raises(render.RenderCancelled, match="before it started"):
            render.render_job(job, cancelled=lambda: True)
        assert not job.destination.exists()
        assert not job.temp.exists()

    def test_cancelling_part_way_leaves_no_partial_sequence(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=6)
        written: list[int] = []

        def stop_after_two() -> bool:
            return len(written) >= 2

        with pytest.raises(render.RenderCancelled, match="after 2 frames"):
            render.render_job(job, on_frame=written.append, cancelled=stop_after_two)
        assert not job.destination.exists()
        assert not job.temp.exists()

    def test_a_cancel_check_that_stays_false_renders_normally(self, tmp_path: Path) -> None:
        job = raw_job(tmp_path, count=3)
        deliverable = render.render_job(job, cancelled=lambda: False)
        assert deliverable.status == "done"
        assert deliverable.frame_count == 3


class TestProgressMessage:
    def test_a_fraction_needs_no_guard_against_a_job_with_no_frames(self) -> None:
        assert render.Progress("copy", "done").fraction == 0.0

    def test_a_fraction_is_clamped_and_proportional(self) -> None:
        assert render.Progress("s", "frame", 5, 10).fraction == 0.5
        assert render.Progress("s", "frame", 12, 10).fraction == 1.0


class TestExecute:
    def test_every_job_comes_back_in_the_order_it_was_given(self, tmp_path: Path) -> None:
        jobs = [raw_job(tmp_path / f"j{index}", count=2) for index in range(4)]
        results = render.execute(jobs, workers=2)
        # Paths, not names: every job here delivers the same shot into its own root,
        # so the names are identical and only the path tells them apart.
        assert [d.path for d in results] == [job.destination for job in jobs]
        assert all(d.status == "done" for d in results)
        assert all(job.destination.is_dir() for job in jobs)

    def test_no_jobs_is_not_an_error_and_starts_no_pool(self) -> None:
        assert render.execute([]) == []

    def test_one_failing_job_does_not_stop_the_others(self, tmp_path: Path) -> None:
        good = raw_job(tmp_path / "good", count=2)
        broken = raw_job(tmp_path / "broken", count=2)
        broken.source.unlink()
        results = render.execute([good, broken], workers=2)
        statuses = {d.path: d.status for d in results}
        assert statuses[good.destination] == "done"
        assert statuses[broken.destination] == "failed"
        assert good.destination.is_dir()
        assert not broken.destination.exists()

    def test_a_failure_carries_qc_100_and_the_reason(self, tmp_path: Path) -> None:
        broken = raw_job(tmp_path, count=2)
        broken.source.unlink()
        failed = render.execute([broken], workers=1)[0]
        assert [result.rule_id for result in failed.qc] == [render.RENDER_FAILED]
        assert failed.qc[0].severity == "error"
        assert failed.qc[0].scope == "deliverable"
        assert broken.name in failed.qc[0].message

    def test_progress_arrives_in_the_calling_process(self, tmp_path: Path) -> None:
        seen: list[render.Progress] = []
        job = raw_job(tmp_path, count=3)
        render.execute([job], workers=1, on_progress=seen.append)
        states = [message.state for message in seen]
        assert states[0] == "started"
        assert states[-1] == "done"
        assert [m.frames_done for m in seen if m.state == "frame"] == [1, 2, 3]
        assert all(m.name == job.name for m in seen)

    def test_a_cancelled_run_writes_nothing_and_reports_skipped(self, tmp_path: Path) -> None:
        context = multiprocessing.get_context("spawn")
        cancel = context.Event()
        cancel.set()
        jobs = [raw_job(tmp_path / f"j{index}", count=2) for index in range(3)]
        results = render.execute(jobs, workers=2, cancel=cancel)
        assert {d.status for d in results} == {"skipped"}
        assert not any(job.destination.exists() for job in jobs)
        assert not any(job.temp.exists() for job in jobs)


class TestApplyResults:
    def test_executed_records_replace_the_planned_ones_on_their_row(self) -> None:
        planned = Deliverable(kind="raw_dir", name="a", path=Path("/x/a"), version=1)
        other = Deliverable(kind="audio", name="b", path=Path("/x/b"), version=1)
        row = ShotRow(turnover_id="t1", clip_name="MELT0001_pl01")
        row.deliverables = [planned, other]
        batch = Batch(name="b", rows=[row])

        done = Deliverable(kind="raw_dir", name="a", path=Path("/x/a"), version=1, status="done")
        render.apply_results(batch, [done])

        assert row.deliverables[0].status == "done"
        assert row.deliverables[1] is other

    def test_a_result_for_a_path_no_row_planned_is_ignored(self) -> None:
        planned = Deliverable(kind="raw_dir", name="a", path=Path("/x/a"), version=1)
        row = ShotRow(turnover_id="t1", clip_name="MELT0001_pl01")
        row.deliverables = [planned]
        batch = Batch(name="b", rows=[row])

        stray = Deliverable(kind="audio", name="z", path=Path("/x/z"), version=1, status="done")
        render.apply_results(batch, [stray])
        assert row.deliverables == [planned]
