"""The only place ffmpeg and ffprobe are invoked.

Nothing else in the codebase shells out. Every command is logged verbatim before it
runs so the user can paste it into a terminal and reproduce a render, which is a
stated requirement in CLAUDE.md.

Binary resolution order is: an explicit Settings override, then the bundled binary
for this platform, then PATH. The bundled binaries are macOS arm64 Mach-O executables,
so the bundled step is skipped off macOS and the Linux dev machine falls through to
PATH. That guard is load bearing: `ffmpeg` and `ffprobe` are spelled the same on both
platforms, so without it a Mach-O binary resolves as a perfectly good file on Linux and
then fails every subprocess with a bare "Exec format error".
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import IO, Any

import numpy as np
import numpy.typing as npt

from proingest.core import frames

log = logging.getLogger(__name__)

BUNDLED_DIR = Path(__file__).resolve().parent.parent / "resources" / "ffmpeg"

BUNDLED_PLATFORM = "darwin"
"""The lock file pins macOS arm64 binaries, so the bundle only applies on macOS."""

DEFAULT_TIMEOUT = 120

DECODE_TIMEOUT = 600
"""Only bounds the wait after the last frame is read; the read itself is unbounded."""

DECODE_PIXEL_FORMAT = "gbrpf32le"
"""COLOR_AND_FORMAT section 7. Planar float32, so nothing quantises on the way out."""

_PLANES = 3

_RAW_DTYPE = np.dtype("<f4")


class FFmpegNotFound(RuntimeError):
    """Neither the bundled binary, the override, nor PATH produced a usable tool."""


class FFprobeError(RuntimeError):
    """ffprobe ran but could not read the file. Reported as QC-014."""


class FFmpegError(RuntimeError):
    """ffmpeg ran and failed, or stopped short of the frames that were asked for."""


def _platform_binary(tool: str) -> str:
    return f"{tool}.exe" if os.name == "nt" else tool


def resolve_tool(tool: str, override: Path | None = None) -> Path:
    """Locate `ffmpeg` or `ffprobe`.

    An override is honoured whether it names the binary itself or the folder holding
    it, because both are natural things to paste into a settings field.
    """
    if override is not None:
        candidate = override / _platform_binary(tool) if override.is_dir() else override
        if candidate.is_file():
            return candidate
        raise FFmpegNotFound(f"{tool} override {override} does not exist")

    bundled = BUNDLED_DIR / _platform_binary(tool)
    if sys.platform == BUNDLED_PLATFORM and bundled.is_file():
        return bundled

    found = shutil.which(tool)
    if found:
        return Path(found)

    raise FFmpegNotFound(
        f"{tool} not found. Looked for a Settings override, then {bundled}, then PATH. "
        f"Run `python build/fetch_ffmpeg.py` to populate the bundled binaries."
    )


def run(command: list[str], timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a command, logging it verbatim first. Does not raise on a non-zero exit."""
    log.info("running: %s", " ".join(command))
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def probe_raw(path: Path, ffprobe: Path | None = None) -> dict[str, Any]:
    """Return ffprobe's JSON for one file.

    Raises FFprobeError when the file cannot be read, which the caller turns into
    QC-014 rather than letting it escape.
    """
    tool = ffprobe or resolve_tool("ffprobe")
    command = [
        str(tool),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = run(command)
    if result.returncode != 0:
        raise FFprobeError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    try:
        parsed: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FFprobeError(f"ffprobe returned unreadable JSON for {path}: {exc}") from exc
    if not parsed.get("streams"):
        raise FFprobeError(f"ffprobe found no streams in {path}")
    return parsed


def count_frames(path: Path, ffprobe: Path | None = None) -> int:
    """Exact frame count by decoding. Slow, so it is only used by QC-111."""
    tool = ffprobe or resolve_tool("ffprobe")
    command = [
        str(tool),
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_read_frames",
        "-print_format",
        "json",
        str(path),
    ]
    result = run(command, timeout=600)
    if result.returncode != 0:
        raise FFprobeError(f"frame count failed on {path}: {result.stderr.strip()}")
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise FFprobeError(f"no video stream in {path}")
    return int(streams[0]["nb_read_frames"])


@dataclass(frozen=True)
class ToolInfo:
    """Recorded in every QC log, per docs/PACKAGING.md."""

    path: Path
    version: str

    def __str__(self) -> str:
        return self.version


def tool_info(tool: str = "ffmpeg", override: Path | None = None) -> ToolInfo:
    """First line of `-version`, which carries the build string we pin in the lock file."""
    path = resolve_tool(tool, override)
    result = run([str(path), "-hide_banner", "-version"], timeout=30)
    first_line = result.stdout.splitlines()[0].strip() if result.stdout else "unknown"
    return ToolInfo(path=path, version=first_line)


@lru_cache(maxsize=1)
def available_encoders(ffmpeg: Path | None = None) -> frozenset[str]:
    """Encoder names this build supports. Cached; the binary does not change at runtime."""
    path = ffmpeg or resolve_tool("ffmpeg")
    result = run([str(path), "-hide_banner", "-encoders"], timeout=30)
    names = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        # Encoder rows look like " V....D libx264   libx264 H.264 ..."
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return frozenset(names)


def has_nvenc(ffmpeg: Path | None = None) -> bool:
    """Whether NVENC H.264 encoding is compiled in.

    Presence in the build does not prove a working NVIDIA GPU is attached; FR-7 wants
    detection at startup, and an actual encode attempt is the only real proof.
    """
    return "h264_nvenc" in available_encoders(ffmpeg)


# --- Decoding a container source to numpy frames. COLOR_AND_FORMAT section 7. ---


def decode_command(
    source: str,
    in_frame: int,
    out_frame: int,
    is_sequence: bool,
    target_size: tuple[int, int] | None = None,
    ffmpeg: Path | None = None,
) -> list[str]:
    """The command that decodes `[in_frame, out_frame]` to raw float32 on stdout.

    Built apart from running it so a caller can log or show it, and so the frame
    seek can be tested without decoding anything.

    Seeking is by frame in both branches, never by time. A sequence seeks with
    `-start_number`, which skips the frames before `in_frame` without opening them.
    A container has to decode from its start, so it seeks with the `trim` filter,
    which counts frames; `-ss` would take a float number of seconds and land on the
    wrong frame at 23.976.

    `target_size` adds the Lanczos downscale COLOR_AND_FORMAT section 4 specifies, so
    the HD pass is this same command with one more filter. That is the second decode
    per row, and it is deliberate: a filtergraph split to write both resolutions at
    once is more moving parts than the decode is worth.
    """
    tool = ffmpeg or resolve_tool("ffmpeg")
    count = frames.duration(in_frame, out_frame)
    command = [str(tool), "-hide_banner", "-loglevel", "error", "-nostdin"]

    filters = []
    if is_sequence:
        command += ["-start_number", str(in_frame)]
    else:
        # end_frame is exclusive, so it is the first frame past the range.
        filters.append(f"trim=start_frame={in_frame}:end_frame={out_frame + 1}")
    command += ["-i", source]
    if target_size is not None:
        filters.append(f"scale={target_size[0]}:{target_size[1]}:flags=lanczos")
    if filters:
        command += ["-vf", ",".join(filters)]

    # Map the video alone: a source with audio would otherwise reach the rawvideo
    # muxer as a second stream. fps_mode passthrough stops ffmpeg inventing or
    # dropping frames to hit a constant rate, which would break the 1:1 mapping
    # between source and output frames that section 6 defines.
    return [
        *command,
        "-map",
        "0:v:0",
        "-an",
        "-frames:v",
        str(count),
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        "-pix_fmt",
        DECODE_PIXEL_FORMAT,
        "-",
    ]


def _frame_from_planes(
    block: bytes, width: int, height: int
) -> npt.NDArray[np.float32]:
    """One `gbrpf32le` frame as `(h, w, 3)` RGB.

    The pixel format stores whole planes in G, B, R order, so RGB is planes 2, 0, 1.
    `np.stack` reorders and interleaves in a single copy.
    """
    planes = np.frombuffer(block, dtype=_RAW_DTYPE).reshape(_PLANES, height, width)
    return np.stack((planes[2], planes[0], planes[1]), axis=-1)


def _stderr_tail(handle: IO[bytes], limit: int = 2000) -> str:
    handle.seek(0)
    return handle.read().decode("utf-8", "replace").strip()[-limit:]


def decode_frames(
    source: str,
    source_size: tuple[int, int],
    in_frame: int,
    out_frame: int,
    is_sequence: bool = False,
    target_size: tuple[int, int] | None = None,
    ffmpeg: Path | None = None,
    timeout: int = DECODE_TIMEOUT,
) -> Generator[npt.NDArray[np.float32], None, None]:
    """Yield each frame of `[in_frame, out_frame]` as `(h, w, 3)` float32 RGB.

    `source` is what goes after `-i`: a file path, or a printf pattern for a
    sequence. `source_size` is the media's own resolution, which is how the frame
    size on the pipe is known; when `target_size` is given the frames arrive at that
    size instead.

    Frames are yielded one at a time and never accumulated. A 4k float32 frame is
    95 MB, so a hundred-frame shot held in a list would be 9 GB.

    Raises FFmpegError if ffmpeg fails or the stream ends early, and always leaves
    the process dead: abandoning the generator part way through a shot kills it
    rather than leaving a decode running.
    """
    width, height = target_size or source_size
    frame_bytes = width * height * _PLANES * _RAW_DTYPE.itemsize
    expected = frames.duration(in_frame, out_frame)
    command = decode_command(source, in_frame, out_frame, is_sequence, target_size, ffmpeg)
    log.info("running: %s", " ".join(command))

    with tempfile.TemporaryFile() as errors:
        # stderr goes to a file rather than a pipe nobody drains: a decode that fails
        # on every frame can write more than a pipe buffer holds and deadlock.
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        stdout = process.stdout
        assert stdout is not None
        try:
            for index in range(expected):
                block = stdout.read(frame_bytes)
                if len(block) != frame_bytes:
                    process.wait(timeout)
                    raise FFmpegError(
                        f"{source} gave {index} of {expected} frames from "
                        f"{in_frame}-{out_frame}: {_stderr_tail(errors)}"
                    )
                yield _frame_from_planes(block, width, height)
            if process.wait(timeout) != 0:
                raise FFmpegError(f"decoding {source} failed: {_stderr_tail(errors)}")
        finally:
            if process.poll() is None:
                process.kill()
            stdout.close()
            process.wait()


# --- Extracting audio out of a container. COLOR_AND_FORMAT section 3. ---


def extract_audio_command(
    source: Path, destination: Path, ffmpeg: Path | None = None
) -> list[str]:
    """Pull the first audio stream out as PCM 16 bit.

    Neither `-ar` nor `-ac` is passed, which is what "no resampling" means: the sample
    rate and the channel count arrive on the output exactly as they were on the input,
    and only the sample format changes. QC-044 reports a source that was not 16 bit
    already.

    **`-f wav` is not optional.** Every deliverable is written to a `.part` path and
    renamed, so ffmpeg never sees the real extension and cannot infer a format from it.
    Any ffmpeg output added later has to state its format the same way.
    """
    tool = ffmpeg or resolve_tool("ffmpeg")
    return [
        str(tool),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-map",
        "0:a:0",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        str(destination),
    ]


def extract_audio(source: Path, destination: Path, ffmpeg: Path | None = None) -> None:
    """Run the extract, raising FFmpegError with ffmpeg's own complaint on failure."""
    result = run(extract_audio_command(source, destination, ffmpeg))
    if result.returncode != 0:
        raise FFmpegError(f"extracting audio from {source} failed: {result.stderr.strip()}")
