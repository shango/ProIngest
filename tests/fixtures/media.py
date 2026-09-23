"""Synthetic test media, generated with ffmpeg and the OpenEXR bindings.

Never committed. Everything is built into a tmp_path at test time.

Real media at 3840x2160 is far too slow to generate per test, so the helpers default
to a small frame size and take the resolution as an argument. Tests that care about
resolution pass the real one; the rest stay fast. This is the "reduced resolution
flag" ARCHITECTURE.md asks for.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import OpenEXR

from proingest.core import qc
from proingest.core.models import FrameRate, MediaInfo

SMALL = (64, 36)
"""Default test resolution: 16:9, tiny, still exercises every code path."""

UHD = (3840, 2160)

FPS = 24


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"fixture command failed: {' '.join(command)}\n{result.stderr[-2000:]}")


@dataclass(frozen=True)
class SequenceFixture:
    directory: Path
    base: str
    first: int
    count: int
    width: int
    height: int

    @property
    def pattern(self) -> str:
        return str(self.directory / f"{self.base}.%04d.exr")

    def path_for(self, frame: int) -> Path:
        return self.directory / f"{self.base}.{frame:04d}.exr"


def make_exr_sequence(
    directory: Path,
    base: str = "MELT0001_pl01",
    count: int = 8,
    first: int = 1001,
    size: tuple[int, int] = SMALL,
    timecode: str | None = "01:00:00:00",
    fps: int = FPS,
    header_fps: int | None = None,
) -> SequenceFixture:
    """Write a half-float RGB EXR sequence.

    Written with the OpenEXR bindings rather than ffmpeg so the frames can carry a
    `timeCode` header attribute, which is where COLOR_AND_FORMAT section 5 says an
    EXR's source timecode comes from. ffmpeg's exr encoder cannot write one.
    """
    directory.mkdir(parents=True, exist_ok=True)
    width, height = size

    header: dict[str, object] = {"compression": OpenEXR.ZIP_COMPRESSION}
    if timecode is not None:
        hours, minutes, seconds, frame = (int(part) for part in timecode.split(":"))
        value = OpenEXR.TimeCode()
        value.hours, value.minutes, value.seconds, value.frame = hours, minutes, seconds, frame
        header["timeCode"] = value
    # header_fps differs from fps to simulate stale camera metadata surviving a
    # conform: the shooter set the clip to 24 in Resolve but the header still says
    # what the camera shot.
    header["framesPerSecond"] = fps if header_fps is None else header_fps

    for offset in range(count):
        pixels = np.zeros((height, width, 3), dtype=np.float16)
        # A per-frame ramp so frames are distinguishable and never uniformly black.
        pixels[:, :, 0] = np.float16((offset + 1) / (count + 1))
        OpenEXR.File(dict(header), {"RGB": pixels}).write(str(directory / f"{base}.{first + offset:04d}.exr"))

    return SequenceFixture(directory, base, first, count, width, height)


def make_mov(
    path: Path,
    count: int = 8,
    size: tuple[int, int] = SMALL,
    fps: int = FPS,
    timecode: str = "01:00:00:00",
    with_audio: bool = False,
    codec: str = "prores_ks",
    profile: str = "4",
    rate: str | None = None,
) -> Path:
    """A ProRes 4444 mov, one of the source formats COLOR_AND_FORMAT section 2 accepts.

    `rate` overrides `fps` with an exact fraction, for `24000/1001`, which is what every
    real delivered file states."""
    path.parent.mkdir(parents=True, exist_ok=True)
    numerator, _, denominator = (rate or str(fps)).partition("/")
    seconds = count * int(denominator or 1) / int(numerator)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size[0]}x{size[1]}:rate={rate or fps}:duration={seconds}",
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=48000"]
    command += ["-c:v", codec, "-profile:v", profile, "-pix_fmt", "yuva444p10le"]
    if with_audio:
        command += ["-c:a", "pcm_s16le", "-ac", "2"]
    command += ["-timecode", timecode, "-frames:v", str(count), str(path)]
    _run(command)
    return path


def make_mp4(path: Path, count: int = 8, size: tuple[int, int] = SMALL, fps: int = FPS) -> Path:
    """An 8 bit 4:2:0 source, which QC-020 must reject as a linear plate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size[0]}x{size[1]}:rate={fps}:duration={count / fps}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-frames:v",
            str(count),
            str(path),
        ]
    )
    return path


def make_wav(
    path: Path,
    seconds: float = 1.0,
    sample_rate: int = 48000,
    channels: int = 2,
    bit_depth: int = 16,
) -> Path:
    """48k 16 bit PCM by default, matching what the spec PDF calls for."""
    path.parent.mkdir(parents=True, exist_ok=True)
    codec = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}[bit_depth]
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}:sample_rate={sample_rate}",
            "-ac",
            str(channels),
            "-c:a",
            codec,
            str(path),
        ]
    )
    return path


def make_dpx_sequence(
    directory: Path,
    base: str = "MELT0002_pl01",
    count: int = 4,
    first: int = 1001,
    size: tuple[int, int] = SMALL,
    fps: int = FPS,
) -> Path:
    """A DPX sequence, which is QC-021: integer container carrying linear data."""
    directory.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size[0]}x{size[1]}:rate={fps}:duration={count / fps}",
            "-pix_fmt",
            "gbrp10le",
            "-frames:v",
            str(count),
            "-start_number",
            str(first),
            str(directory / f"{base}.%04d.dpx"),
        ]
    )
    return directory


def make_solid_dpx(path: Path, colour: str = "0x804020", size: tuple[int, int] = SMALL) -> Path:
    """A single DPX frame of one flat colour, for pinning down channel order.

    `gbrp10le` so the RGB values survive without a YUV round trip. lavfi's `color`
    still lands a little off the requested value, so tests compare channels against
    each other rather than against an exact number.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={colour}:size={size[0]}x{size[1]}",
            "-pix_fmt",
            "gbrp10le",
            "-frames:v",
            "1",
            str(path),
        ]
    )
    return path


def make_still(path: Path, size: tuple[int, int] = SMALL) -> Path:
    """A single image, used for BTS copies and for lone-numbered-file cases."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size[0]}x{size[1]}",
            "-frames:v",
            "1",
            str(path),
        ]
    )
    return path


def media_info_with_tags(tags: dict[str, str]) -> MediaInfo:
    """A probe result carrying container tags, which is the second carrier for OQ-44."""
    return MediaInfo(
        path=Path(f"/turnover/{next(iter(tags), 'clip')}.mov"),
        codec="prores",
        pixel_format="yuv444p12le",
        width=64,
        height=36,
        rate=FrameRate(FPS),
        frame_count=4,
        tags=tags,
    )


SOURCE_ENCODING = "ACEScct"
"""What the fixture turnover's clips say they are encoded in, in their own metadata.

A real clip names this and the scan reads it (M4.6.4, OQ-44). ACEScct because that is
what these tests rendered through before the encoding became a per clip fact.
"""


def make_meta_csv(
    path: Path, rows: list[tuple[str, str, str]], encoding: str | None = SOURCE_ENCODING
) -> Path:
    """Ben's metadata CSV, in the shape the real one has.

    `rows` is (File Name, Shot, Shot Type). UTF-16 with a BOM and **`Shot Type` twice**,
    because the real file carries Resolve's built-in at column 12 and the shooters'
    custom field of the same name at column 44: a fixture without the collision would
    not exercise the reader that exists to arbitrate it (QC-065).
    """
    gamma, space = encoding.split(" ", 1) if encoding and " " in encoding else (encoding or "", "")
    header = ["File Name", "Shot", "Shot Type", "Gamma Notes", "Color Space Notes", "Shot Code", "Shot Type"]
    lines = [header] + [[name, shot, kind, gamma, space, shot, kind] for name, shot, kind in rows]
    text = "\r\n".join(",".join(f'"{cell}"' for cell in line) for line in lines) + "\r\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-16"))
    return path


def make_final_edl(
    path: Path,
    clips: list[str],
    duration: int = 240,
    source_start: int = 86400,
    record_start: int = 86400,
    with_cdl: bool = True,
    reel: str = "MELT0001",
) -> Path:
    """Ben's final EDL: one event per clip, with the CDL that is the grade.

    Laid end to end in record order, which is what a stringout timeline looks like.
    `clips` are `FROM CLIP NAME` values, matched to a row by stem (`clf.event_for`); an
    empty one writes no name, which is what Resolve's CDL export does.
    """
    lines = [f"TITLE: {path.stem}", "FCM: NON-DROP FRAME", ""]
    record = record_start
    for index, clip in enumerate(clips, 1):
        src_out = timecode(source_start + duration)
        lines.append(
            f"{index:03d}  {reel} V     C        {timecode(source_start)} {src_out} "
            f"{timecode(record)} {timecode(record + duration)}"
        )
        if clip:
            lines.append(f"* FROM CLIP NAME: {clip}")
        if with_cdl:
            lines += [
                "*ASC_SOP (1.020000 0.990000 1.010000)"
                "(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)",
                "*ASC_SAT 1.050000",
            ]
        record += duration
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def timecode(frame: int, fps: int = FPS) -> str:
    seconds, rest = divmod(frame, fps)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}:{rest:02d}"


def make_turnover(
    root: Path,
    shots: int = 2,
    frames: int = 8,
    source_encoding: str | None = SOURCE_ENCODING,
    shot_types: list[str] | None = None,
) -> Path:
    """A handover folder as Ben leaves it: the media, his EDL and his metadata CSV.

    One EXR sequence and one wav per shot, named for the shot the way consolidated media
    is not - the fixture keeps the old names because the media search is by filename and
    what matters here is that the CSV, the EDL and the files agree, not what they agree on.
    """
    root.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str]] = []
    clips: list[str] = []
    for index in range(1, shots + 1):
        shot = f"MELT{index:04d}"
        name = f"{shot}_pl01"
        make_exr_sequence(root / "media", base=name, count=frames)
        make_wav(root / "media" / f"{name}.wav", seconds=frames / FPS)
        kind = shot_types[index - 1] if shot_types else "pl01"
        rows.append((name, shot, kind))
        clips.append(name)
    make_meta_csv(root / "metadata.csv", rows, source_encoding)
    make_final_edl(root / "FINAL_v01.edl", clips, duration=frames, source_start=86400)
    return root


SMALL_RULES = qc.RuleSettings(
    min_duration_frames=1,
    max_duration_frames=10_000,
    expected_handle_frames=0,
    target_resolution=SMALL,
)
"""Rule thresholds a fixture turnover can actually satisfy.

Fixture media is 64x36 and a few frames long, because a real 3840x2160 plate of the
minimum 120 frames is half a gigabyte. The rules are settings driven exactly so the
tests can say so out loud rather than special-casing themselves inside the rules.
"""


def write_rules_file(path: Path, settings: qc.RuleSettings = SMALL_RULES) -> Path:
    """A `--rules` JSON file, for driving the CLI against fixture-sized media."""
    path.write_text(json.dumps(settings.to_dict()), encoding="utf-8")
    return path
