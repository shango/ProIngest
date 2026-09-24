"""Ben's final EDL: the conform, and the CDL on each event, which is the grade.

COLOR_AND_FORMAT section 1. Colour is decided before the tool runs. Ben's session exports
an updated final EDL, and this module is where it is read: the conform, the approved
In/Out, and the **ASC CDL on each event, which is the grade** (decided 2026-09-18,
OQ-46). `core/color.py` supplies the legs either side of it, into ACEScct and out to
ACEScg, and this module supplies the middle.

**There are no per-shot grade files** (user, 2026-09-22). The CDL on the event is the
whole grade, and nothing beside the EDL is read: no `.cube`, no `.clf`, anywhere. What
went with them is QC-019, QC-039 and the probe that asked whether a cube had a display
rendering baked into it. The module keeps its name because it is still the module that
reads the session.

**The EDL is parsed here rather than through `core/timeline.py`.** That module reads the
shooters' timeline through otio, which is the right tool for a conform and the wrong one
here: otio's CMX3600 adapter hands back the CDL as numbers and drops the event id and the
verbatim `*ASC_SOP` / `*ASC_SAT` lines, and a delivered EXR is specified to carry that
original text (COLOR_AND_FORMAT, EXR metadata). An event line is a fixed format, so
reading it directly costs less than reconstructing what the adapter threw away, and
timecode still goes through `frames.timecode_to_frames`, which refuses drop-frame.

**An event belongs to the row whose file's timecode contains its source range** (OQ-30,
answered 2026-09-23 by Ben's real EDL, which carries no `FROM CLIP NAME` and reels every
event `AX`). Where an event does name its clip, the name has to agree. Every failure here
looks entirely plausible on screen: a row paired with a neighbour's event takes the wrong
approved In/Out and the wrong grade. Nothing guesses at the nearest candidate, and a match
that could go two ways is reported rather than chosen (QC-066, QC-067).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

import PyOpenColorIO as ocio

from proingest.core import color, frames, naming
from proingest.core.models import (
    CDL,
    FrameRate,
    InOut,
    MediaInfo,
    ShotRow,
    SourceEncodingOrigin,
)

log = logging.getLogger(__name__)


class ColorSessionError(RuntimeError):
    """The colour session package cannot be read. Reported as QC-008."""


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
    cdl: CDL | None = None
    speed: float | None = None
    """The M2 speed in frames a second, or None for an event with no motion effect."""

    freeze: bool = False
    """An M2 at speed 0: the event holds `source_in` for its whole length, so it uses one
    source frame and `source_out` is where the EDL would have run to, not a frame it shows."""

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
    What crosses is a colour space name and the CDL, which are both plain data.

    The default is a shot with no grade and no encoding resolved for it, which is the
    honest starting point rather than a usable chain: every chain starts at the encoding
    the clip's metadata names, and a shot with no grade renders through that leg alone.
    """

    source_encoding: str | None = None
    """The colour space the input transform starts at, resolved from what the clip named.

    None where the clip's metadata named no encoding, or named one the input transform
    table could not resolve (QC-046, QC-047). Nothing renders without it: the grade is
    applied in ACEScct and this is what gets the clip there.
    """

    source_encoding_origin: SourceEncodingOrigin | None = None
    """Which carrier named it, carried so the delivered EXR header can say.

    It describes the row's written name rather than the colour space above it, which is
    what the resolution was performed on. Set even where `source_encoding` is None, since
    a name that resolved to nothing still came from somewhere; `exr.provenance` writes it
    only beside an encoding, because an origin with nothing to originate says nothing.
    """

    cdl: CDL | None = None

    def plate_transforms(self) -> list[ocio.Transform]:
        """The plate branch: into ACEScct, the CDL, out to ACEScg. One leg with no grade.

        **The grade means something only in ACEScct** (OQ-46, decided 2026-09-18). It is
        the primaries of node one in a session whose timeline is ACEScct, so the tool gets
        the clip there from the encoding its metadata names and carries the result on to
        ACEScg. Either leg applied in a different space is a plausible looking wrong image
        rather than an error, which is why this returns the transforms a chain contains
        rather than leaving the rule to a caller. COLOR_AND_FORMAT section 1 states the
        same thing as a table.
        """
        if self.source_encoding is None:
            raise ClfError(
                f"no source encoding: nothing turns these pixels into {color.WORKING_SPACE} "
                f"for the grade, or into {color.PLATE_SPACE}. QC-046 and QC-047 report this "
                "before a render"
            )
        if self.cdl is None:
            return [color.input_transform(self.source_encoding)]
        return [color.to_working(self.source_encoding), color.cdl_transform(self.cdl), color.from_working()]

    def view_transforms(self) -> list[ocio.Transform]:
        """The view branch: the plate branch, then the ACES output transform to sRGB.

        The two branches share everything up to linear ACEScg, which is why this is the
        plate chain plus one leg rather than a chain of its own.
        """
        return [*self.plate_transforms(), color.output_transform()]


def resolved_encoding(row: ShotRow) -> str | None:
    """The colour space this row's clip named, or None when nothing resolves to one.

    One definition because two paths build a `ShotColor`: with a colour session and
    without one. None covers both a clip that named no encoding (QC-046) and one whose
    name the input transform table could not resolve (QC-047); the chain treats them
    identically, since neither gives it anything to convert with, and the rules are
    where the difference is reported rather than here.
    """
    if row.source_encoding is None:
        return None
    try:
        return color.resolve_encoding(row.source_encoding)
    except color.ColorError:
        return None


def has_grade(row: ShotRow) -> bool:
    """Whether the session left this row a grade: a CDL on its event.

    One definition, because the ingest report, QC-008, QC-009 and QC-048 all ask it and
    the answer has to be the same one the chain gives. Since 2026-09-22 that is the CDL
    and nothing else, there being no per-shot grade files.
    """
    return row.cdl is not None


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

    One definition, and the only one since the session is ingested rather than carried:
    a planned row and a reopened batch resolve their colour the same way, from the four
    fields ingest filled in. A row nothing was ingested for carries no grade, which
    renders through the input transform alone and is QC-009.
    """
    return ShotColor(
        source_encoding=resolved_encoding(row),
        source_encoding_origin=row.source_encoding_origin,
        cdl=row.cdl,
    )


def approved_in_out(event: ConformEvent, media: MediaInfo) -> InOut | None:
    """The event's source range as frame indices into this media.

    None when the media states no start timecode, because then an EDL's source timecode
    says nothing about which frames it means. The caller reports that; guessing an
    origin here would silently conform every row to the wrong frames.
    """
    if media.start_timecode is None:
        return None
    start = media.start_frame + (event.source_in - media.start_timecode)
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
                # clip name and the CDL that follow belong to the picture.
                continue
            if pending is not None:
                events.extend(pending.build(path, rate))
            pending = _Event(head) if _is_video(head["channel"]) else None
            continue
        if pending is not None:
            pending.comment(line)
    if pending is not None:
        events.extend(pending.build(path, rate))

    if not events:
        raise ColorSessionError(f"{path} carries no video events")
    return events


_EVENT_HEAD = re.compile(
    r"^(?P<event>\d{3,})\s+(?P<reel>\S+)\s+(?P<channel>\S+)\s+(?P<edit>[A-Z]+\d*)\b(?P<rest>.*)$"
)
_TIMECODE = re.compile(r"\d{1,2}:\d{2}:\d{2}[:;]\d{2}")
_FROM_CLIP = re.compile(r"^\*\s*FROM CLIP NAME:\s*(?P<name>.+?)\s*$", re.IGNORECASE)
_ASC_SOP = re.compile(r"^\*\s*ASC_SOP\b", re.IGNORECASE)
_ASC_SAT = re.compile(r"^\*\s*ASC_SAT\s+(?P<value>\S+)", re.IGNORECASE)
_MOTION = re.compile(r"^M2\s+\S+\s+(?P<speed>-?\d+(?:\.\d+)?)\s+")
"""A motion effect: `M2   AX   000.0   00:00:40:10`, reel, speed in frames a second, entry."""
_TRIPLE = re.compile(r"\(\s*(?P<a>\S+)\s+(?P<b>\S+)\s+(?P<c>\S+)\s*\)")


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
        self.sop_text = ""
        self.sat_text = ""
        self.speed: float | None = None

    def comment(self, line: str) -> None:
        from_clip = _FROM_CLIP.match(line)
        motion = _MOTION.match(line)
        if motion is not None:
            self.speed = float(motion["speed"])
        elif from_clip is not None:
            self.clip_name = from_clip["name"]
        elif _ASC_SOP.match(line):
            self.sop_text = line.strip()
        elif _ASC_SAT.match(line):
            self.sat_text = line.strip()

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
                cdl=_parse_cdl(self.sop_text, self.sat_text),
                speed=self.speed,
                freeze=self.speed == 0,
            )
        ]


def _parse_cdl(sop_text: str, sat_text: str) -> CDL | None:
    """The CDL off an event's comment lines, or None when it carries neither.

    A partial CDL is None rather than a default: slope 1 offset 0 power 1 is a real
    grade that says do nothing, so standing in for a missing line would record a
    neutral grade the colourist never wrote.
    """
    if not sop_text or not sat_text:
        return None
    triples = list(_TRIPLE.finditer(sop_text))
    saturation = _ASC_SAT.match(sat_text)
    if len(triples) != 3 or saturation is None:
        return None
    try:
        slope, offset, power = (_triple(match) for match in triples)
        return CDL(
            slope=slope,
            offset=offset,
            power=power,
            saturation=float(saturation["value"]),
            sop_text=sop_text,
            sat_text=sat_text,
        )
    except ValueError:
        return None


def _triple(match: re.Match[str]) -> tuple[float, float, float]:
    return float(match["a"]), float(match["b"]), float(match["c"])
