"""OpenEXR reading and writing.

Reading exists because an EXR sequence carries its start timecode in a `timeCode`
attribute that ffprobe does not surface, and COLOR_AND_FORMAT section 5 says source
timecode comes from the container or the EXR header.

Writing is the raw deliverable, COLOR_AND_FORMAT section 3: scanline, DWAA at level
45, half float, data window equal to display window, frames numbered from 1001.

The bindings take the header first and the channel dict second:
`OpenEXR.File(header, {"RGB": pixels})`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import OpenEXR

from proingest.core import clf, color, frames

DWA_COMPRESSION_LEVEL = 45
"""What COLOR_AND_FORMAT section 3 pins, and the default. Written as a float attribute.

Higher is smaller and lossier. The Settings page's Output section may move it (FR-12),
which is what `set_compression_level` is for; an integer because every value anyone
states for DWAA is one, and a spin box is how the page edits it.
"""

_LEVEL = float(DWA_COMPRESSION_LEVEL)
"""The level in force for this process (FR-12, Output).

A module global for the reason `ffmpeg._OVERRIDE` is one, and it crosses the spawn
boundary on the same channel: `core/render.py` hands it to every worker at its
initialiser, because a worker is a fresh interpreter that never saw the Settings page.
"""


def set_compression_level(level: float) -> None:
    """Write every later frame at this DWAA level."""
    global _LEVEL
    _LEVEL = float(level)


def current_compression_level() -> float:
    """What is in force, so a caller can hand it to a process that has not got it."""
    return _LEVEL


CHROMATICITIES = (0.713, 0.293, 0.165, 0.830, 0.128, 0.044, 0.32168, 0.33767)
"""**AP1 primaries with the ACES white point**, COLOR_AND_FORMAT section 1.

Written as the eight floats the attribute is defined as, red through white, so a
reader knows the primaries the linear data is in without being told. This constant is
the difference between a file that is ACEScg and a file that lies about being ACEScg,
and it moved here from sRGB and Rec.709 in M4.5.4 along with everything else that used
to assume a display referred source.
"""

COLORSPACE_ATTRIBUTE = "proingest/colorspace"
"""What the pixels are, stated in the file. COLOR_AND_FORMAT section 1.

Always `color.PLATE_SPACE` now, because the tool transforms every plate it writes into
it rather than passing the source through. It was a parameter while the source's own
space was what the file carried; the value is a fact about the deliverable, so it is a
constant.
"""

SOURCE_ENCODING_ATTRIBUTE = "proingest/source_encoding"
"""The log encoding the source was read as, and therefore the input transform applied."""

SOURCE_ENCODING_ORIGIN_ATTRIBUTE = "proingest/source_encoding_origin"
"""Where that name came from: the clip's metadata, a container tag, or an override.

The encoding is the fact that matters and the origin is how a wrong one is traced back
to whoever wrote it (COLOR_AND_FORMAT, EXR metadata). Written only beside an encoding,
so the header never carries a source for a name it does not state.
"""

CLF_ATTRIBUTE = "proingest/clf"
CLF_HASH_ATTRIBUTE = "proingest/clf_hash"
"""The CLF's filename and its sha256. **The hash is what identifies the grade**: a CLF
re-exported and redelivered gets a new one, so frames rendered from the old version stay
findable afterwards. Both are absent from a frame rendered with no CLF, rather than
present and empty, so a reader cannot mistake ungraded for graded-with-nothing."""

CDL_ATTRIBUTES = (
    "proingest/cdl_slope",
    "proingest/cdl_offset",
    "proingest/cdl_power",
    "proingest/cdl_saturation",
    "proingest/cdl_asc_sop",
    "proingest/cdl_asc_sat",
    "proingest/cdl_note",
)
"""The CDL from the final EDL, as numbers and as the lines it was written on.

Both forms, because the numbers are what a tool reads and the verbatim text is what a
human compares against the session. Neither was applied to these pixels, and
`proingest/cdl_note` says so in the file: the CLF is the transform and the CDL is its
readable record (COLOR_AND_FORMAT section 1, EXR metadata).
"""

CDL_NOTE = "record only; the CLF named in proingest/clf is what was applied"

RGB_CHANNELS = "RGB"
RGBA_CHANNELS = "RGBA"


class ExrError(RuntimeError):
    """The file did not open or its header did not parse. Reported as QC-014 or QC-052."""


@dataclass(frozen=True)
class ExrHeader:
    """The header fields QC-103, QC-104 and QC-105 check."""

    width: int
    height: int
    data_window: tuple[int, int, int, int]
    display_window: tuple[int, int, int, int]
    compression: str
    channels: tuple[str, ...]
    pixel_type: str
    timecode: str | None = None
    is_drop_frame: bool = False
    frames_per_second: tuple[int, int] | None = None
    """Rate as (numerator, denominator). ffprobe cannot know this from one frame."""

    @property
    def windows_match(self) -> bool:
        """QC-104 requires the data window to equal the display window."""
        return self.data_window == self.display_window

    @property
    def resolution(self) -> tuple[int, int]:
        return self.width, self.height


def _window(value: Any) -> tuple[int, int, int, int]:
    """A window comes back as a pair of (x, y) arrays for the min and max corners."""
    low, high = value
    return int(low[0]), int(low[1]), int(high[0]), int(high[1])


def _channel_names(part: Any) -> tuple[str, ...]:
    """The numpy API groups RGB into one array, so expand it back to real channel names."""
    names: list[str] = []
    for key in part.channels:
        if key in ("RGB", "RGBA"):
            names.extend(key)
        else:
            names.append(key)
    return tuple(names)


def read_header(path: Path) -> ExrHeader:
    """Read one EXR header. Raises ExrError when the file will not open.

    Everything is copied out inside the `with`: the header dict the binding hands
    back is only readable while the file is open, and the file is closed here rather
    than left to the collector because opening it decoded the whole frame with it.
    """
    try:
        with OpenEXR.File(str(path)) as handle:
            header = handle.header()
            part = handle.parts[0]
            data_window = _window(header["dataWindow"])
            display_window = _window(header["displayWindow"])
            compression = str(header["compression"]).rsplit(".", 1)[-1]
            channels = _channel_names(part)
            pixel_type = str(next(iter(part.channels.values())).pixels.dtype)
            timecode = header.get("timeCode")
            rate = header.get("framesPerSecond")
            timecode_text = _format_timecode(timecode) if timecode is not None else None
            is_drop_frame = bool(getattr(timecode, "dropFrame", False)) if timecode is not None else False
            fps = (int(rate.numerator), int(rate.denominator)) if rate is not None else None
    except Exception as exc:  # the bindings raise several unrelated types
        raise ExrError(f"could not read EXR header from {path}: {exc}") from exc

    return ExrHeader(
        width=display_window[2] - display_window[0] + 1,
        height=display_window[3] - display_window[1] + 1,
        data_window=data_window,
        display_window=display_window,
        compression=compression,
        channels=channels,
        pixel_type=pixel_type,
        timecode=timecode_text,
        is_drop_frame=is_drop_frame,
        frames_per_second=fps,
    )


def _format_timecode(value: Any) -> str:
    return f"{value.hours:02d}:{value.minutes:02d}:{value.seconds:02d}:{value.frame:02d}"


def start_timecode_frames(path: Path, fps: float) -> int | None:
    """Start timecode of an EXR as a frame count, or None when the header carries none.

    A drop-frame header is refused rather than silently miscounted; the caller
    reports that as QC-027.
    """
    return header_timecode_frames(read_header(path), fps)


def header_timecode_frames(header: ExrHeader, fps: float) -> int | None:
    """`start_timecode_frames` for a header already in hand, so a probe reads it once."""
    if header.timecode is None:
        return None
    if header.is_drop_frame:
        raise ExrError("EXR header carries drop-frame timecode (QC-027)")
    return frames.timecode_to_frames(header.timecode, fps)


# --- Reading pixels, for the EXR source path. COLOR_AND_FORMAT section 7. ---


def read_pixels(path: Path) -> npt.NDArray[np.float32]:
    """Read one EXR's colour channels as float32 `(h, w, channels)`.

    Float32 rather than the file's own type because everything downstream, the
    resample in particular, works in float and half would lose precision twice.
    Any extra channel the file carries is dropped: a plate delivers RGB, or RGBA
    when the source has a real alpha.
    """
    try:
        with OpenEXR.File(str(path)) as handle:
            channels = handle.parts[0].channels
            for grouped in (RGBA_CHANNELS, RGB_CHANNELS):
                if grouped in channels:
                    return np.array(channels[grouped].pixels, dtype=np.float32)
            names = _colour_channel_names(channels, path)
            return np.stack([np.asarray(channels[name].pixels, dtype=np.float32) for name in names], axis=-1)
    except ExrError:
        raise
    except Exception as exc:  # the bindings raise several unrelated types
        raise ExrError(f"could not read pixels from {path}: {exc}") from exc


def _colour_channel_names(channels: Any, path: Path) -> tuple[str, ...]:
    """R, G, B and A when they are separate channels rather than one grouped array."""
    if not all(name in channels for name in RGB_CHANNELS):
        raise ExrError(f"{path} has no RGB channels (found {sorted(channels)})")
    return tuple(RGBA_CHANNELS) if "A" in channels else tuple(RGB_CHANNELS)


# --- Writing the raw deliverable. COLOR_AND_FORMAT section 3. ---


def provenance(shot_color: clf.ShotColor, loaded_clf: clf.LoadedClf | None = None) -> dict[str, Any]:
    """The header's account of how these pixels got here. COLOR_AND_FORMAT section 1.

    A graded plate is only auditable if the file says what was done to it, and the two
    things that identify a grade are the CLF's hash and the source encoding it started
    from. An attribute is written or absent, never written empty: a reader that finds
    no `proingest/clf` knows the frame is ungraded, where an empty one would only mean
    somebody lost the filename. The source encoding follows the same rule: a clip whose
    metadata named none (QC-046) leaves the attribute out rather than claiming a guess.
    """
    header: dict[str, Any] = {}
    if shot_color.source_encoding is not None:
        header[SOURCE_ENCODING_ATTRIBUTE] = shot_color.source_encoding
        if shot_color.source_encoding_origin is not None:
            header[SOURCE_ENCODING_ORIGIN_ATTRIBUTE] = shot_color.source_encoding_origin
    if loaded_clf is not None:
        header[CLF_ATTRIBUTE] = loaded_clf.path.name
        header[CLF_HASH_ATTRIBUTE] = loaded_clf.digest
    cdl = shot_color.cdl
    if cdl is not None:
        slope, offset, power, saturation, sop, sat, note = CDL_ATTRIBUTES
        header[slope] = cdl.slope
        header[offset] = cdl.offset
        header[power] = cdl.power
        header[saturation] = float(cdl.saturation)
        header[sop] = cdl.sop_text
        header[sat] = cdl.sat_text
        header[note] = CDL_NOTE
    return header


def write_frame(
    path: Path,
    pixels: npt.NDArray[Any],
    timecode_frames: int | None = None,
    fps: float = 24.0,
    compression_level: float | None = None,
    shot_color: clf.ShotColor = clf.DEFAULT_SHOT_COLOR,
    loaded_clf: clf.LoadedClf | None = None,
) -> None:
    """Write one delivery frame: DWAA, half float, data window equal to display window.

    `pixels` is `(h, w, 3)` or `(h, w, 4)` in any float type; it is stored as half
    (OQ-13). The data window comes from the array shape, so the two windows always
    agree and QC-104 cannot fail for a frame this function wrote.

    `compression_level` defaults to whatever the Settings page put in force for this
    process rather than to the constant, so a render honours the setting without every
    caller forwarding it.

    `shot_color` and `loaded_clf` are **recorded, never applied**: the pixels arrive
    already transformed and this states what was done to them. They are the pair
    `render.py` holds anyway, so the header cannot describe a chain other than the one
    the frame went through.

    The file is not read back here. Every frame is opened again by QC-103 after the
    sequence lands, and doing it twice would double the IO for nothing.
    """
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        raise ValueError(f"expected an (h, w, 3) or (h, w, 4) image, got shape {pixels.shape}")

    header: dict[str, Any] = {
        "compression": OpenEXR.DWAA_COMPRESSION,
        "dwaCompressionLevel": _LEVEL if compression_level is None else float(compression_level),
        "type": OpenEXR.scanlineimage,
        "chromaticities": CHROMATICITIES,
        COLORSPACE_ATTRIBUTE: color.PLATE_SPACE,
        **provenance(shot_color, loaded_clf),
    }
    if timecode_frames is not None:
        header["timeCode"] = _timecode_attribute(timecode_frames, fps)

    key = RGB_CHANNELS if pixels.shape[2] == 3 else RGBA_CHANNELS
    half = np.ascontiguousarray(pixels, dtype=np.float16)
    try:
        with OpenEXR.File(header, {key: half}) as handle:
            handle.write(str(path))
    except Exception as exc:  # the bindings raise several unrelated types
        raise ExrError(f"could not write {path}: {exc}") from exc


def _timecode_attribute(total_frames: int, fps: float) -> Any:
    """A `timeCode` attribute for one frame.

    Built through the shared timecode formatter rather than repeating the modulo
    arithmetic, so an output frame's timecode is derived exactly as a source frame's
    is. The bindings expose no constructor that takes the four fields, so an empty
    value is filled in.
    """
    hours, minutes, seconds, frame = (
        int(part) for part in frames.frames_to_timecode(total_frames, fps).split(":")
    )
    value = OpenEXR.TimeCode()
    value.hours, value.minutes, value.seconds, value.frame = hours, minutes, seconds, frame
    return value
