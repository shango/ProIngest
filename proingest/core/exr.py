"""OpenEXR reading.

Writing arrives with the render pipeline in M3. What is needed now is the header,
because an EXR sequence carries its start timecode in a `timeCode` attribute that
ffprobe does not surface, and COLOR_AND_FORMAT section 5 says source timecode comes
from the container or the EXR header.

The bindings take the header first and the channel dict second:
`OpenEXR.File(header, {"RGB": pixels})`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import OpenEXR

from proingest.core import frames

DWA_COMPRESSION_LEVEL = 45.0
"""Required by COLOR_AND_FORMAT section 3. Written as a float attribute."""


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
