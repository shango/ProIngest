"""Synthetic test media, generated with ffmpeg and the OpenEXR bindings.

Never committed. Everything is built into a tmp_path at test time.

Real media at 3840x2160 is far too slow to generate per test, so the helpers default
to a small frame size and take the resolution as an argument. Tests that care about
resolution pass the real one; the rest stay fast. This is the "reduced resolution
flag" ARCHITECTURE.md asks for.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import OpenEXR

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
    header["framesPerSecond"] = fps

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
) -> Path:
    """A ProRes 4444 mov, one of the source formats COLOR_AND_FORMAT section 2 accepts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size[0]}x{size[1]}:rate={fps}:duration={count / fps}",
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={count / fps}:sample_rate=48000"]
    command += ["-c:v", codec, "-profile:v", profile, "-pix_fmt", "yuva444p10le"]
    if with_audio:
        command += ["-c:a", "pcm_s16le", "-ac", "2"]
    command += ["-timecode", timecode, "-frames:v", str(count), str(path)]
    _run(command)
    return path


def make_mp4(path: Path, count: int = 8, size: tuple[int, int] = SMALL, fps: int = FPS) -> Path:
    """An 8 bit 4:2:0 source, which QC-020 must reject as a linear plate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size[0]}x{size[1]}:rate={fps}:duration={count / fps}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-frames:v", str(count), str(path),
    ])
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
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate={sample_rate}",
        "-ac", str(channels), "-c:a", codec, str(path),
    ])
    return path


def make_dpx_sequence(
    directory: Path, base: str = "MELT0002_pl01", count: int = 4, first: int = 1001,
    size: tuple[int, int] = SMALL, fps: int = FPS,
) -> Path:
    """A DPX sequence, which is QC-021: integer container carrying linear data."""
    directory.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size[0]}x{size[1]}:rate={fps}:duration={count / fps}",
        "-pix_fmt", "gbrp10le", "-frames:v", str(count),
        "-start_number", str(first), str(directory / f"{base}.%04d.dpx"),
    ])
    return directory


def make_still(path: Path, size: tuple[int, int] = SMALL) -> Path:
    """A single image, used for BTS copies and for lone-numbered-file cases."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size[0]}x{size[1]}",
        "-frames:v", "1", str(path),
    ])
    return path
