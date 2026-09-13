"""Integer frame math, timecode conversion, and In/Out input parsing.

Every quantity here is an integer frame index or count. Timecode is never stored or
compared as a float; it is converted at the edges only. See docs/COLOR_AND_FORMAT.md
section 6 for the definitions and docs/UI_SPEC.md section 5 for the input grammar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from proingest.core.naming import FIRST_OUTPUT_FRAME

TimecodeMode = Literal["source", "record"]

_RELATIVE = re.compile(r"^[+-]\d+$")
_TIMECODE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})(?P<sep>[:;])(?P<f>\d{2})$")
_ABSOLUTE = re.compile(r"^\d+$")

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24


def nominal_rate(fps: float) -> int:
    """The integer rate timecode counts at.

    23.976 and 24 both count 24 frames per timecode second; the fractional part is a
    playback rate, not a counting rate. Timecode math uses this, never the float.
    """
    rate = round(fps)
    if rate <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    return rate


def duration(in_frame: int, out_frame: int) -> int:
    """Inclusive frame count. `out` is the last frame delivered, not one past it."""
    return out_frame - in_frame + 1


def max_available_out(source_start: int, source_length: int) -> int:
    """Last usable source frame. Shown in the Max Avail column."""
    return source_start + source_length - 1


def output_frame_for(in_frame: int, source_frame: int) -> int:
    """Output sequences always start at 1001 regardless of source numbering."""
    return FIRST_OUTPUT_FRAME + (source_frame - in_frame)


def source_frame_for(in_frame: int, output_frame: int) -> int:
    return in_frame + (output_frame - FIRST_OUTPUT_FRAME)


def timecode_frames_for(source_frame: int, source_start: int, source_start_timecode: int) -> int:
    """The timecode of one source frame, in frames. COLOR_AND_FORMAT section 5.

    Source TC is the media's start timecode plus the offset into the media, so the
    origin is `source_start`, which is the first sequence number or 0 for a container,
    and not the In point.
    """
    return source_start_timecode + (source_frame - source_start)


# --- Timecode. Non-drop only; drop-frame is QC-027. ---


def frames_to_timecode(total_frames: int, fps: float) -> str:
    """Render a frame count as non-drop `HH:MM:SS:FF`, wrapping at 24 hours."""
    rate = nominal_rate(fps)
    if total_frames < 0:
        raise ValueError(f"cannot render negative frame count {total_frames} as timecode")
    frames = total_frames % rate
    total_seconds = total_frames // rate
    seconds = total_seconds % SECONDS_PER_MINUTE
    minutes = (total_seconds // SECONDS_PER_MINUTE) % MINUTES_PER_HOUR
    hours = (total_seconds // (SECONDS_PER_MINUTE * MINUTES_PER_HOUR)) % HOURS_PER_DAY
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def timecode_to_frames(text: str, fps: float) -> int:
    """Parse non-drop `HH:MM:SS:FF` into a frame count.

    Raises ValueError on malformed input or on a drop-frame separator, which the
    caller reports as QC-027.
    """
    rate = nominal_rate(fps)
    match = _TIMECODE.match(text.strip())
    if match is None:
        raise ValueError(f"{text!r} is not a timecode")
    if match["sep"] == ";":
        raise ValueError("drop-frame timecode is not supported (QC-027)")
    hours, minutes, seconds, frames = (int(match[k]) for k in ("h", "m", "s", "f"))
    if minutes >= MINUTES_PER_HOUR:
        raise ValueError(f"{text!r} has more than 59 minutes")
    if seconds >= SECONDS_PER_MINUTE:
        raise ValueError(f"{text!r} has more than 59 seconds")
    if frames >= rate:
        raise ValueError(f"{text!r} has a frame number at or above the rate {rate}")
    return ((hours * MINUTES_PER_HOUR + minutes) * SECONDS_PER_MINUTE + seconds) * rate + frames


# --- In/Out input parsing, UI_SPEC.md section 5. ---


@dataclass(frozen=True)
class EditContext:
    """What a typed In/Out value needs in order to become a source frame index.

    `source_start_timecode` is the timecode of `source_start`, in frames. When the
    display toggle is on record, a typed timecode is read against the record anchors
    instead, which is the same conversion with a different origin.
    """

    fps: float
    source_start: int
    source_start_timecode: int
    record_start_timecode: int
    record_start_source_frame: int
    mode: TimecodeMode = "source"

    def timecode_origin(self) -> tuple[int, int]:
        """(timecode frames, source frame) of the anchor the current mode reads against."""
        if self.mode == "record":
            return self.record_start_timecode, self.record_start_source_frame
        return self.source_start_timecode, self.source_start


@dataclass(frozen=True)
class ParsedInput:
    """Outcome of a cell edit.

    On failure `frame` is None and `error` carries the message the cell shows. The
    typed text is kept by the UI either way so the editor can see what they typed.
    """

    frame: int | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.frame is not None


def parse_in_out(text: str, current: int, context: EditContext) -> ParsedInput:
    """Turn a typed In/Out value into a source frame index.

    Formats are auto-detected in the order fixed by UI_SPEC section 5: relative
    offset, timecode, absolute source frame. Order matters because `+12` and `12`
    mean different things.
    """
    stripped = text.strip()
    if not stripped:
        return ParsedInput(None, "empty")

    if _RELATIVE.match(stripped):
        return ParsedInput(current + int(stripped))

    if _TIMECODE.match(stripped):
        try:
            typed = timecode_to_frames(stripped, context.fps)
        except ValueError as exc:
            return ParsedInput(None, str(exc))
        origin_timecode, origin_frame = context.timecode_origin()
        return ParsedInput(typed - origin_timecode + origin_frame)

    if _ABSOLUTE.match(stripped):
        return ParsedInput(int(stripped))

    return ParsedInput(None, "unrecognized")


def source_frame_to_timecode(source_frame: int, context: EditContext) -> str:
    """Render a source frame in whichever timecode the display toggle is showing.

    A frame before the media's own start has no timecode of its own. The list stores
    such a value rather than refusing it, so QC-031 can report it, and this shows it
    as the negative it is rather than raising inside a cell.
    """
    origin_timecode, origin_frame = context.timecode_origin()
    total = origin_timecode + (source_frame - origin_frame)
    if total < 0:
        return f"-{frames_to_timecode(-total, context.fps)}"
    return frames_to_timecode(total, context.fps)
