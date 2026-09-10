"""EXR reading and writing.

The header assertions here are the same ones QC-103, QC-104 and QC-105 will make
after a render, so a frame this writer produces is checked against the delivery spec
at the point it is written, not only at the point it is verified.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import OpenEXR
import pytest

from proingest.core import exr, frames
from tests.fixtures import media as fixtures

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
    def test_colour_space_is_stated_in_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            assert handle.header()[exr.COLORSPACE_ATTRIBUTE] == exr.COLORSPACE_VALUE

    def test_primaries_are_written(self, tmp_path: Path) -> None:
        path = tmp_path / "frame.exr"
        exr.write_frame(path, image())
        with OpenEXR.File(str(path)) as handle:
            written = handle.header()["chromaticities"]
        assert np.allclose(np.asarray(written, dtype=np.float64), exr.CHROMATICITIES, atol=1e-6)

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
            delivered, lanczos_resize(exr.read_pixels(source_path), 192, 108),
            timecode_frames=ONE_HOUR, fps=FPS,
        )

        header = exr.read_header(delivered)
        assert header.resolution == (192, 108)
        assert header.compression == "DWAA_COMPRESSION"
        assert header.pixel_type == "float16"
        assert header.timecode == "01:00:00:00"
        assert exr.read_pixels(delivered).mean() == pytest.approx(0.5, abs=0.01)
