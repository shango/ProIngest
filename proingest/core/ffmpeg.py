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
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Generator, Iterable, Sequence
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


_OVERRIDE: Path | None = None
"""The Settings page's ffmpeg path, in force for this process (FR-12, Advanced).

A module global rather than an argument because seven call sites pass none and threading
one through every signature to reach `resolve_tool` would be a parameter each of them
only forwards. It is set once at startup and once per **worker process** at its
initialiser, which is how it crosses the spawn boundary: `core/render.py` hands it over
beside the log queue, for the same reason and on the same channel.
"""


def set_override(path: Path | None) -> None:
    """Point every later `resolve_tool` at this binary or folder. None restores normal.

    `available_encoders` is cached against the binary it asked, so its answer is thrown
    away here: a different build of ffmpeg is exactly the thing that changes it.
    """
    global _OVERRIDE
    _OVERRIDE = path
    available_encoders.cache_clear()


def current_override() -> Path | None:
    """What is in force, so a caller can hand it to a process that has not got it."""
    return _OVERRIDE


def resolve_tool(tool: str, override: Path | None = None) -> Path:
    """Locate `ffmpeg` or `ffprobe`.

    An override is honoured whether it names the binary itself or the folder holding
    it, because both are natural things to paste into a settings field. **A path that
    does not exist raises rather than falling back**: an override silently ignored is a
    render done with the wrong build of ffmpeg and nothing said about it.
    """
    override = override if override is not None else _OVERRIDE
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
    log.info("running: %s", shlex.join(command))
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
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except json.JSONDecodeError as exc:
        raise FFprobeError(f"ffprobe returned unreadable JSON for {path}: {exc}") from exc
    if not streams:
        raise FFprobeError(f"no video stream in {path}")
    return int(streams[0]["nb_read_frames"])


def container_frame_count(path: Path, ffprobe: Path | None = None) -> int:
    """Frames the container says its video stream holds, read from the index.

    The cheap counterpart to `count_frames`, which decodes. It is enough to verify a
    file this tool just wrote, and it costs nothing on a 4k reference where a decode
    would cost minutes.

    Raises FFprobeError when the stream states no count, rather than reporting zero:
    the caller uses this to prove a delivery is complete, and an unknown count must
    never read as a verified one.
    """
    for stream in probe_raw(path, ffprobe).get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        if "nb_frames" not in stream:
            raise FFprobeError(f"{path} states no frame count")
        return int(stream["nb_frames"])
    raise FFprobeError(f"no video stream in {path}")


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


def available_decoders(ffmpeg: Path | None = None) -> frozenset[str]:
    """Decoder names this build supports, which is what QC-022 compares a codec against.

    ffprobe reports a stream's codec by the same name `-decoders` lists, so the
    comparison is direct. A build that cannot answer at all returns an empty set and
    QC-022 stays silent rather than failing every row.
    """
    path = ffmpeg or resolve_tool("ffmpeg")
    result = run([str(path), "-hide_banner", "-decoders"], timeout=30)
    names = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        # Decoder rows look like " V....D h264   H.264 / AVC ..." after a header block.
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return frozenset(names)


# --- YCbCr to RGB and back. D17 of the 2026-09-23 review. ---

DEFAULT_MATRIX = "bt709"
"""The matrix a file that states none is decoded with, and every reference is encoded
with. BT.709 is provisional (user, 2026-09-23: "pick a matrix for now"): the shooters'
files state no matrix at all, and ffmpeg's own fallback for that is BT.601, which is
the wrong answer for any HD or UHD camera file."""

_SCALE_MATRIX = {
    "bt709": "bt709",
    "smpte170m": "smpte170m",
    "bt470bg": "bt470",
    "bt2020nc": "bt2020",
    "bt2020c": "bt2020",
    "fcc": "fcc",
    "smpte240m": "smpte240m",
}
"""ffprobe's name for a matrix, to the `scale` filter's name for the same one."""


def input_matrix(color_space: str) -> str:
    """The matrix a file is decoded with: its own when it states one, else BT.709."""
    return _SCALE_MATRIX.get(color_space, DEFAULT_MATRIX)


def input_range(color_range: str) -> str:
    """The range a file is decoded at: full only when it says so, as the real files do."""
    return "full" if color_range in ("pc", "jpeg") else "limited"


def to_rgb(size: tuple[int, int] | None, color_space: str, color_range: str, pixel_format: str) -> str:
    """The filter that turns the source into float RGB, resized on the way when asked.

    **The matrix and range are stated rather than left to swscale**, which reads them
    off the frame and, for a file that states no matrix, falls back to BT.601. Every
    real file measured so far states none. The `format` straight after makes this one
    `scale` do the conversion, instead of an automatic one inserted later that would
    not see these options. An RGB source ignores both.
    """
    resize = f"{size[0]}:{size[1]}:flags=lanczos:" if size is not None else ""
    matrix, value_range = input_matrix(color_space), input_range(color_range)
    return f"scale={resize}in_color_matrix={matrix}:in_range={value_range},format={pixel_format}"


# --- Decoding a container source to numpy frames. COLOR_AND_FORMAT section 7. ---


def decode_command(
    source: str,
    in_frame: int,
    out_frame: int,
    is_sequence: bool,
    target_size: tuple[int, int] | None = None,
    ffmpeg: Path | None = None,
    color_space: str = "",
    color_range: str = "",
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

    `color_space` and `color_range` are the file's own tags, and `to_rgb` turns them
    into an explicit matrix and range for the conversion to RGB.
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
    filters.append(to_rgb(target_size, color_space, color_range, DECODE_PIXEL_FORMAT))
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


def _frame_from_planes(block: bytes, width: int, height: int) -> npt.NDArray[np.float32]:
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
    color_space: str = "",
    color_range: str = "",
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
    command = decode_command(
        source,
        in_frame,
        out_frame,
        is_sequence,
        target_size,
        ffmpeg,
        color_space=color_space,
        color_range=color_range,
    )
    log.info("running: %s", shlex.join(command))

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


VIEW_CODEC = ["-c:v", "ffv1", "-pix_fmt", "gbrp16le"]
"""A display referred picture the stringout cuts from: lossless 16 bit RGB, read once more
by the segment encode and then deleted, so size does not matter and a second lossy pass
would."""


def write_frames(
    frames_in: Iterable[npt.NDArray[np.float32]],
    size: tuple[int, int],
    destination: Path,
    rate: str,
    ffmpeg: Path | None = None,
    timeout: int = DECODE_TIMEOUT,
) -> int:
    """Write `(h, w, 3)` float32 RGB frames, already display referred and 0..1, to a
    lossless file at `destination` (`.mkv`). Returns the frames written.

    The pipe's other direction from `decode_frames`: planes go in G, B, R order. Raises
    FFmpegError when ffmpeg fails, and always leaves the process dead.
    """
    tool = ffmpeg or resolve_tool("ffmpeg")
    width, height = size
    command = [
        str(tool), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "gbrpf32le", "-s", f"{width}x{height}", "-r", rate, "-i", "-",
        *VIEW_CODEC, "-f", "matroska", str(destination),
    ]  # fmt: skip
    log.info("running: %s", shlex.join(command))
    written = 0
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        stdin = process.stdin
        assert stdin is not None
        try:
            for frame in frames_in:
                planes = np.stack((frame[..., 1], frame[..., 2], frame[..., 0])).astype(_RAW_DTYPE)
                stdin.write(planes.tobytes())
                written += 1
            stdin.close()
            if process.wait(timeout) != 0:
                raise FFmpegError(f"writing {destination.name} failed: {_stderr_tail(errors)}")
        except BrokenPipeError as exc:
            process.wait(timeout)
            raise FFmpegError(f"writing {destination.name} failed: {_stderr_tail(errors)}") from exc
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    return written


# --- Extracting audio out of a container. COLOR_AND_FORMAT section 3. ---


def extract_audio_command(
    source: Path,
    destination: Path,
    ffmpeg: Path | None = None,
    skip: float = 0.0,
    tempo: float = 1.0,
    duration: float | None = None,
) -> list[str]:
    """Pull the first audio stream out as PCM 16 bit.

    With a `duration`, the sound is cut to the picture: `skip` seconds dropped off the
    front, sped up by `tempo` so it follows a picture played at 24 (1.001 for a
    24000/1001 file), and padded or cut to exactly `duration` seconds. `atempo` keeps the
    pitch. The numbers come from integer frames in `core/render.py`.

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
        *(["-ss", f"{skip:.6f}"] if skip > 0 else []),
        "-i",
        str(source),
        "-vn",
        "-map",
        "0:a:0",
        *(["-af", _audio_fit(tempo, duration)] if duration is not None else []),
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        str(destination),
    ]


def _audio_fit(tempo: float, duration: float) -> str:
    """Speed the sound up to the picture's rate, then make it exactly `duration` long."""
    fit = f"apad,atrim=duration={duration:.6f}"
    return fit if tempo == 1.0 else f"atempo={tempo:.9f},{fit}"


def extract_audio(
    source: Path,
    destination: Path,
    ffmpeg: Path | None = None,
    skip: float = 0.0,
    tempo: float = 1.0,
    duration: float | None = None,
) -> None:
    """Run the extract, raising FFmpegError with ffmpeg's own complaint on failure."""
    result = run(extract_audio_command(source, destination, ffmpeg, skip, tempo, duration))
    if result.returncode != 0:
        raise FFmpegError(f"extracting audio from {source} failed: {result.stderr.strip()}")


# --- Encoding a reference mp4. COLOR_AND_FORMAT section 3. ---

ENCODE_TIMEOUT = 1800
"""A 4k CRF 18 `preset slow` encode of a long shot is minutes, not seconds."""

REFERENCE_CRF = 18
"""The quality a reference is encoded at by default, COLOR_AND_FORMAT section 3.

x264's rate factor: lower is better and bigger, 0 is lossless and 51 is the worst the
encoder will do. The spec pins 18 and the Settings page's Output section may move it
(FR-12), which is what `set_reference_crf` below is for.
"""

REFERENCE_PRESET = "slow"
REFERENCE_KEYINT = "24"
"""One keyframe a second at 24. The spec pins the number, not the duration."""

_CRF = REFERENCE_CRF
"""The rate factor in force for this process (FR-12, Output).

A module global for the reason `_OVERRIDE` is one, and it crosses the spawn boundary on
the same channel: `core/render.py` hands it to every worker at its initialiser, because
a worker is a fresh interpreter that never saw the Settings page.
"""


def set_reference_crf(crf: int) -> None:
    """Encode every later reference at this rate factor."""
    global _CRF
    _CRF = int(crf)


def current_reference_crf() -> int:
    """What is in force, so a caller can hand it to a process that has not got it."""
    return _CRF


REFERENCE_PIXEL_FORMAT = "yuv420p"
REFERENCE_AUDIO_BITRATE = "192k"

REFERENCE_TO_YUV = (
    f"scale=out_color_matrix={DEFAULT_MATRIX}:out_range=limited,format={REFERENCE_PIXEL_FORMAT}"
)
"""The conversion back to what x264 is handed, with the matrix the output is tagged with."""


def pad_filter(canvas: tuple[int, int]) -> str:
    """Letterbox the picture onto the canvas, where `resize.letterbox_offset` puts it in
    an EXR: centred, rounded down to an even pixel."""
    return f"pad={canvas[0]}:{canvas[1]}:trunc((ow-iw)/4)*2:trunc((oh-ih)/4)*2:black"


DEFAULT_DISPLAY = "sRGB - Display"

REFERENCE_TRANSFERS: dict[str, tuple[str, str]] = {
    "sRGB - Display": ("iec61966-2-1", "iec61966-2-1"),
    "Gamma 2.2 Rec.709 - Display": ("gamma22", "bt470m"),
    "Rec.1886 Rec.709 - Display": ("bt709", "bt709"),
}
"""The transfer a reference is labelled with, by the display its pixels were rendered for.

Since 2026-09-28 the display comes from the clip's AMF, so the label has to follow it: a
gamma 2.2 encode labelled sRGB is played back through the wrong curve by any player that
reads the tag. Only the three Rec.709 primaries displays of the pinned config are here,
because a reference is an 8 bit Rec.709 mp4; a display that is not (P3, HDR) is QC-079 at
scan. Each is two names for one curve, because the two places it is set spell it
differently: the `-color_trc` option takes `gamma22` and refuses `bt470m`, and `setparams`
takes `bt470m` (the standard's code for a 2.2 curve) and refuses `gamma22` (ffmpeg 6.1).
"""


def reference_label(display: str = DEFAULT_DISPLAY) -> str:
    """The same label as a filter, set on every frame as the chain's last step.

    **Both, because ffmpeg versions disagree about which wins.** 6.1 labels the stream from
    the `-color_trc` option; the bundled 9.0.1 takes the frames' own properties, which the
    conversion to 4:2:0 leaves unset, and wrote no transfer at all (CI, 2026-09-28).
    """
    reference_tags(display)  # the same refusal for a display with no label
    transfer = REFERENCE_TRANSFERS[display][1]
    return f"setparams=color_primaries=bt709:color_trc={transfer}:colorspace=bt709:range=tv"


def reference_tags(display: str = DEFAULT_DISPLAY) -> list[str]:
    """How the output is labelled: Rec.709 primaries and matrix, the display's transfer."""
    transfer = REFERENCE_TRANSFERS.get(display)
    if transfer is None:
        raise FFmpegError(f"a reference cannot be labelled for {display!r}")
    return ["-color_primaries", "bt709", "-colorspace", "bt709", "-color_trc", transfer[0]]


LUT_PIXEL_FORMAT = "gbrpf32le"
"""What the cube is applied in. Planar float32 RGB, the same format the decode uses.

Stated rather than left to ffmpeg's format negotiation, which would pick whatever
`lut3d` and the decoder happen to share: that is a high bit depth format today and it
is not something the delivered look should depend on.
"""

LUT_INTERPOLATION = "tetrahedral"
"""`lut3d` already defaults to this. It is written out for the same reason
`color.INTERPOLATION` exists: trilinear is visibly worse on saturated colour and it is
a one word difference nobody notices being wrong."""


def _x264(crf: int | None = None, display: str = DEFAULT_DISPLAY) -> list[str]:
    """How every reference, and every stringout segment, is encoded."""
    return [
        "-c:v", "libx264", "-profile:v", "high", "-preset", REFERENCE_PRESET,
        "-crf", str(_CRF if crf is None else crf), "-g", REFERENCE_KEYINT,
        "-pix_fmt", REFERENCE_PIXEL_FORMAT, *reference_tags(display),
    ]  # fmt: skip


def lut_filter(cube: Path) -> str:
    """The filter that applies a baked `.cube`, COLOR_AND_FORMAT section 1.

    **This is how an OCIO transform reaches ffmpeg**, which has no OCIO filter. The
    whole view branch is inside the cube, so the encode stays one pass and no frame is
    pulled through Python.

    A filter argument is colon separated and backslash escaped, so the path is escaped
    rather than pasted. Nothing the tool writes contains either character, and a
    filtergraph that fails to parse is a render that fails on a temp directory name.
    """
    return f"lut3d={_filter_path(cube)}:interp={LUT_INTERPOLATION}"


def shaper_filter(cube: Path) -> str:
    """The 1D shaper a linear source goes through before its cube (`color.shaper_lut`)."""
    return f"lut1d={_filter_path(cube)}:interp=linear"


def encode_command(
    source: str,
    destination: Path,
    in_frame: int,
    out_frame: int,
    is_sequence: bool,
    rate: str,
    target_size: tuple[int, int] | None = None,
    lut: Path | None = None,
    audio: Path | None = None,
    audio_skip: float = 0.0,
    ffmpeg: Path | None = None,
    crf: int | None = None,
    audio_tempo: float = 1.0,
    shaper: Path | None = None,
    timecode: str | None = None,
    color_space: str = "",
    color_range: str = "",
    canvas: tuple[int, int] | None = None,
    hold: int = 0,
    overlay: Sequence[str] = (),
    silence: bool = False,
    audio_format: Sequence[str] = (),
    display: str = DEFAULT_DISPLAY,
    insets: Sequence[Inset] = (),
) -> list[str]:
    """The command that encodes `[in_frame, out_frame]` to one reference mp4.

    `overlay` is filters drawn last, on the finished canvas: the stringout's burn-ins.
    `insets` are pictures laid over the canvas before them (a stringout plate's cp and wit).
    `silence` gives a picture with no `audio` a silent track of the same length, so every
    stringout segment has the same streams and they join without a re-encode, and
    `audio_format` pins the sound's rate and layout for the same reason.

    With `hold` longer than the range, the last frame is repeated until the reference
    is `hold` frames long: a freeze delivers one frame shown for five seconds.

    The seek is `decode_command`'s, for the same reasons: `-start_number` for a
    sequence, the frame-counting `trim` filter for a container, never `-ss`, which
    would take seconds and land on the wrong frame at 23.976.

    Three things here are load bearing and none of them fail loudly:

    - **`rate` is passed as `-framerate` before a sequence input.** The image2 demuxer
      states no rate of its own and defaults to **25**, so without this every reference
      built from an EXR or DPX sequence plays 4% fast with nothing in the log.
    - **`rate` is passed as `-r` before a container input too**, which makes ffmpeg read
      the file as that rate frame for frame. The shooters' files are 24000/1001 and every
      deliverable is written at 24 (user, 2026-09-23); without it the mp4 kept 23.976
      and QC-113 refused all four references. Measured: the same frames come out, bit
      for bit, and restamping after the trim with `setpts` left the encoder at 23.976.
    - **`setpts=PTS-STARTPTS` follows the trim.** `trim` keeps the source timestamps,
      so the first delivered frame lands at its original offset and the mp4 opens with
      a gap that long. Measured: four frames at 24 came out 0.25s instead of 0.17s.
    - **`timecode` is the first delivered frame's, 1001** (2026-09-25; it was the In frame's
      camera timecode), stated with `-timecode`, because otherwise the muxer copies the
      source's start timecode.
    - **`-f mp4` is stated.** The output is a `.part` path, so there is no extension to
      infer a muxer from. This is the same trap `extract_audio_command` documents.
    - **Both matrices are stated.** In through `to_rgb`, from the file's own tags, and
      out with `REFERENCE_TO_YUV`. Left to swscale, the conversion back to 4:2:0 used
      BT.601 under a BT.709 tag, which shifts every saturated colour (F7).

    `canvas` is the size the picture is letterboxed onto, given only when the source has
    another shape than the deliverable, which is how it keeps its shape (F9).

    `lut` is the viewing LUT `color.view_lut` baked for this shot, applied after the
    scale so the downscale runs on the log values, which are bounded 0..1 the way
    swscale needs them (section 1). Everything unbounded is inside the cube. `audio_skip`
    drops that many seconds off the front of the audio, which is how sound stays with
    the picture when the editor delivers a sub-range.

    `crf` defaults to whatever the Settings page put in force for this process, the same
    way `ffmpeg` defaults to the override: a caller that has an opinion states it, and
    everything else gets the one setting rather than a constant.
    """
    tool = ffmpeg or resolve_tool("ffmpeg")
    count = frames.duration(in_frame, out_frame)
    written = max(count, hold)
    command = [str(tool), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]

    filters = []
    if is_sequence:
        command += ["-framerate", rate, "-start_number", str(in_frame)]
    else:
        # end_frame is exclusive, so it is the first frame past the range.
        command += ["-r", rate]
        filters += [
            f"trim=start_frame={in_frame}:end_frame={out_frame + 1}",
            "setpts=PTS-STARTPTS",
        ]
    if written > count:
        # Cut the range first: a sequence input runs on past it, and the hold repeats the
        # range's last frame, not whatever follows it.
        filters += [f"trim=end_frame={count}", f"tpad=stop_mode=clone:stop={written - count}"]
    command += ["-i", source]

    if audio is not None:
        if audio_skip > 0:
            command += ["-ss", f"{audio_skip:.6f}"]
        command += ["-i", str(audio)]
    elif silence:
        command += ["-f", "lavfi", "-i", SILENCE]

    filters.append(to_rgb(target_size, color_space, color_range, LUT_PIXEL_FORMAT))
    if shaper is not None:
        filters.append(shaper_filter(shaper))
    if lut is not None:
        filters.append(lut_filter(lut))
    filters += [REFERENCE_TO_YUV, reference_label(display)]
    if canvas is not None:
        filters.append(pad_filter(canvas))
    if insets:
        # The label again after the overlays, so it is on the frames that are encoded.
        command += ["-vf", inset_graph(filters, insets, [reference_label(display), *overlay])]
    else:
        command += ["-vf", ",".join([*filters, *overlay])]

    # fps_mode passthrough for the same reason the decode passes it: ffmpeg must not
    # invent or drop frames to reach a constant rate, because section 6 maps output
    # frame 1001 + k onto source frame in + k and nothing may break that.
    command += ["-map", "0:v:0"]
    sounded = audio is not None or silence
    command += ["-map", "1:a:0"] if sounded else ["-an"]
    command += [
        "-frames:v",
        str(written),
        "-fps_mode",
        "passthrough",
        *_x264(crf, display),
    ]
    if sounded:
        # `apad` then `atrim` states the audio's length outright: pad it to endless,
        # then cut it to exactly the picture. Both halves are needed and neither is
        # about the other stream. A wav shorter than the picture is padded with silence,
        # because OQ-27 says the wav runs cut to cut and the editor can extend Out into
        # the handles; a wav that overruns is cut back to the delivered range.
        #
        # **This used to be `apad` and `-shortest`, and `-shortest` is a heuristic.** It
        # ends the output when the shortest stream does, but it lets audio buffer ahead
        # of a video stream that is still in a filtergraph, and how far ahead depends on
        # the ffmpeg version. M4.5.4 put a `lut3d` in that graph and ffmpeg 9.0.1, which
        # is the bundled build, delivered 0.98 seconds of audio against a third of a
        # second of picture; ffmpeg 6.1.1 on the dev machine did not, so only CI saw it.
        # A duration computed from integer frames does not depend on either.
        command += [
            "-c:a",
            "aac",
            "-b:a",
            REFERENCE_AUDIO_BITRATE,
            "-af",
            _audio_fit(audio_tempo, _seconds(written, rate)),
            *audio_format,
        ]
    if timecode is not None:
        command += ["-timecode", timecode]
    return [*command, "-movflags", "+faststart", "-f", "mp4", str(destination)]


STRINGOUT_AUDIO = ("-ar", "48000", "-ac", "2")
"""Every stringout segment's sound, whatever its plate recorded, so all of them match."""

SILENCE = "anullsrc=r=48000:cl=stereo"
"""A stringout segment with no sound of its own: 48 kHz stereo, what AAC from a camera wav
comes out as, so the segments agree and join by stream copy."""


def drawtext_literal(text: str) -> str:
    """Text for `drawtext` to print as written. Its expansion reads `%{...}` and a backslash
    even from a `textfile`, so both are escaped: a Scene of `50% rain` must not vanish."""
    return text.replace("\\", "\\\\").replace("%", "\\%")


BURN_IN_BOX = "black@0.3"
"""The semi-transparent rectangle behind every burn-in, 30% opaque (user, 2026-10-05)."""

BURN_IN_PADDING = 8
"""How far the rectangle reaches past the text on each side, in pixels."""


def drawtext_filter(textfile: Path, font: Path, size: int, x: str, y: str) -> str:
    """One burn-in, read from a file rather than inlined: the docs warn that inline text
    can need four levels of escaping, and a file needs one (the path)."""
    return (
        f"drawtext=fontfile={_filter_path(font)}:textfile={_filter_path(textfile)}"
        f":fontsize={size}:fontcolor=white:x={x}:y={y}"
        f":y_align=font:box=1:boxcolor={BURN_IN_BOX}:boxborderw={BURN_IN_PADDING}"
    )


@dataclass(frozen=True)
class Inset:
    """A picture in picture: `length` frames of the mp4 at `path` from frame `start`,
    scaled to `size` with its top left corner at (`x`, `y`). It is gone once it ends.
    `filters` run on it after the scale, so a burn-in on it goes when it does."""

    path: Path
    start: int
    length: int
    x: int
    y: int
    size: tuple[int, int]
    filters: tuple[str, ...] = ()


def inset_graph(chain: Sequence[str], insets: Sequence[Inset], after: Sequence[str]) -> str:
    """`chain`, then each inset laid over it in order, then `after` (the burn-ins, on top).

    Still one `-vf` graph with one input and one output: each inset is read by a `movie`
    source inside it, so the encode stays a single command. `eof_action=pass` is what
    removes an inset when it runs out rather than holding its last frame (user,
    2026-09-29).
    """
    links = [f"{','.join(chain)}[m0]"]
    for index, inset in enumerate(insets):
        end = inset.start + inset.length
        links.append(
            f"movie={_filter_path(inset.path)},trim=start_frame={inset.start}:end_frame={end},"
            f"setpts=PTS-STARTPTS,scale={inset.size[0]}:{inset.size[1]}:flags=lanczos"
            f"{''.join(',' + step for step in inset.filters)}[p{index}]"
        )
        links.append(f"[m{index}][p{index}]overlay=x={inset.x}:y={inset.y}:eof_action=pass[m{index + 1}]")
    links.append(f"[m{len(insets)}]{','.join(after)}")
    return ";".join(links)


def _filter_path(path: Path) -> str:
    """A path inside a filtergraph argument: colon separated and backslash escaped."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def black_command(
    destination: Path,
    size: tuple[int, int],
    rate: str,
    length: int,
    overlay: Sequence[str] = (),
    ffmpeg: Path | None = None,
    display: str = DEFAULT_DISPLAY,
) -> list[str]:
    """`length` frames of black with silence, encoded as a reference is, so it joins the
    segments either side of it: a gap in the EDL, or an event nothing is known about."""
    tool = ffmpeg or resolve_tool("ffmpeg")
    picture = f"color=c=black:s={size[0]}x{size[1]}:r={rate}"
    filters = [REFERENCE_TO_YUV, reference_label(display), *overlay]
    return [
        str(tool), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "lavfi", "-i", picture, "-f", "lavfi", "-i", SILENCE,
        "-vf", ",".join(filters), "-map", "0:v:0", "-map", "1:a:0",
        "-frames:v", str(length), *_x264(display=display),
        "-c:a", "aac", "-b:a", REFERENCE_AUDIO_BITRATE,
        "-af", f"atrim=duration={_seconds(length, rate):.6f}", *STRINGOUT_AUDIO,
        "-movflags", "+faststart", "-f", "mp4", str(destination),
    ]  # fmt: skip


def concat_command(listing: Path, destination: Path, timecode: str, ffmpeg: Path | None = None) -> list[str]:
    """Join encoded segments by stream copy (the concat demuxer), as one mp4 whose own
    timecode starts where the EDL's record does. Every segment was encoded with the same
    settings and streams, which is what makes copying safe."""
    tool = ffmpeg or resolve_tool("ffmpeg")
    return [
        str(tool), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-c", "copy", "-timecode", timecode, "-movflags", "+faststart", "-f", "mp4", str(destination),
    ]  # fmt: skip


def _seconds(count: int, rate: str) -> float:
    """`count` frames at `rate`, as seconds, at the ffmpeg boundary.

    `render._audio_skip` is the other place frames become seconds; both divide by the
    exact fraction rather than a float rate.

    `rate` arrives as the exact fraction `encode_command` passes to ffmpeg, so 23.976
    stays 24000/1001 until here and the audio cannot drift against the picture over a
    long shot.
    """
    numerator, _, denominator = rate.partition("/")
    return count * int(denominator or 1) / int(numerator)


def encode_reference(
    source: str,
    destination: Path,
    in_frame: int,
    out_frame: int,
    is_sequence: bool,
    rate: str,
    target_size: tuple[int, int] | None = None,
    lut: Path | None = None,
    audio: Path | None = None,
    audio_skip: float = 0.0,
    ffmpeg: Path | None = None,
    audio_tempo: float = 1.0,
    timecode: str | None = None,
    color_space: str = "",
    color_range: str = "",
    canvas: tuple[int, int] | None = None,
    hold: int = 0,
    display: str = DEFAULT_DISPLAY,
) -> None:
    """Run the reference encode, raising FFmpegError with ffmpeg's own complaint.

    One pass over the source, unlike the raw path: x264 wants the frames anyway, so
    there is nothing to gain by decoding them into this process first, and a good deal
    to lose in copying 95 MB a frame across a pipe.
    """
    command = encode_command(
        source,
        destination,
        in_frame,
        out_frame,
        is_sequence,
        rate,
        target_size,
        lut,
        audio,
        audio_skip,
        ffmpeg,
        audio_tempo=audio_tempo,
        timecode=timecode,
        color_space=color_space,
        color_range=color_range,
        canvas=canvas,
        hold=hold,
        display=display,
    )
    result = run(command, timeout=ENCODE_TIMEOUT)
    if result.returncode != 0:
        raise FFmpegError(f"encoding {destination.name} failed: {result.stderr.strip()}")
