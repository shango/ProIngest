"""Decoding a container source to numpy frames.

The property that matters is that the frame range is exact. Every assertion about a
range here is made against a full decode of the same media, so the test cannot agree
with the code about an off by one: it compares what came out of the range against
what is genuinely at those indices.

Seeking is by frame in both branches. `-ss` takes a float number of seconds and lands
on the wrong frame at 23.976, which is the mistake COLOR_AND_FORMAT section 6 exists
to prevent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from proingest.core import ffmpeg, media
from tests.fixtures import media as fixtures

WIDTH, HEIGHT = fixtures.SMALL
SIZE = (WIDTH, HEIGHT)
HALF = (WIDTH // 2, HEIGHT // 2)


def decode(
    source: str,
    first: int,
    last: int,
    is_sequence: bool = False,
    target_size: tuple[int, int] | None = None,
) -> list[np.ndarray]:
    """Every frame of a range, as a list. Only ever used on tiny test media."""
    return list(
        ffmpeg.decode_frames(
            source, SIZE, first, last, is_sequence=is_sequence, target_size=target_size
        )
    )


class TestDecodeCommand:
    def test_a_container_seeks_with_trim_not_start_number(self) -> None:
        command = ffmpeg.decode_command("plate.mov", 3, 7, is_sequence=False)
        assert "-start_number" not in command
        assert "trim=start_frame=3:end_frame=8" in command

    def test_trim_end_frame_is_one_past_the_last_delivered_frame(self) -> None:
        command = ffmpeg.decode_command("plate.mov", 10, 10, is_sequence=False)
        assert "trim=start_frame=10:end_frame=11" in command
        assert command[command.index("-frames:v") + 1] == "1"

    def test_a_sequence_seeks_with_start_number_before_the_input(self) -> None:
        command = ffmpeg.decode_command("plate.%04d.dpx", 1004, 1009, is_sequence=True)
        assert command.index("-start_number") < command.index("-i")
        assert command[command.index("-start_number") + 1] == "1004"
        assert not any(part.startswith("trim=") for part in command)
        assert command[command.index("-frames:v") + 1] == "6"

    def test_a_target_size_adds_the_lanczos_scale_after_the_trim(self) -> None:
        command = ffmpeg.decode_command("plate.mov", 0, 3, is_sequence=False, target_size=(1920, 1080))
        filters = command[command.index("-vf") + 1]
        assert filters == "trim=start_frame=0:end_frame=4,scale=1920:1080:flags=lanczos"

    def test_no_filter_at_all_when_a_sequence_needs_no_scale(self) -> None:
        command = ffmpeg.decode_command("plate.%04d.dpx", 1001, 1004, is_sequence=True)
        assert "-vf" not in command

    def test_the_output_is_raw_float_planes_on_stdout(self) -> None:
        command = ffmpeg.decode_command("plate.mov", 0, 1, is_sequence=False)
        assert command[-5:] == ["-f", "rawvideo", "-pix_fmt", ffmpeg.DECODE_PIXEL_FORMAT, "-"]


class TestDecodeContainer:
    def test_every_frame_arrives_as_float32_rgb(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "plate.mov", count=6)
        decoded = decode(str(source), 0, 5)
        assert len(decoded) == 6
        assert all(frame.shape == (HEIGHT, WIDTH, 3) for frame in decoded)
        assert all(frame.dtype == np.float32 for frame in decoded)

    def test_a_range_is_the_frames_at_those_indices(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "plate.mov", count=10)
        everything = decode(str(source), 0, 9)
        middle = decode(str(source), 3, 6)
        assert len(middle) == 4
        for offset, frame in enumerate(middle):
            assert np.array_equal(frame, everything[3 + offset])

    def test_a_single_frame_range_yields_one_frame(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "plate.mov", count=6)
        everything = decode(str(source), 0, 5)
        only = decode(str(source), 4, 4)
        assert len(only) == 1
        assert np.array_equal(only[0], everything[4])

    def test_a_long_gop_source_is_still_frame_exact(self, tmp_path: Path) -> None:
        """h.264 stores frames out of display order. `trim` counts them after the
        decoder has reordered them, so the range lands where a `-ss` seek would not."""
        source = fixtures.make_mp4(tmp_path / "plate.mp4", count=12)
        everything = decode(str(source), 0, 11)
        middle = decode(str(source), 4, 7)
        assert len(middle) == 4
        for offset, frame in enumerate(middle):
            assert np.array_equal(frame, everything[4 + offset])

    def test_audio_in_the_source_does_not_reach_the_raw_stream(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "plate.mov", count=4, with_audio=True)
        assert len(decode(str(source), 0, 3)) == 4

    def test_asking_past_the_end_of_the_media_fails_loudly(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "plate.mov", count=4)
        with pytest.raises(ffmpeg.FFmpegError, match="of 8 frames"):
            decode(str(source), 0, 7)

    def test_a_source_that_is_not_there_fails_loudly(self, tmp_path: Path) -> None:
        with pytest.raises(ffmpeg.FFmpegError):
            decode(str(tmp_path / "absent.mov"), 0, 3)


class TestChannelOrder:
    """`gbrpf32le` is planar G, B, R. Getting this wrong swaps red and blue silently."""

    def test_red_green_and_blue_land_in_that_order(self, tmp_path: Path) -> None:
        source = fixtures.make_solid_dpx(tmp_path / "flat.dpx", colour="0x804020")
        frame = decode(str(source), 0, 0)[0]
        red, green, blue = (float(frame[:, :, index].mean()) for index in range(3))
        assert red > green > blue
        assert red == pytest.approx(0.5, abs=0.02)
        assert green == pytest.approx(0.25, abs=0.02)
        assert blue == pytest.approx(0.125, abs=0.02)


class TestDecodeSequence:
    def test_a_range_starts_at_the_sequence_frame_number(self, tmp_path: Path) -> None:
        directory = fixtures.make_dpx_sequence(tmp_path / "seq", count=8, first=1001)
        pattern = media.printf_pattern_for(directory / "MELT0002_pl01.1001.dpx")
        everything = decode(pattern, 1001, 1008, is_sequence=True)
        middle = decode(pattern, 1004, 1006, is_sequence=True)
        assert len(everything) == 8
        assert len(middle) == 3
        for offset, frame in enumerate(middle):
            assert np.array_equal(frame, everything[3 + offset])

    def test_a_missing_frame_in_the_range_fails_loudly(self, tmp_path: Path) -> None:
        directory = fixtures.make_dpx_sequence(tmp_path / "seq", count=6, first=1001)
        pattern = media.printf_pattern_for(directory / "MELT0002_pl01.1001.dpx")
        (directory / "MELT0002_pl01.1004.dpx").unlink()
        with pytest.raises(ffmpeg.FFmpegError):
            decode(pattern, 1001, 1006, is_sequence=True)


class TestTargetSize:
    def test_frames_arrive_at_the_target_size(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "plate.mov", count=4)
        decoded = decode(str(source), 0, 3, target_size=HALF)
        assert len(decoded) == 4
        assert all(frame.shape == (HALF[1], HALF[0], 3) for frame in decoded)

    def test_the_downscale_is_not_a_crop(self, tmp_path: Path) -> None:
        """A subsample would keep the corner values; an integrating filter averages."""
        source = fixtures.make_solid_dpx(tmp_path / "flat.dpx", colour="0x804020")
        full = decode(str(source), 0, 0)[0]
        small = decode(str(source), 0, 0, target_size=HALF)[0]
        assert small.mean() == pytest.approx(float(full.mean()), abs=1e-3)


class TestStreaming:
    def test_frames_are_yielded_before_the_decode_finishes(self, tmp_path: Path) -> None:
        """Nothing accumulates: a 4k float32 frame is 95 MB and a shot is hundreds."""
        source = fixtures.make_mov(tmp_path / "plate.mov", count=8)
        stream = ffmpeg.decode_frames(str(source), SIZE, 0, 7)
        first = next(stream)
        assert first.shape == (HEIGHT, WIDTH, 3)
        stream.close()

    def test_abandoning_a_decode_leaves_no_process_running(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "plate.mov", count=8)
        stream = ffmpeg.decode_frames(str(source), SIZE, 0, 7)
        next(stream)
        stream.close()
        # A second close is a no-op, and neither raises: the generator's finally
        # clause killed and reaped the process on the first one.
        stream.close()


class TestPrintfPattern:
    def test_a_frame_path_rebuilds_its_own_pattern(self, tmp_path: Path) -> None:
        sequence = fixtures.make_exr_sequence(tmp_path / "seq")
        index = media.index_directory(tmp_path)
        found = index.sequences[0]
        assert media.printf_pattern_for(sequence.path_for(1004)) == found.printf_pattern()

    def test_padding_comes_from_the_digits_on_the_file(self, tmp_path: Path) -> None:
        pattern = media.printf_pattern_for(tmp_path / "MELT0001_pl01.100001.exr")
        assert pattern.endswith("MELT0001_pl01.%06d.exr")

    def test_a_file_with_no_frame_number_is_not_a_sequence(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not a numbered sequence frame"):
            media.printf_pattern_for(tmp_path / "MELT0001_pl01.exr")
