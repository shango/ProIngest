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

import subprocess
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
        ffmpeg.decode_frames(source, SIZE, first, last, is_sequence=is_sequence, target_size=target_size)
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


class TestExtractAudio:
    def test_the_format_is_stated_because_the_output_is_a_part_path(self) -> None:
        """A `.part` name tells ffmpeg nothing, so the muxer has to be named outright.

        Without this ffmpeg refuses the output with "Unable to choose an output
        format", which every deliverable written through ffmpeg would hit.
        """
        command = ffmpeg.extract_audio_command(Path("plate.mov"), Path("MELT0001_pl01_audio_v01.wav.part"))
        assert command[command.index("-f") + 1] == "wav"

    def test_nothing_resamples_or_remixes(self) -> None:
        command = ffmpeg.extract_audio_command(Path("plate.mov"), Path("out.wav.part"))
        assert "-ar" not in command
        assert "-ac" not in command
        assert command[command.index("-c:a") + 1] == "pcm_s16le"


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


class TestEncodeCommand:
    """The reference encode's argv. COLOR_AND_FORMAT section 3.

    Three of these pin traps that produce a plausible file rather than an error, which
    is why they are asserted on the command rather than left to an eye on the output.
    """

    def test_a_sequence_states_its_rate_because_image2_would_invent_25(self) -> None:
        """No `-framerate` and every sequence reference plays 4% fast, silently."""
        command = ffmpeg.encode_command(
            "plate.%04d.exr", Path("out.mp4.part"), 1001, 1004, is_sequence=True, rate="24/1"
        )
        assert command.index("-framerate") < command.index("-i")
        assert command[command.index("-framerate") + 1] == "24/1"
        assert command[command.index("-start_number") + 1] == "1001"

    def test_the_rate_is_exact_rather_than_rounded(self) -> None:
        """23.976 is 24000/1001, and a decimal there would drift against the timecode."""
        command = ffmpeg.encode_command(
            "plate.%04d.exr", Path("out.mp4.part"), 1001, 1004, is_sequence=True, rate="24000/1001"
        )
        assert command[command.index("-framerate") + 1] == "24000/1001"

    def test_a_container_trims_by_frame_and_rebases_the_timestamps(self) -> None:
        """Without setpts the mp4 opens with a gap as long as the trim offset."""
        command = ffmpeg.encode_command(
            "plate.mov", Path("out.mp4.part"), 2, 5, is_sequence=False, rate="24/1"
        )
        filters = command[command.index("-vf") + 1]
        assert filters == "trim=start_frame=2:end_frame=6,setpts=PTS-STARTPTS"
        assert "-framerate" not in command
        assert command[command.index("-frames:v") + 1] == "4"

    def test_the_format_is_stated_because_the_output_is_a_part_path(self) -> None:
        command = ffmpeg.encode_command(
            "plate.mov",
            Path("MELT0001_pl01_ref_4k_v01.mp4.part"),
            0,
            3,
            is_sequence=False,
            rate="24/1",
        )
        assert command[-3:] == ["-f", "mp4", "MELT0001_pl01_ref_4k_v01.mp4.part"]

    def test_the_encode_is_the_one_the_spec_pins(self) -> None:
        command = ffmpeg.encode_command(
            "plate.mov", Path("out.mp4.part"), 0, 3, is_sequence=False, rate="24/1"
        )
        assert command[command.index("-c:v") + 1] == "libx264"
        assert command[command.index("-profile:v") + 1] == "high"
        assert command[command.index("-crf") + 1] == "18"
        assert command[command.index("-preset") + 1] == "slow"
        assert command[command.index("-g") + 1] == "24"
        assert command[command.index("-pix_fmt") + 1] == "yuv420p"
        assert command[command.index("-movflags") + 1] == "+faststart"

    def test_the_output_is_tagged_bt709_with_an_srgb_transfer(self) -> None:
        """Section 1: both colour branches land here, so the tags never vary."""
        command = ffmpeg.encode_command(
            "plate.mov", Path("out.mp4.part"), 0, 3, is_sequence=False, rate="24/1"
        )
        assert command[command.index("-color_primaries") + 1] == "bt709"
        assert command[command.index("-colorspace") + 1] == "bt709"
        assert command[command.index("-color_trc") + 1] == "iec61966-2-1"

    def test_the_lut_runs_after_the_scale(self) -> None:
        """Section 1: the downscale runs on the log values, which are bounded 0..1.

        swscale clamps float to that range, so the order is what keeps the reference a
        single pass: everything unbounded is inside the cube.
        """
        command = ffmpeg.encode_command(
            "plate.mov",
            Path("out.mp4.part"),
            0,
            3,
            is_sequence=False,
            rate="24/1",
            target_size=(1920, 1080),
            lut=Path("/tmp/lut/MELT0001_ref_HD_v01.cube"),
        )
        filters = command[command.index("-vf") + 1].split(",")
        assert filters[-3:] == [
            "scale=1920:1080:flags=lanczos",
            "format=gbrpf32le",
            "lut3d=/tmp/lut/MELT0001_ref_HD_v01.cube:interp=tetrahedral",
        ]

    def test_the_lut_is_applied_tetrahedrally(self) -> None:
        """`lut3d` defaults to it. Stated anyway: trilinear is one word and looks wrong."""
        assert "interp=tetrahedral" in ffmpeg.lut_filter(Path("/tmp/a.cube"))

    def test_a_colon_in_the_lut_path_is_escaped_not_pasted(self) -> None:
        """A filter argument is colon separated, so an unescaped path ends the filter."""
        assert ffmpeg.lut_filter(Path("/tmp/a:b/lut.cube")).endswith(
            "lut3d=/tmp/a\\:b/lut.cube:interp=tetrahedral"
        )

    def test_no_lut_means_no_filter_at_all(self) -> None:
        """`encode_command` still has to build a command without one, for the tests above."""
        command = ffmpeg.encode_command(
            "plate.%04d.exr", Path("out.mp4.part"), 1001, 1004, is_sequence=True, rate="24/1"
        )
        assert "-vf" not in command

    def test_no_audio_means_the_stream_is_dropped_not_silent(self) -> None:
        command = ffmpeg.encode_command(
            "plate.mov", Path("out.mp4.part"), 0, 3, is_sequence=False, rate="24/1"
        )
        assert "-an" in command
        assert "aac" not in command
        assert command.count("-i") == 1

    def test_audio_is_a_second_input_mapped_and_encoded_at_192k(self) -> None:
        command = ffmpeg.encode_command(
            "plate.mov",
            Path("out.mp4.part"),
            0,
            3,
            is_sequence=False,
            rate="24/1",
            audio=Path("MELT0001_pl01.wav"),
        )
        assert command.count("-i") == 2
        assert "-map" in command
        assert command[command.index("0:v:0") - 1] == "-map"
        assert command[command.index("1:a:0") - 1] == "-map"
        assert command[command.index("-c:a") + 1] == "aac"
        assert command[command.index("-b:a") + 1] == "192k"

    def test_the_audio_is_padded_and_then_cut_to_the_picture(self) -> None:
        """`apad` and `atrim` are one idiom and neither half is about the other stream.

        The pad covers a wav shorter than the delivered range, which OQ-27 makes
        reachable whenever the editor extends Out into the handles; the trim covers one
        that overruns. Stated outright rather than left to `-shortest`, which lets audio
        buffer ahead of a video stream still inside a filtergraph by a margin that
        varies with the ffmpeg version.
        """
        command = ffmpeg.encode_command(
            "plate.mov",
            Path("out.mp4.part"),
            0,
            3,
            is_sequence=False,
            rate="24/1",
            audio=Path("a.wav"),
        )
        assert command[command.index("-af") + 1] == "apad,atrim=duration=0.166667"
        assert "-shortest" not in command

    def test_the_audio_length_is_exact_at_a_fractional_rate(self) -> None:
        """24 frames at 23.976 is 1.001 seconds, not 1.0: the rate stays a fraction."""
        command = ffmpeg.encode_command(
            "plate.mov",
            Path("out.mp4.part"),
            0,
            23,
            is_sequence=False,
            rate="24000/1001",
            audio=Path("a.wav"),
        )
        assert command[command.index("-af") + 1].endswith("atrim=duration=1.001000")

    def test_an_audio_skip_seeks_the_audio_input_and_not_the_picture(self) -> None:
        """-ss binds to the input that follows it, so its position is the whole point."""
        command = ffmpeg.encode_command(
            "plate.mov",
            Path("out.mp4.part"),
            0,
            3,
            is_sequence=False,
            rate="24/1",
            audio=Path("a.wav"),
            audio_skip=0.5,
        )
        assert command[command.index("-ss") + 1] == "0.500000"
        assert command[command.index("-ss") + 2] == "-i"
        assert command[command.index("-ss") + 3] == "a.wav"
        assert command.index("-ss") > command.index("plate.mov")

    def test_an_untrimmed_shot_seeks_the_audio_not_at_all(self) -> None:
        command = ffmpeg.encode_command(
            "plate.mov",
            Path("out.mp4.part"),
            0,
            3,
            is_sequence=False,
            rate="24/1",
            audio=Path("a.wav"),
        )
        assert "-ss" not in command


class TestCountFrames:
    def test_unreadable_json_is_an_ffprobe_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def garbage(command: list[str], timeout: int = 0) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 0, stdout="not json", stderr="")

        monkeypatch.setattr(ffmpeg, "run", garbage)
        with pytest.raises(ffmpeg.FFprobeError, match="unreadable JSON"):
            ffmpeg.count_frames(tmp_path / "x.mov", ffprobe=Path("ffprobe"))


class TestAvailableDecoders:
    """QC-022 compares a probed codec name against this set, so it has to be real."""

    def test_it_lists_the_codecs_a_turnover_arrives_in(self) -> None:
        decoders = ffmpeg.available_decoders()
        assert {"exr", "h264", "prores", "dpx"} <= decoders

    def test_it_does_not_list_encoder_only_names(self) -> None:
        assert "libx264" not in ffmpeg.available_decoders()
