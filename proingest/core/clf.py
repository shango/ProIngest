"""Ben's final EDL, which is the cut, and a shot's colour chain from its AMF.

COLOR_AND_FORMAT section 1. Colour is decided before the tool runs. Since 2026-09-28
(user) Ben's session hands over the final EDL, which is **the cut** (the approved In/Out
of every event), and one AMF per event with the CLFs it names, which is **the colour**
(`core/amf.py`). The EDL's `*ASC_SOP` lines, if any, are no longer read. This module keeps
its name: it is still where the session's cut is read, and `ShotColor` is where a shot's
chain is put together.

**The EDL is parsed here rather than through `core/timeline.py`.** An event line is a
fixed format, so reading it directly costs less than reconstructing what otio's CMX3600
adapter throws away (the event id, which is also how an AMF is matched to its event), and
timecode still goes through `frames.timecode_to_frames`, which refuses drop-frame.

**An event belongs to the row whose file's timecode contains its source range** (OQ-30,
answered 2026-09-23 by Ben's real EDL). Where an event does name its clip, the name has to
agree. Every failure here looks entirely plausible on screen: a row paired with a
neighbour's event takes the wrong approved In/Out and the wrong AMF. Nothing guesses at the
nearest candidate, and a match that could go two ways is reported rather than chosen
(QC-066, QC-067).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

import PyOpenColorIO as ocio

from proingest.core import color, frames, naming
from proingest.core.models import (
    FrameRate,
    GradeLook,
    InOut,
    MediaInfo,
    ShotRow,
    SourceEncodingOrigin,
)

log = logging.getLogger(__name__)


class ColorSessionError(RuntimeError):
    """The final EDL cannot be read. Reported as QC-002."""


class ClfError(RuntimeError):
    """A chain that cannot be built, most often because nothing resolved the encoding."""


@dataclass(frozen=True)
class ConformEvent:
    """One event of the colour session's final EDL.

    Source and record values are frames at the EDL's rate, and both ranges are
    inclusive: an EDL's own out timecode is the first frame after the cut and it is
    converted on the way in, so nothing downstream has to remember which convention
    this came from.
    """

    event_id: str
    reel: str
    clip_name: str
    source_in: int
    source_out: int
    record_in: int
    record_out: int
    speed: float | None = None
    """The M2 speed in frames a second, or None for an event with no motion effect."""

    freeze: bool = False
    """An M2 at speed 0: the event holds `source_in` for its whole length, so it uses one
    source frame and `source_out` is where the EDL would have run to, not a frame it shows."""

    position: int = 0
    """Its place among the EDL's video events, from 0: Resolve's timeline index, which is
    what an AMF's file name carries (`amf.Amf.index`). Not the event number less one: an
    audio-only event takes a number of its own (turnover134, 2026-10-05)."""

    def retimed(self, rate: FrameRate) -> bool:
        """A motion effect other than a freeze or normal speed: a retime or a reversal,
        which the tool does not render (OQ-63, QC-073)."""
        return self.speed is not None and self.speed != 0 and self.speed != rate.as_float()

    @property
    def used_out(self) -> int:
        """The last source frame the event actually shows."""
        return self.source_in if self.freeze else self.source_out

    @property
    def duration(self) -> int:
        """Source frames the event uses: one for a freeze."""
        return frames.duration(self.source_in, self.used_out)

    @property
    def use(self) -> tuple[int, int]:
        """What makes two events of one clip the same use of it, as Resolve counts uses:
        the source range the EDL states. The metadata CSV carries one row per clip per use
        (verified on Turnover121, 2026-09-23), so this is what pairs events with rows. A
        freeze keeps its stated out, because two holds of different length are two uses."""
        return self.source_in, self.source_out

    def named(self, clip_name: str) -> ConformEvent:
        """This event with the clip it cuts, from the ALE when the EDL names none."""
        return replace(self, clip_name=clip_name)

    @property
    def clip_stem(self) -> str:
        """`FROM CLIP NAME` without its extension, which is what a clip name is."""
        return Path(self.clip_name).stem


@dataclass(frozen=True)
class ShotColor:
    """One shot's colour, in the form that survives a pickle to a worker process.

    A render job is self contained (`planner.DeliverableJob`), so what a worker needs to
    know about colour travels on it. That rules out holding an `ocio` object: it does not
    pickle, and a transform built in the parent could not cross a spawn boundary anyway.
    What crosses is names and paths, which are plain data.

    The default is a shot with nothing resolved, which is the honest starting point rather
    than a usable chain: every chain starts at the encoding the clip's AMF names.
    """

    source_encoding: str | None = None
    """The colour space the AMF's input transform converts from, or None (QC-046, QC-047).
    Nothing renders without it."""

    source_encoding_origin: SourceEncodingOrigin | None = None
    """Which carrier named it, carried so the delivered EXR header can say."""

    looks: tuple[GradeLook, ...] = ()
    """The AMF's looks in order: the Reference Gamut Compress, then the CLF nodes."""

    amf: str = ""
    """The AMF's file name, for the delivered EXR header."""

    display: str | None = None
    view: str | None = None
    """What the AMF's output transform resolved to: where a reference is viewed."""

    def plate_transforms(self) -> list[ocio.Transform]:
        """The plate branch: into ACES2065-1, the looks in order, out to ACEScg.

        One leg when there is no look, which is the same pixels in one transform.
        """
        if self.source_encoding is None:
            raise ClfError(
                f"no source encoding: nothing turns these pixels into {color.ACES} "
                f"or {color.PLATE_SPACE}. QC-046 and QC-047 report this before a render"
            )
        if not self.looks:
            return [color.input_transform(self.source_encoding)]
        legs: list[ocio.Transform] = [color.to_aces(self.source_encoding)]
        for look in self.looks:
            if look.kind == "look":
                legs.append(color.look_transform(look.name))
            elif look.kind == "cdl":
                legs.append(color.cdl_transform(look.cdl, look.name))
            else:
                legs.append(color.clf_transform(Path(look.name)))
        legs.append(color.to_plate())
        return legs

    def view_transforms(self) -> list[ocio.Transform]:
        """The view branch: the plate branch, then the AMF's output transform.

        The two branches share everything up to linear ACEScg, which is why this is the
        plate chain plus one leg rather than a chain of its own.
        """
        if self.display is None or self.view is None:
            raise ClfError("no output transform: the clip's AMF names none the config has (QC-079)")
        return [*self.plate_transforms(), color.output_transform(self.display, self.view)]


def resolved_encoding(row: ShotRow) -> str | None:
    """The colour space this row's AMF named, or None when it names none the config has."""
    if row.source_encoding is None:
        return None
    try:
        return color.resolve_encoding(row.source_encoding)
    except color.ColorError:
        return None


def has_grade(row: ShotRow) -> bool:
    """Whether the colourist left this row a grade: a CLF in its AMF. QC-009 asks."""
    return row.grade is not None and row.grade.graded


DEFAULT_SHOT_COLOR = ShotColor()
"""No grade and no encoding: what a job carries until the planner fills it in.

A copy job carries this and ignores it, because bytes are bytes. Anything that renders
pixels is given a real one, and a row that cannot be given one is what QC-046 reports.
"""


@dataclass(frozen=True)
class ColorSession:
    """One final EDL, read once. It is the whole of what Ben's session hands over."""

    edl_path: Path
    events: list[ConformEvent]

    def event_for(self, row: ShotRow) -> ConformEvent | None:
        """The one event that conforms this row, or None when there is none or several."""
        found = self.candidates(row)
        return found[0] if len(found) == 1 else None

    def candidates(self, row: ShotRow) -> list[ConformEvent]:
        """Every event that could conform this row.

        An event that names its clip (`FROM CLIP NAME`) is this row's when the name agrees,
        compared without extension or case; QC-029 reports one that then runs outside the
        media. An event that names nothing, which is what Resolve's CDL export writes, is
        this row's when its whole source range sits inside the file's own timecode. The
        reel is never read: the real export writes `AX` on every event.

        A list rather than one answer, because an event inside two files, or two events
        inside one file, is a match the tool must refuse rather than choose (QC-067), and
        only the caller sees every row at once.
        """
        stem = Path(row.clip_name).stem.casefold()
        span = _timecode_span(row.media)
        found: list[ConformEvent] = []
        for event in self.events:
            if event.clip_name:
                if event.clip_stem.casefold() == stem:
                    found.append(event)
            elif span is not None and span[0] <= event.source_in <= event.used_out <= span[1]:
                found.append(event)
        return found


def _timecode_span(media: MediaInfo | None) -> tuple[int, int] | None:
    """The first and last source timecode frame the file holds, or None when it states none."""
    if media is None or media.start_timecode is None:
        return None
    return media.start_timecode, media.start_timecode + media.frame_count - 1


def load_session(
    edl_path: Path, rate: FrameRate, show_pattern: str = naming.DEFAULT_SHOW_PATTERN
) -> ColorSession:
    """Read the final EDL. It is the whole session as far as this tool is concerned."""
    return ColorSession(edl_path=edl_path, events=read_final_edl(edl_path, rate))


def shot_color(row: ShotRow) -> ShotColor:
    """What this row's deliverables are rendered through, read off the row alone.

    A planned row and a reopened batch resolve their colour the same way, from what the
    scan put on the row out of its AMF.
    """
    grade = row.grade
    shown = (grade.display, grade.view) if grade is not None and grade.display and grade.view else None
    display, view = shown or color.DEFAULT_VIEW
    return ShotColor(
        source_encoding=resolved_encoding(row),
        source_encoding_origin=row.source_encoding_origin,
        looks=grade.looks if grade is not None else (),
        amf=grade.amf.name if grade is not None else "",
        display=display,
        view=view,
    )


def approved_in_out(event: ConformEvent, media: MediaInfo) -> InOut:
    """The event's source range as frame indices into this media, at face value.

    A file with no timecode is counted from 00:00:00:00, which is where Resolve starts one
    and what the EDL's source In counts from (turnover097's events 008 and 015). QC-028 says
    the file has none; the cut is taken as the timeline has it (user, 2026-10-07).
    """
    start = media.start_frame + (event.source_in - (media.start_timecode or 0))
    return InOut(start, start + event.duration - 1)


def read_final_edl(path: Path, rate: FrameRate) -> list[ConformEvent]:
    """Parse the colour session's final EDL into events, in file order.

    Video events only: an audio only event conforms nothing, and an EDL that carries
    both has the picture event for the same cut anyway.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise ColorSessionError(f"could not read {path}: {exc}") from exc

    events: list[ConformEvent] = []
    pending: _Event | None = None
    for line in text.splitlines():
        head = _EVENT_HEAD.match(line)
        if head is not None:
            if _same_event_audio(pending, head):
                # A `V` line then an `A` line under one event number is one cut; the
                # clip name that follows belongs to the picture.
                continue
            if pending is not None:
                _place(events, pending.build(path, rate))
            pending = _Event(head) if _is_video(head["channel"]) else None
            continue
        if pending is not None:
            pending.comment(line)
    if pending is not None:
        _place(events, pending.build(path, rate))

    if not events:
        raise ColorSessionError(f"{path} carries no video events")
    return events


def _place(events: list[ConformEvent], built: list[ConformEvent]) -> None:
    """Append, numbering each by its place among the video events kept so far. A
    zero-length event is the outgoing side of a dissolve, part of the clip before it, so
    it takes no place."""
    events.extend(replace(event, position=len(events) + offset) for offset, event in enumerate(built))


_EVENT_HEAD = re.compile(
    r"^(?P<event>\d{3,})\s+(?P<reel>\S+)\s+(?P<channel>\S+)\s+(?P<edit>[A-Z]+\d*)\b(?P<rest>.*)$"
)
_TIMECODE = re.compile(r"\d{1,2}:\d{2}:\d{2}[:;]\d{2}")
_FROM_CLIP = re.compile(r"^\*\s*FROM CLIP NAME:\s*(?P<name>.+?)\s*$", re.IGNORECASE)
_MOTION = re.compile(r"^M2\s+\S+\s+(?P<speed>-?\d+(?:\.\d+)?)\s+")
"""A motion effect: `M2   AX   000.0   00:00:40:10`, reel, speed in frames a second, entry."""


def _same_event_audio(pending: _Event | None, head: re.Match[str]) -> bool:
    """An audio line under the event number of the picture event being read."""
    return pending is not None and head["event"] == pending.head["event"] and not _is_video(head["channel"])


def _is_video(channel: str) -> bool:
    """`V`, or `B` and `AA/V` which carry picture and audio together."""
    return "V" in channel.upper() or channel.upper() == "B"


class _Event:
    """One event under construction: the head line, then the comments under it."""

    def __init__(self, head: re.Match[str]) -> None:
        self.head = head
        self.clip_name = ""
        self.speed: float | None = None

    def comment(self, line: str) -> None:
        from_clip = _FROM_CLIP.match(line)
        motion = _MOTION.match(line)
        if motion is not None:
            self.speed = float(motion["speed"])
        elif from_clip is not None:
            self.clip_name = from_clip["name"]

    def build(self, path: Path, rate: FrameRate) -> list[ConformEvent]:
        """The event, or nothing for a zero-length one: the outgoing side of a dissolve
        is written as a cut that covers no frames, and it conforms nothing."""
        head = self.head
        found = _TIMECODE.findall(head["rest"])
        if len(found) < 4:
            raise ColorSessionError(f"{path}: event {head['event']} states {len(found)} timecodes, not four")
        try:
            times = [frames.timecode_to_frames(value, rate.as_float()) for value in found[-4:]]
        except ValueError as exc:
            raise ColorSessionError(f"{path}: event {head['event']} has {exc}") from exc
        source_in, source_out, record_in, record_out = times
        if source_out <= source_in:
            return []
        return [
            ConformEvent(
                event_id=head["event"],
                reel=head["reel"],
                clip_name=self.clip_name,
                source_in=source_in,
                source_out=source_out - 1,
                record_in=record_in,
                record_out=record_out - 1,
                speed=self.speed,
                freeze=self.speed == 0,
            )
        ]
