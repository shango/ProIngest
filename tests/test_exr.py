"""EXR reading and writing.

The header assertions here are the same ones QC-103, QC-104 and QC-105 will make
after a render, so a frame this writer produces is checked against the delivery spec
at the point it is written, not only at the point it is verified.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import OpenEXR
import PyOpenColorIO as ocio
import pytest

from proingest.core import clf, color, exr, frames
from proingest.core.models import CDL
from tests.fixtures import media as fixtures

SOP_TEXT = "*ASC_SOP (1.020000 0.990000 1.010000)(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)"

FPS = 24.0
ONE_HOUR = frames.timecode_to_frames("01:00:00:00", FPS)


def image(height: int = 16, width: int = 24, channels: int = 3, value: float = 0.5) -> np.ndarray:
    return np.full((height, width, channels), value, dtype=np.float32)


class TestWriteFrame:
    def test_a_written_frame_reads_back(self, tmp_path: Path) -> None:
        path = tmp_path / "MELT0001_pl01_raw_4k_v01.1001.exr"
        exr.write_frame(path, image())
        header = exr.read_header(path)
        assert header.resolution == (24, 16)

    def test_compression_is_dwaa_at_the_specified_level(self, tmp_path: Path) -> None:
        """QC-105. DWAA at 45 is what COLOR_AND_FORMAT section 3 requires."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        assert exr.read_header(path).compression == "DWAA_COMPRESSION"
        with OpenEXR.File(str(path)) as handle:
            assert handle.header()["dwaCompressionLevel"] == exr.DWA_COMPRESSION_LEVEL

    def test_a_level_in_force_is_what_is_written(self, tmp_path: Path) -> None:
        """FR-12, Output. The Settings page may move it, M5.12, and a worker is told it."""
        was = exr.current_compression_level()
        try:
            exr.set_compression_level(60)
            path = tmp_path / "frame.exr"
            exr.write_frame(path, image())
            with OpenEXR.File(str(path)) as handle:
                assert handle.header()["dwaCompressionLevel"] == 60.0
        finally:
            exr.set_compression_level(was)

    def test_a_stated_level_wins_over_the_one_in_force(self, tmp_path: Path) -> None:
        was = exr.current_compression_level()
        try:
            exr.set_compression_level(60)
            path = tmp_path / "frame.exr"
            exr.write_frame(path, image(), compression_level=10)
            with OpenEXR.File(str(path)) as handle:
                assert handle.header()["dwaCompressionLevel"] == 10.0
        finally:
            exr.set_compression_level(was)

    def test_pixels_are_half_float(self, tmp_path: Path) -> None:
        """QC-105, and OQ-13: half, not full float."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        assert exr.read_header(path).pixel_type == "float16"

    def test_the_windows_match(self, tmp_path: Path) -> None:
        """QC-104. Nothing this writer produces has an offset data window."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(height=108, width=192))
        header = exr.read_header(path)
        assert header.windows_match
        assert header.data_window == (0, 0, 191, 107)

    def test_it_is_a_scanline_image(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            assert str(handle.header()["type"]).endswith("scanlineimage")

    def test_rgb_by_default(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(channels=3))
        assert exr.read_header(path).channels == ("R", "G", "B")

    def test_alpha_is_kept_when_the_source_has_it(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(channels=4))
        assert exr.read_header(path).channels == ("R", "G", "B", "A")

    @pytest.mark.parametrize("shape", [(16, 16), (16, 16, 1), (16, 16, 2), (16, 16, 5)])
    def test_an_unusable_channel_count_is_refused(self, tmp_path: Path, shape: tuple[int, ...]) -> None:
        with pytest.raises(ValueError, match="h, w, 3"):
            exr.write_frame(tmp_path / "frame.exr", np.zeros(shape, dtype=np.float32))

    def test_an_unwritable_path_is_an_exr_error(self, tmp_path: Path) -> None:
        with pytest.raises(exr.ExrError, match="could not write"):
            exr.write_frame(tmp_path / "no_such_folder" / "frame.exr", image())


class TestWrittenMetadata:
    def test_every_delivered_frame_states_acescg(self, tmp_path: Path) -> None:
        """The tool transforms every plate into it, so the value is not a parameter."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            assert handle.header()[exr.COLORSPACE_ATTRIBUTE] == color.PLATE_SPACE

    def test_the_source_encoding_is_named(self, tmp_path: Path) -> None:
        """Which log the frame was read as, and therefore the input transform applied."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(), shot_color=clf.ShotColor(source_encoding="ARRI LogC3 (EI800)"))
        with OpenEXR.File(str(path)) as handle:
            assert handle.header()[exr.SOURCE_ENCODING_ATTRIBUTE] == "ARRI LogC3 (EI800)"

    def test_the_origin_of_the_encoding_is_named_beside_it(self, tmp_path: Path) -> None:
        """How a wrong encoding is traced back to whoever wrote it (M4.6.5)."""
        path = tmp_path / "frame.exr"
        shot_color = clf.ShotColor(
            source_encoding="BMDFilm WideGamut Gen5", source_encoding_origin="container tag"
        )
        exr.write_frame(path, image(), shot_color=shot_color)
        with OpenEXR.File(str(path)) as handle:
            assert handle.header()[exr.SOURCE_ENCODING_ORIGIN_ATTRIBUTE] == "container tag"

    def test_an_origin_with_no_encoding_beside_it_is_not_written(self, tmp_path: Path) -> None:
        """A source for a name the header does not state would say nothing at all."""
        path = tmp_path / "frame.exr"
        shot_color = clf.ShotColor(source_encoding=None, source_encoding_origin="clip metadata")
        exr.write_frame(path, image(), shot_color=shot_color)
        with OpenEXR.File(str(path)) as handle:
            assert exr.SOURCE_ENCODING_ORIGIN_ATTRIBUTE not in handle.header()

    def test_a_clip_that_named_no_encoding_leaves_the_attribute_out(self, tmp_path: Path) -> None:
        """Absent rather than a guess. There is no default to write (M4.6.1, QC-046)."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            assert exr.SOURCE_ENCODING_ATTRIBUTE not in handle.header()

    def test_an_ungraded_frame_carries_no_clf_attributes_at_all(self, tmp_path: Path) -> None:
        """Absent rather than empty: an empty name would read as a lost filename."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            header = handle.header()
        assert exr.CLF_ATTRIBUTE not in header
        assert exr.CLF_HASH_ATTRIBUTE not in header
        assert not any(name in header for name in exr.CDL_ATTRIBUTES)

    def test_primaries_are_written(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            written = handle.header()["chromaticities"]
        assert np.allclose(np.asarray(written, dtype=np.float64), exr.CHROMATICITIES, atol=1e-6)

    def test_the_primaries_are_ap1_and_not_rec709(self, tmp_path: Path) -> None:
        """Written out rather than read off the constant: that constant is the file's

        only claim to being ACEScg, and a regression to sRGB's red at 0.64 is exactly
        the kind a test that reads the constant back cannot see.
        """
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            red_x, red_y, *_ = np.asarray(handle.header()["chromaticities"], dtype=np.float64)
        assert (red_x, red_y) == pytest.approx((0.713, 0.293), abs=1e-6)


class TestProvenance:
    """What a graded plate says was done to it. COLOR_AND_FORMAT section 1.

    A delivered EXR leaves the tool and the studio, so the header is the only record a
    facility with no colour session has. These assert the file, not the dict.
    """

    def shot_color(self, tmp_path: Path) -> clf.ShotColor:
        return clf.ShotColor(
            clf_path=tmp_path / "MELT0001_grade.clf",
            cdl=CDL(
                slope=(1.02, 0.99, 1.01),
                offset=(0.001, -0.002, 0.0),
                power=(0.98, 1.0, 1.02),
                saturation=1.05,
                sop_text=SOP_TEXT,
                sat_text="*ASC_SAT 1.050000",
            ),
        )

    def written(self, tmp_path: Path) -> dict[str, object]:
        shot_color = self.shot_color(tmp_path)
        path_to_clf = shot_color.clf_path or Path()
        loaded = clf.LoadedClf(
            path=path_to_clf,
            digest="abc123",
            transform=ocio.FileTransform(src=str(path_to_clf)),
            is_grade_only=True,
        )
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(), shot_color=shot_color, loaded_clf=loaded)
        with OpenEXR.File(str(path)) as handle:
            return dict(handle.header())

    def test_the_clf_is_named_and_hashed(self, tmp_path: Path) -> None:
        """The hash identifies the grade: a re-exported CLF gets a new one."""
        header = self.written(tmp_path)
        assert header[exr.CLF_ATTRIBUTE] == "MELT0001_grade.clf"
        assert header[exr.CLF_HASH_ATTRIBUTE] == "abc123"

    def test_the_cdl_goes_in_as_numbers(self, tmp_path: Path) -> None:
        header = self.written(tmp_path)
        slope, offset, power, saturation, _, _, _ = exr.CDL_ATTRIBUTES
        assert np.allclose(np.asarray(header[slope]), (1.02, 0.99, 1.01), atol=1e-6)
        assert np.allclose(np.asarray(header[offset]), (0.001, -0.002, 0.0), atol=1e-6)
        assert np.allclose(np.asarray(header[power]), (0.98, 1.0, 1.02), atol=1e-6)
        assert header[saturation] == pytest.approx(1.05)

    def test_the_cdl_also_goes_in_verbatim(self, tmp_path: Path) -> None:
        """The original lines, because that is what another facility's tool reads."""
        header = self.written(tmp_path)
        _, _, _, _, sop, sat, _ = exr.CDL_ATTRIBUTES
        assert str(header[sop]).startswith("*ASC_SOP (1.020000")
        assert header[sat] == "*ASC_SAT 1.050000"

    def test_with_a_cube_the_header_says_the_cdl_was_not_the_thing_applied(self, tmp_path: Path) -> None:
        """Two grade artifacts in one header is only safe if the file says which is which."""
        header = self.written(tmp_path)
        assert header[exr.CDL_ATTRIBUTES[-1]] == exr.CDL_NOTE_RECORD
        assert exr.CLF_ATTRIBUTE in exr.CDL_NOTE_RECORD

    def test_without_a_cube_the_header_says_the_cdl_was_applied_and_where(self, tmp_path: Path) -> None:
        shot_color = dataclasses.replace(self.shot_color(tmp_path), clf_path=None)
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(), shot_color=shot_color)
        with OpenEXR.File(str(path)) as handle:
            header = dict(handle.header())
        assert header[exr.CDL_ATTRIBUTES[-1]] == exr.CDL_NOTE_APPLIED
        assert color.WORKING_SPACE in exr.CDL_NOTE_APPLIED
        assert exr.CLF_ATTRIBUTE not in header

    def test_a_frame_carries_its_own_timecode(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(), timecode_frames=ONE_HOUR + 12, fps=FPS)
        assert exr.read_header(path).timecode == "01:00:00:12"

    def test_timecode_round_trips_through_the_reader(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(), timecode_frames=ONE_HOUR, fps=FPS)
        assert exr.start_timecode_frames(path, FPS) == ONE_HOUR

    def test_no_timecode_is_written_when_the_source_had_none(self, tmp_path: Path) -> None:
        """QC-028 says a source without timecode is a warning, not an invention."""
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        assert exr.read_header(path).timecode is None


class TestReadPixels:
    def test_reads_what_was_written(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        row = np.linspace(0.0, 4.0, 24, dtype=np.float32)
        source = np.repeat(np.tile(row, (16, 1))[:, :, None], 3, axis=2)
        exr.write_frame(path, source)
        read = exr.read_pixels(path)
        assert read.shape == (16, 24, 3)
        assert read.dtype == np.float32
        assert np.allclose(read, source, rtol=0.01, atol=0.002)

    def test_scene_linear_highlights_survive_the_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(value=64.0))
        assert exr.read_pixels(path).max() == pytest.approx(64.0, rel=1e-2)

    def test_alpha_comes_back(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image(channels=4))
        assert exr.read_pixels(path).shape[2] == 4

    def test_reads_a_sequence_written_by_the_fixture(self, tmp_path: Path) -> None:
        """The fixture writes ZIP, not DWAA, so this also covers a foreign compression."""
        sequence = fixtures.make_exr_sequence(tmp_path, count=2)
        pixels = exr.read_pixels(sequence.path_for(sequence.first))
        assert pixels.shape == (sequence.height, sequence.width, 3)

    def test_a_missing_file_is_an_exr_error(self, tmp_path: Path) -> None:
        with pytest.raises(exr.ExrError, match="could not read pixels"):
            exr.read_pixels(tmp_path / "absent.exr")

    def test_a_file_without_colour_channels_is_an_exr_error(self, tmp_path: Path) -> None:
        path = tmp_path / "depth.exr"
        OpenEXR.File({}, {"Z": np.zeros((8, 8), dtype=np.float32)}).write(str(path))
        with pytest.raises(exr.ExrError, match="no RGB channels"):
            exr.read_pixels(path)

    def test_separate_channels_are_stacked(self, tmp_path: Path) -> None:
        path = tmp_path / "split.exr"
        plane = np.full((8, 8), 0.25, dtype=np.float32)
        OpenEXR.File({}, {"R": plane, "G": plane * 2, "B": plane * 3}).write(str(path))
        pixels = exr.read_pixels(path)
        assert pixels.shape == (8, 8, 3)
        assert pixels[0, 0].tolist() == pytest.approx([0.25, 0.5, 0.75])


class TestDwaaIsLossy:
    """DWAA is a lossy codec, so a raw deliverable is not bit-identical to its source.

    COLOR_AND_FORMAT section 3 requires DWAA at 45 anyway, and section 1's "pixels in,
    pixels out" means no colour transform is applied, not that the file is a byte copy.
    The error is relative, around a tenth of a percent, so QC cannot compare a rendered
    frame to its source by equality. QC-106 hashes the written file instead, which is
    sound because the encoder is deterministic.
    """

    def test_error_stays_near_a_tenth_of_a_percent(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        for value in (0.5, 64.0):
            exr.write_frame(path, image(value=value))
            error = abs(float(exr.read_pixels(path).mean()) - value)
            assert error <= value * 0.002, f"{value} came back off by {error}"

    def test_the_same_pixels_produce_the_same_bytes(self, tmp_path: Path) -> None:
        """QC-106 records a hash per frame, so a re-render has to be reproducible."""
        first, second = tmp_path / "a.exr", tmp_path / "b.exr"
        source = image(height=32, width=32)
        exr.write_frame(first, source, timecode_frames=ONE_HOUR, fps=FPS)
        exr.write_frame(second, source, timecode_frames=ONE_HOUR, fps=FPS)
        assert first.read_bytes() == second.read_bytes()


class TestDeliveryFrame:
    """A source frame becoming a delivered frame, which is what M3 does per frame."""

    def test_four_k_source_to_hd_delivery(self, tmp_path: Path) -> None:
        from proingest.core.resize import lanczos_resize

        source_path = tmp_path / "source.exr"
        exr.write_frame(source_path, image(height=216, width=384))

        delivered = tmp_path / "MELT0001_pl01_raw_HD_v01.1001.exr"
        exr.write_frame(
            delivered,
            lanczos_resize(exr.read_pixels(source_path), 192, 108),
            timecode_frames=ONE_HOUR,
            fps=FPS,
        )

        header = exr.read_header(delivered)
        assert header.resolution == (192, 108)
        assert header.compression == "DWAA_COMPRESSION"
        assert header.pixel_type == "float16"
        assert header.timecode == "01:00:00:00"
        assert exr.read_pixels(delivered).mean() == pytest.approx(0.5, abs=0.01)
