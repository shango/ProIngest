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

from proingest.core import frames

DWA_COMPRESSION_LEVEL = 45.0
"""Required by COLOR_AND_FORMAT section 3. Written as a float attribute."""

CHROMATICITIES = (0.64, 0.33, 0.30, 0.60, 0.15, 0.06, 0.3127, 0.3290)
"""sRGB and Rec.709 primaries with a D65 white point, COLOR_AND_FORMAT section 1.

Written as the eight floats the attribute is defined as, red through white, so a
reader knows the primaries the linear data is in without being told.
"""

COLORSPACE_ATTRIBUTE = "proingest/colorspace"
COLORSPACE_VALUE = "scene_linear_sRGB"
"""What the pixels are, stated in the file. COLOR_AND_FORMAT section 1.

The tool applies no transform to raw output, so this records the source's colour
space rather than claiming a conversion happened. See OQ-17.
"""

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
    """Read one EXR header. Raises ExrError when the file will not open."""
    try:
        handle = OpenEXR.File(str(path))
        header = handle.header()
        part = handle.parts[0]
    except Exception as exc:  # the bindings raise several unrelated types
        raise ExrError(f"could not read EXR header from {path}: {exc}") from exc

    data_window = _window(header["dataWindow"])
    display_window = _window(header["displayWindow"])
    pixels = next(iter(part.channels.values())).pixels

    timecode = header.get("timeCode")
    rate = header.get("framesPerSecond")
    return ExrHeader(
        width=display_window[2] - display_window[0] + 1,
        height=display_window[3] - display_window[1] + 1,
        data_window=data_window,
        display_window=display_window,
        compression=str(header["compression"]).rsplit(".", 1)[-1],
        channels=_channel_names(part),
        pixel_type=str(pixels.dtype),
        timecode=_format_timecode(timecode) if timecode is not None else None,
        is_drop_frame=bool(getattr(timecode, "dropFrame", False)) if timecode is not None else False,
        frames_per_second=(int(rate.numerator), int(rate.denominator)) if rate is not None else None,
    )


def _format_timecode(value: Any) -> str:
    return f"{value.hours:02d}:{value.minutes:02d}:{value.seconds:02d}:{value.frame:02d}"


def start_timecode_frames(path: Path, fps: float) -> int | None:
    """Start timecode of an EXR as a frame count, or None when the header carries none.

    A drop-frame header is refused rather than silently miscounted; the caller
    reports that as QC-027.
    """
    header = read_header(path)
    if header.timecode is None:
        return None
    if header.is_drop_frame:
        raise ExrError(f"{path} carries drop-frame timecode (QC-027)")
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
            return np.stack(
                [np.asarray(channels[name].pixels, dtype=np.float32) for name in names], axis=-1
            )
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


def write_frame(
    path: Path,
    pixels: npt.NDArray[Any],
    timecode_frames: int | None = None,
    fps: float = 24.0,
    compression_level: float = DWA_COMPRESSION_LEVEL,
) -> None:
    """Write one delivery frame: DWAA, half float, data window equal to display window.

    `pixels` is `(h, w, 3)` or `(h, w, 4)` in any float type; it is stored as half
    (OQ-13). The data window comes from the array shape, so the two windows always
    agree and QC-104 cannot fail for a frame this function wrote.

    The file is not read back here. Every frame is opened again by QC-103 after the
    sequence lands, and doing it twice would double the IO for nothing.
    """
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        raise ValueError(f"expected an (h, w, 3) or (h, w, 4) image, got shape {pixels.shape}")

    header: dict[str, Any] = {
        "compression": OpenEXR.DWAA_COMPRESSION,
        "dwaCompressionLevel": float(compression_level),
        "type": OpenEXR.scanlineimage,
        "chromaticities": CHROMATICITIES,
        COLORSPACE_ATTRIBUTE: COLORSPACE_VALUE,
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
