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

import numpy as np
import numpy.typing as npt
import OpenEXR
import pytest

from proingest.core import batchfile, clf, color, exr, ffmpeg, frames, media, naming, qc, render
from proingest.core.models import Batch, Deliverable, FrameRate, QCResult, ShotRow
from proingest.core.planner import DeliverableJob
from tests.fixtures import color as color_fixtures
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
    shot_color: clf.ShotColor = color_fixtures.UNGRADED,
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
        shot_color=shot_color,
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


def ids(results: list[QCResult]) -> list[str]:
    return [result.rule_id for result in results]



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

    def test_every_delivered_frame_states_acescg(self, tmp_path: Path) -> None:
        """The plate branch put it there, so the label is a fact rather than a setting."""
        job = raw_job(tmp_path, count=1)
        render.render_job(job)
        with OpenEXR.File(str(job.frame_path(1001))) as handle:
            assert handle.header()[exr.COLORSPACE_ATTRIBUTE] == color.PLATE_SPACE


class TestPlateBranch:
    """The colour the plate is delivered in. COLOR_AND_FORMAT section 1.

    The fixture writes a flat 0.2 into red, which is a code value in the source's log
    encoding and not a scene linear one. What lands in the EXR is what the chain makes
    of it, and the number is far enough from 0.2 that a chain that never ran shows up.
    """

    SOURCE_PIXEL = (0.2, 0.0, 0.0)
    """What the fixture writes on the first of four frames: red is `1 / (4 + 1)`.

    The whole triple, not just red: the session's CLF carries a saturation, which mixes
    channels, so red out of a red-only pixel is not red out of a neutral one.
    """

    def delivered(
        self, tmp_path: Path, shot_color: clf.ShotColor = color_fixtures.UNGRADED
    ) -> npt.NDArray[np.float32]:
        job = raw_job(tmp_path, count=4, shot_color=shot_color)
        render.render_job(job)
        return exr.read_pixels(job.frame_path(1001))

    def expected(self, shot_color: clf.ShotColor) -> float:
        """The source pixel through the same chain, asked of OCIO rather than typed out."""
        pixels = np.array([[list(self.SOURCE_PIXEL)]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.plate_transforms(shot_color.load())))
        return float(pixels[0, 0, 0])

    def test_the_source_is_transformed_and_not_passed_through(self, tmp_path: Path) -> None:
        red = float(self.delivered(tmp_path)[0, 0, 0])
        assert red == pytest.approx(self.expected(color_fixtures.UNGRADED), abs=0.002)
        assert red != pytest.approx(self.SOURCE_PIXEL[0], abs=0.01)

    def test_the_shot_s_clf_is_what_is_applied(self, tmp_path: Path) -> None:
        """A different grade has to give a different plate, or nothing was applied."""
        graded = clf.ShotColor(
            source_encoding=color_fixtures.SOURCE_ENCODING,
            clf_path=color_fixtures.plate_clf(tmp_path / "MELT0001.clf"),
        )
        with_clf = self.delivered(tmp_path / "graded", shot_color=graded)
        without = self.delivered(tmp_path / "plain")
        assert float(with_clf[0, 0, 0]) != pytest.approx(float(without[0, 0, 0]), abs=0.002)
        assert float(with_clf[0, 0, 0]) == pytest.approx(self.expected(graded), abs=0.002)

    def test_the_header_names_the_clf_that_was_applied(self, tmp_path: Path) -> None:
        """The header and the pixels come from the one `LoadedClf`, so they cannot differ."""
        path = color_fixtures.plate_clf(tmp_path / "MELT0001_grade.clf")
        shot_color = clf.ShotColor(
            source_encoding=color_fixtures.SOURCE_ENCODING, clf_path=path
        )
        job = raw_job(tmp_path, count=1, shot_color=shot_color)
        render.render_job(job)
        with OpenEXR.File(str(job.frame_path(1001))) as handle:
            # Copied rather than held: the mapping the bindings hand back empties when
            # the file closes, and an assertion on it outside the block passes on nothing.
            header = dict(handle.header())
        assert header[exr.CLF_ATTRIBUTE] == "MELT0001_grade.clf"
        assert header[exr.CLF_HASH_ATTRIBUTE] == clf.clf_digest(path)
        assert header[exr.SOURCE_ENCODING_ATTRIBUTE] == color_fixtures.SOURCE_ENCODING

    def test_alpha_does_not_go_through_the_chain(self) -> None:
        """Coverage is not colour, and a transformed alpha only shows up over a comp."""
        branch = render._plate_branch(DeliverableJob(
            kind="raw_dir", source=Path("x"), destination=Path("y"), version=1,
            shot_code="MELT0001", elem="pl01", shot_color=color_fixtures.UNGRADED,
        ))
        pixels = np.full((2, 2, 4), 0.5, dtype=np.float32)
        pixels[:, :, 3] = 0.25
        out = branch.apply(pixels)
        assert out.shape == (2, 2, 4)
        assert np.all(out[:, :, 3] == 0.25)
        assert not np.any(out[:, :, :3] == 0.5)


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

    def test_one_whose_clip_named_no_encoding_is_refused_rather_than_converted(
        self, tmp_path: Path
    ) -> None:
        """QC-046's claim, end to end: the deliverable is blocked rather than approximated.

        A mis-converted colour chart still looks exactly like a chart, so a still with
        nothing to convert it by is worth failing. Nothing is left behind, like every
        other failure here.
        """
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=1, first=1001)
        job = sequence_job(
            fixture.path_for(1001),
            tmp_path / "out" / "MELT0001_pl01_colorChart_01_4k_v01.exr",
            1001,
            1001,
            kind="aux_still",
            shot_color=clf.DEFAULT_SHOT_COLOR,
        )
        with pytest.raises(clf.ClfError, match="no source encoding"):
            render.render_job(job)
        assert not job.destination.exists()
        assert not list(job.destination.parent.glob("*.part"))
        assert ids(render._worker(job).qc) == [render.RENDER_FAILED]


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


class TestViewBranch:
    """The reference's colour, which reaches ffmpeg as a baked cube (section 1).

    What these guard is the join: the cube has to exist, be a real LUT and be named in
    the command **while ffmpeg runs**, and be gone afterwards. A missing cube is an
    ffmpeg error nobody would misread; a stale one is a reference that silently carries
    the wrong look.
    """

    def captured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        """Render a reference with the encode stubbed, keeping what it was handed."""
        seen: dict[str, object] = {}

        def fake_encode(*args: object, **kwargs: object) -> None:
            cube = kwargs["lut"]
            assert isinstance(cube, Path)
            seen["path"] = cube
            seen["text"] = cube.read_text()
            Path(str(args[1])).write_bytes(b"")  # the `.part` the real encode would write

        monkeypatch.setattr(ffmpeg, "encode_reference", fake_encode)
        monkeypatch.setattr(ffmpeg, "container_frame_count", lambda path: 4)
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=8)
        render.render_job(ref_job(tmp_path, source, 0, 3))
        return seen

    def test_the_encode_is_handed_a_real_cube(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self.captured(tmp_path, monkeypatch)
        text = str(seen["text"])
        assert text.startswith(f"LUT_3D_SIZE {color.LUT_SIZE}")
        assert len(text.splitlines()) == color.LUT_SIZE**3 + 1

    def test_the_cube_is_named_after_the_deliverable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ffmpeg command is logged verbatim, so the name has to say which shot."""
        cube = self.captured(tmp_path, monkeypatch)["path"]
        assert isinstance(cube, Path)
        assert cube.name == f"MELT0001_pl01_ref_4k_v01{render.LUT_SUFFIX}"

    def test_nothing_is_left_behind_once_the_encode_is_over(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The cube is not a deliverable, and it is not written to the delivery root."""
        cube = self.captured(tmp_path, monkeypatch)["path"]
        assert isinstance(cube, Path)
        assert not cube.exists()
        assert not cube.parent.exists()
        assert render.LUT_SUFFIX not in [path.suffix for path in (tmp_path / "out").iterdir()]

    def test_the_delivered_reference_is_not_the_raw_log(self, tmp_path: Path) -> None:
        """End to end through the real ffmpeg: the view branch has to change the picture.

        A reference encoded with no transform is the failure M3 shipped with, and it
        looks flat and milky rather than broken, so the check is against an encode of
        the same frames with no LUT at all.
        """
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=4)
        job = ref_job(tmp_path, source, 0, 3)
        render.render_job(job)
        plain = tmp_path / "plain.mp4"
        ffmpeg.encode_reference(str(source), plain, 0, 3, is_sequence=False, rate="24/1")
        assert render.file_digest(job.destination) != render.file_digest(plain)


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

    def test_audio_shorter_than_the_picture_does_not_truncate_it(self, tmp_path: Path) -> None:
        """OQ-27: the wav is cut to cut, so extending Out into the handles outruns it.

        The picture is what the deliverable is, so it wins and the audio is padded with
        silence. Before the pad existed a short wav cut the picture down with it: 24
        frames asked for, 12 delivered.
        """
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=24)
        wav = fixtures.make_wav(tmp_path / "src" / "short.wav", seconds=0.5)
        job = ref_job(tmp_path, source, 0, 23, audio=wav)
        deliverable = render.render_job(job)
        assert ffmpeg.count_frames(job.destination) == 24
        assert deliverable.frame_count == 24

    def test_audio_longer_than_the_picture_is_still_cut_to_it(self, tmp_path: Path) -> None:
        """Padding the audio must not stop a wav that overruns being cut back.

        This is the test that caught `-shortest` letting audio buffer ahead of the
        `lut3d` filtergraph: on ffmpeg 9.0.1 it delivered 0.98 seconds of sound against
        a third of a second of picture, and only the macOS runner saw it.
        """
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=8)
        wav = fixtures.make_wav(tmp_path / "src" / "long.wav", seconds=5.0)
        job = ref_job(tmp_path, source, 0, 7, audio=wav)
        render.render_job(job)
        video = video_stream(job.destination)
        audio = next(s for s in streams(job.destination) if s["codec_type"] == "audio")
        assert float(str(audio["duration"])) <= float(str(video["duration"])) + 0.05

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


class TestPostRenderQC:
    """Phase B runs inside `render_job`, immediately after the atomic rename."""

    def test_a_clean_render_carries_no_qc_results(self, tmp_path: Path) -> None:
        deliverable = render.render_job(raw_job(tmp_path, count=3))
        assert deliverable.status == "done"
        assert deliverable.qc == []

    def test_a_failed_check_marks_the_deliverable_and_keeps_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """QC_RULES phase B: a file that failed a check is evidence, so it stays."""
        job = raw_job(tmp_path, count=2)
        monkeypatch.setattr(
            qc,
            "run_phase_b",
            lambda _job, _deliverable: [QCResult("QC-105", "error", "deliverable", "wrong")],
        )
        deliverable = render.render_job(job)

        assert deliverable.status == "failed"
        assert job.destination.is_dir(), "the file stays for inspection"
        marker = job.destination.with_name(job.destination.name + batchfile.FAILED_MARKER)
        assert marker.is_file()
        assert "QC-105" in marker.read_text()

    def test_the_marker_is_what_a_reopened_batch_reads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A crash after the check still reopens as failed rather than as done."""
        job = raw_job(tmp_path, count=2)
        monkeypatch.setattr(
            qc,
            "run_phase_b",
            lambda _job, _deliverable: [QCResult("QC-106", "error", "deliverable", "changed")],
        )
        deliverable = render.render_job(job)
        deliverable.status = "done"  # as a stale batch file would have it
        batch = Batch(rows=[ShotRow(turnover_id="t1", clip_name="x", deliverables=[deliverable])])
        batchfile.reconcile_with_filesystem(batch)
        assert batch.rows[0].deliverables[0].status == "failed"

    def test_a_warning_alone_does_not_fail_the_deliverable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = raw_job(tmp_path, count=2)
        monkeypatch.setattr(
            qc,
            "run_phase_b",
            lambda _job, _deliverable: [QCResult("QC-107", "warning", "deliverable", "dark")],
        )
        deliverable = render.render_job(job)
        assert deliverable.status == "done"
        assert ids(deliverable.qc) == ["QC-107"]

    def test_apply_results_runs_the_row_and_batch_rules(self, tmp_path: Path) -> None:
        """QC-150 and QC-151 cannot run in a worker: one sees a job, not a batch."""
        job = raw_job(tmp_path, count=2)
        deliverable = render.render_job(job)
        deliverable.name = "nonsense"
        row = ShotRow(turnover_id="t1", clip_name="x", deliverables=[job.to_deliverable()])
        batch = Batch(rows=[row])
        render.apply_results(batch, [deliverable])
        assert "QC-151" in ids(batch.qc)

    def test_apply_results_reparses_under_the_pattern_the_names_were_planned_with(
        self, tmp_path: Path
    ) -> None:
        """A custom show pattern names the deliverables; QC-151 must read them with it too."""
        job = raw_job(tmp_path, count=2)
        deliverable = render.render_job(job)
        deliverable.name = "mx0001_pl01_raw_4k_v01"
        row = ShotRow(turnover_id="t1", clip_name="x", deliverables=[job.to_deliverable()])
        batch = Batch(rows=[row])
        render.apply_results(batch, [deliverable], show_pattern="[a-z]{2}")
        assert "QC-151" not in ids(batch.qc)
